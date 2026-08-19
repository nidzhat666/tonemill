from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ExecutionPath = Literal["gpu", "cpu"]


@dataclass(frozen=True)
class ProfileParams:
    """A profile's tunable grading/encode parameters (FR-024). hlg-gpu/hlg-cpu's values are
    validated (FR-011) and MUST NOT be re-derived by eye -- see tools/tune_profile.py.
    """

    tonemap_operator: str
    contrast: float
    saturation_or_vibrance: float
    quality_target: str
    extra: dict[str, str] = field(default_factory=dict)


class GradingProfile(ABC):
    """A pluggable color-grading pipeline (FR-023, FR-025). New source formats subclass
    this rather than changing the job/queue/API/storage layers.
    """

    name: str
    source_format: str
    execution_path: ExecutionPath
    implemented: bool = True
    performance_reference: str = ""

    @abstractmethod
    async def is_available(self) -> bool:
        """Whether this profile can actually run on the current host."""

    @abstractmethod
    def build_command(
        self, source_path: Path, output_path: Path, *, max_quality: bool = False
    ) -> list[str]:
        """Build the ffmpeg argv for one decode/tone-map/grade/encode pass.

        max_quality swaps the encoder's quality target for a near-lossless one in the SAME
        pass (FR-028) -- callers must reject it before calling this on a non-GPU profile.
        Output MUST be tagged bt709/bt709/bt709/tv (FR-014).
        """


def output_color_tagging_args() -> list[str]:
    """Belt-and-suspenders top-level ffmpeg output flags for bt709/bt709/bt709/tv (FR-014).

    Not the relied-upon mechanism -- that's in-graph tagging (libplacebo's own params for
    hlg-gpu, zscale + setparams for hlg-cpu). Validated this session that top-level *output*
    flags alone don't reliably reach an encoder's VUI signaling (confirmed on libx265;
    hevc_nvenc unverified, no GPU in dev/test).
    """
    return [
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
    ]


class NotImplementedProfile(GradingProfile):
    """A registered-but-not-yet-implemented profile (e.g. d-log-m, FR-015)."""

    implemented = False
    execution_path = "cpu"

    async def is_available(self) -> bool:
        return False

    def build_command(
        self, source_path: Path, output_path: Path, *, max_quality: bool = False
    ) -> list[str]:
        raise NotImplementedError(f"profile '{self.name}' is registered but not implemented")
