from pathlib import Path

from tonemill.config import Settings
from tonemill.profiles.base import GradingProfile, ProfileParams, mp4_playback_compatibility_args
from tonemill.profiles.registry import is_ffmpeg_available

_CONTRAST = 1.06
_VIBRANCE = 0.22
_QUALITY_CRF = 20


class HlgCpuProfile(GradingProfile):
    """CPU-only fallback (~12 fps on 4K60 -- dev-machine/no-GPU-host path, not a
    production throughput target). Same HLG->Rec.709 color transform as hlg-gpu, no
    max_quality equivalent (FR-029 is GPU-only in v1).

    contrast/saturation are validated the same way as hlg-gpu's (FR-011, FR-017) -- do not
    re-derive by eye.
    """

    name = "hlg-cpu"
    source_format = "HLG/BT.2020"
    execution_path = "cpu"
    performance_reference = "~12 fps on 4K60 HLG source -- fallback only, not a throughput target"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.params = ProfileParams(
            tonemap_operator="hable",
            contrast=_CONTRAST,
            saturation_or_vibrance=_VIBRANCE,
            quality_target=f"crf{_QUALITY_CRF}",
        )

    async def is_available(self) -> bool:
        return is_ffmpeg_available(self._settings.ffmpeg_path)

    async def build_command(
        self, source_path: Path, output_path: Path, *, max_quality: bool = False
    ) -> list[str]:
        """max_quality is GPU-only (FR-029); the worker already rejects it before ever
        calling this, so it's accepted-and-ignored here rather than silently downgraded.
        """
        del max_quality
        vf = (
            "zscale=transfer=linear:npl=100,"
            "format=gbrpf32le,"
            "zscale=primaries=bt709,"
            f"tonemap={self.params.tonemap_operator},"
            "zscale=transfer=bt709:matrix=bt709:range=tv,"
            "format=yuv420p,"
            f"eq=contrast={self.params.contrast},"
            f"vibrance=intensity={self.params.saturation_or_vibrance},"
            "unsharp,"
            f"{_output_color_tagging_filter()}"
        )
        return [
            self._settings.ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-vf",
            vf,
            "-c:v",
            "libx265",
            "-preset",
            "medium",
            "-crf",
            str(_QUALITY_CRF),
            "-color_range",
            "tv",
            *mp4_playback_compatibility_args(),
            "-progress",
            "pipe:1",
            "-nostats",
            str(output_path),
        ]


def _output_color_tagging_filter() -> str:
    """In-graph bt709/bt709/bt709/tv tag (FR-014) -- see base.output_color_tagging_args for
    why this, and not top-level output flags alone, is the mechanism actually relied on.
    """
    return "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
