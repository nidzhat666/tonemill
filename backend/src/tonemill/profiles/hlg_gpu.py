import asyncio
from pathlib import Path

import numpy as np

from tonemill.config import Settings
from tonemill.profiles.base import GradingProfile, ProfileParams, output_color_tagging_args
from tonemill.progress.ffmpeg_progress import probe_duration_ms
from tonemill.tools.tune_profile import worst_case_clip_fraction

_VIBRANCE = 0.22
_DEFAULT_QUALITY_CQ = 20
_MAX_QUALITY_CQ = 1

# Highest first: _auto_contrast tries these in order and returns the first (highest) one
# that stays under _CLIP_THRESHOLD. 1.00 (no boost at all) is always the last resort.
_CANDIDATE_CONTRASTS = [1.18, 1.15, 1.12, 1.09, 1.06, 1.03, 1.00]
_CLIP_THRESHOLD = 0.003
_SAMPLE_FPS = 1
_SAMPLE_WINDOW_SECONDS = 6

# Software decode -> OpenCL tonemap -> NVENC encode. NOT `-hwaccel cuda` decode: tested and
# confirmed this ffmpeg build has no CUDA->OpenCL frame interop (`hwupload` targeting OpenCL
# rejects a `-hwaccel cuda` frame with "Impossible to convert between the formats supported
# by hwupload and auto_scale" / error -38), so decode stays on CPU. Only the tonemap and
# encode stages are GPU-accelerated here -- see the class docstring for why libplacebo/Vulkan
# (which did use CUDA decode) isn't the implementation anymore.
_TONEMAP_OPENCL = (
    "format=p010le,hwupload,"
    "tonemap_opencl=tonemap=hable:format=nv12:primaries=bt709:transfer=bt709:matrix=bt709,"
    "hwdownload,format=nv12"
)


class HlgGpuProfile(GradingProfile):
    """HLG (BT.2020) -> Rec.709 SDR: software decode + OpenCL tonemap (`tonemap_opencl`) +
    NVENC encode.

    NOT libplacebo/Vulkan (this profile's original implementation) -- Vulkan reliably fails
    to initialize inside this host's Docker mount namespace (`vk_icdGetInstanceProcAddr`
    returns NULL / VK_ERROR_INCOMPATIBLE_DRIVER), confirmed NOT fixable via CDI,
    `--privileged`, full namespace sharing, or a newer toolkit -- ICD manifest, driver
    library version, `/proc/driver/nvidia`, and device nodes were all confirmed
    byte-identical to the host, yet it still fails; `nsenter`ing into the host's own mount
    namespace makes the exact same binary work. `tonemap_opencl` was verified to genuinely
    initialize and encode under this exact `runtime: nvidia` container config
    (research.md #11) -- CUDA decode was tried too but this build has no CUDA->OpenCL frame
    interop, so decode is software.

    contrast is NOT a fixed, offline-tuned constant like vibrance/unsharp are -- see
    _auto_contrast. vibrance/unsharp stay constant because they're a taste choice, not a
    correctness constraint; contrast varies per-source because "how much highlight headroom
    does this specific clip have" is a measurable fact, not a taste choice, and a constant
    tuned against a handful of reference scenes doesn't generalize to arbitrary footage
    (confirmed: real HLG drone clips with a blown-out sky exceed the clipping threshold even
    at contrast=1.00 -- no fixed positive value would have been safe for them).
    """

    name = "hlg-gpu"
    source_format = "HLG/BT.2020"
    execution_path = "gpu"
    performance_reference = (
        "not formally benchmarked on this engine yet (research.md #11) -- informally, "
        "~53fps / ~0.88x realtime for decode+tonemap+encode alone on a 4K60 HLG source, "
        "RTX 3080 Ti; the per-job auto-contrast measurement pass adds its own un-benchmarked "
        "overhead on top (up to 7 short sample probes, worst case)"
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.params = ProfileParams(
            tonemap_operator="hable",
            contrast=0.0,  # not a fixed value -- see _auto_contrast; field kept for parity
            saturation_or_vibrance=_VIBRANCE,
            quality_target=f"cq{_DEFAULT_QUALITY_CQ}",
        )

    async def is_available(self) -> bool:
        return await _detect_opencl_tonemap_available(self._settings.ffmpeg_path)

    async def build_command(
        self, source_path: Path, output_path: Path, *, max_quality: bool = False
    ) -> list[str]:
        cq = _MAX_QUALITY_CQ if max_quality else _DEFAULT_QUALITY_CQ
        contrast = await _auto_contrast(
            self._settings.ffmpeg_path, self._settings.ffprobe_path, source_path
        )
        vf = f"{_TONEMAP_OPENCL},eq=contrast={contrast},vibrance=intensity={_VIBRANCE},unsharp"
        return [
            self._settings.ffmpeg_path,
            "-y",
            "-init_hw_device",
            "opencl=ocl:0.0",
            "-i",
            str(source_path),
            "-vf",
            vf,
            "-c:v",
            "hevc_nvenc",
            "-rc",
            "vbr",
            "-cq",
            str(cq),
            "-b:v",
            "0",
            *output_color_tagging_args(),
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_path),
        ]


async def _detect_opencl_tonemap_available(ffmpeg_path: str) -> bool:
    """Whether the real chain this profile needs -- OpenCL device init, `tonemap_opencl`,
    hevc_nvenc -- actually initializes right now, not just whether ffmpeg was compiled with
    these features (see registry.detect_gpu_encoder_available's docstring for why a
    compiled-in check alone isn't enough; the exact same blind spot is what let this
    profile's original libplacebo/Vulkan implementation silently report "available" while
    genuinely broken, research.md #9). The probe frame is explicitly tagged HLG/BT.2020
    (`setparams=...`) -- confirmed required: `tonemap_opencl` rejects an untagged lavfi
    source with "unsupported transfer function characteristic", which would make this probe
    falsely report unavailable even when the real (correctly-tagged) production path works.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-init_hw_device",
            "opencl=ocl:0.0",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=256x256:d=0.1",
            "-vf",
            "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc,"
            f"{_TONEMAP_OPENCL},fps=1",
            "-frames:v",
            "1",
            "-c:v",
            "hevc_nvenc",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=15)
    except (OSError, TimeoutError):
        return False
    return process.returncode == 0


async def _probe_dimensions(ffprobe_path: str, source_path: Path) -> tuple[int, int]:
    process = await asyncio.create_subprocess_exec(
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(source_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe exited with code {process.returncode}")
    width_str, height_str = stdout.decode().strip().split("x")
    return int(width_str), int(height_str)


async def _extract_sample_frames(
    ffmpeg_path: str,
    source_path: Path,
    seek_seconds: float,
    contrast: float,
    width: int,
    height: int,
) -> np.ndarray | None:
    """Decode a short window through the real tonemap+grade chain at `contrast` and return
    sampled frames as (N, H, W, 3) uint8, or None if the probe didn't yield a usable frame
    (treated as "can't confirm this is safe", not a crash -- see _auto_contrast).
    """
    process = await asyncio.create_subprocess_exec(
        ffmpeg_path,
        "-y",
        "-ss",
        str(seek_seconds),
        "-t",
        str(_SAMPLE_WINDOW_SECONDS),
        "-init_hw_device",
        "opencl=ocl:0.0",
        "-i",
        str(source_path),
        "-vf",
        f"{_TONEMAP_OPENCL},eq=contrast={contrast},fps={_SAMPLE_FPS}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    raw, _ = await process.communicate()
    if process.returncode != 0 or not raw:
        return None
    frame_bytes = width * height * 3
    usable_len = (len(raw) // frame_bytes) * frame_bytes
    if usable_len == 0:
        return None
    return np.frombuffer(raw[:usable_len], dtype=np.uint8).reshape(-1, height, width, 3)


async def _auto_contrast(ffmpeg_path: str, ffprobe_path: str, source_path: Path) -> float:
    """Per-source auto-contrast (research.md #11): measure THIS clip's own highlight
    headroom -- not a fixed constant tuned once against a handful of offline reference
    scenes -- using the same worst-case clipping-fraction metric tools/tune_profile.py uses
    (FR-011/FR-017), and pick the highest candidate that stays under the threshold.

    Falls back to 1.00 (no contrast boost) if every candidate exceeds the threshold, or if
    the source can't be probed/sampled at all -- fail toward the safest output, never toward
    a crash or a guessed value. Confirmed on real HLG drone footage: several clips with a
    blown-out sky exceed the threshold even at 1.00, and that's a legitimate answer, not a
    bug in the measurement.
    """
    no_boost = _CANDIDATE_CONTRASTS[-1]
    try:
        duration_ms = await probe_duration_ms(ffprobe_path, str(source_path))
        width, height = await _probe_dimensions(ffprobe_path, source_path)
    except (RuntimeError, ValueError, OSError):
        return no_boost

    duration_seconds = duration_ms / 1000
    seek_seconds = max(0.0, duration_seconds * 0.3 - _SAMPLE_WINDOW_SECONDS / 2)

    for contrast in _CANDIDATE_CONTRASTS:
        frames = await _extract_sample_frames(
            ffmpeg_path, source_path, seek_seconds, contrast, width, height
        )
        if frames is None or frames.size == 0:
            continue
        if worst_case_clip_fraction(frames) < _CLIP_THRESHOLD:
            return contrast
    return no_boost
