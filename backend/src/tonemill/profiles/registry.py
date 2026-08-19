import asyncio
import shutil

from tonemill.profiles.base import GradingProfile


class UnknownProfileError(Exception):
    """Raised when a client references a profile name the registry doesn't know (FR-016)."""


class ProfileRegistry:
    """Name -> profile lookup (FR-023, FR-024, FR-035). Loaded once at process startup;
    changing profiles requires a restart, not a live/hot-reload mechanism (research.md #12).
    """

    def __init__(self) -> None:
        self._profiles: dict[str, GradingProfile] = {}

    def register(self, profile: GradingProfile) -> None:
        self._profiles[profile.name] = profile

    def get(self, name: str) -> GradingProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise UnknownProfileError(name) from exc

    def exists(self, name: str) -> bool:
        return name in self._profiles

    def list(self) -> list[GradingProfile]:
        return list(self._profiles.values())


async def detect_gpu_encoder_available(ffmpeg_path: str, encoder: str = "hevc_nvenc") -> bool:
    """Whether `encoder` can actually initialize right now, for FR-012/FR-013's auto/explicit
    resolution.

    `ffmpeg -encoders` only reports what was compiled in -- BtbN's build always includes
    hevc_nvenc, so that check reports "available" even on hosts with no real NVIDIA GPU/driver
    at all (confirmed: `auto` picked hlg-gpu on a non-GPU host, which then failed encoding).
    This runs a trivial one-frame encode instead, which only succeeds if the encoder can
    genuinely initialize against real hardware.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.1",
            "-frames:v",
            "1",
            "-c:v",
            encoder,
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


def is_ffmpeg_available(ffmpeg_path: str) -> bool:
    return shutil.which(ffmpeg_path) is not None or ffmpeg_path.startswith("/")


async def resolve_auto(registry: ProfileRegistry) -> GradingProfile:
    """profile: "auto" (FR-012) resolves to the first implemented, available GPU-path
    profile, else the first available CPU-path profile. Raises if none is available.
    """
    candidates = [p for p in registry.list() if p.implemented]
    for path in ("gpu", "cpu"):
        for profile in candidates:
            if profile.execution_path == path and await profile.is_available():
                return profile
    raise RuntimeError("no available grading profile on this host (auto resolution failed)")
