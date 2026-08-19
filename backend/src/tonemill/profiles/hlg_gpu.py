from pathlib import Path

from tonemill.config import Settings
from tonemill.profiles.base import GradingProfile, ProfileParams, output_color_tagging_args
from tonemill.profiles.registry import detect_gpu_encoder_available

_CONTRAST = 1.12
_SATURATION = 1.10
_DEFAULT_QUALITY_CQ = 20
_MAX_QUALITY_CQ = 1


class HlgGpuProfile(GradingProfile):
    """HLG (BT.2020) -> Rec.709 SDR, entirely on GPU via CUDA decode + libplacebo.

    contrast/saturation are validated (FR-011, do not re-derive by eye): swept across 4
    reference scenes (overcast road, bright sky+sea, dusk with people, white rooftops),
    picked as the highest value where the worst scene stays under 0.3% highlight/channel
    clipping. Re-tune only via tools/tune_profile.py (FR-017).

    _MAX_QUALITY_CQ is not yet benchmarked the same way (research.md #8) -- an initial,
    conservative near-lossless starting point for FR-027/FR-028, to be re-validated.
    """

    name = "hlg-gpu"
    source_format = "HLG/BT.2020"
    execution_path = "gpu"
    performance_reference = "~65 fps / ~1.08x realtime on 4K60 HLG source, RTX 3080 Ti"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.params = ProfileParams(
            tonemap_operator="hable",
            contrast=_CONTRAST,
            saturation_or_vibrance=_SATURATION,
            quality_target=f"cq{_DEFAULT_QUALITY_CQ}",
        )

    async def is_available(self) -> bool:
        return await detect_gpu_encoder_available(self._settings.ffmpeg_path, "hevc_nvenc")

    def build_command(
        self, source_path: Path, output_path: Path, *, max_quality: bool = False
    ) -> list[str]:
        cq = _MAX_QUALITY_CQ if max_quality else _DEFAULT_QUALITY_CQ
        libplacebo = (
            f"libplacebo=tonemapping={self.params.tonemap_operator}"
            f":contrast={self.params.contrast}"
            f":saturation={self.params.saturation_or_vibrance}"
            ":peak_detect=true"
            ":colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
        )
        return [
            self._settings.ffmpeg_path,
            "-y",
            "-hwaccel",
            "cuda",
            "-i",
            str(source_path),
            "-vf",
            libplacebo,
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
