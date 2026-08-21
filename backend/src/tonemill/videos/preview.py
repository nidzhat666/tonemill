import asyncio
from dataclasses import dataclass
from pathlib import Path

_THUMBNAIL_SECONDS = 5.0
_CLIP_SECONDS = 1.5
_MAX_CLIPS = 10


async def extract_thumbnail(ffmpeg_path: str, output_path: Path, duration_seconds: float) -> Path:
    """One representative frame (FR-001) -- at 5s, or the video's midpoint when it's shorter
    than that (FR-002; spec.md Edge Cases). Deliberately the midpoint, not a frame near the
    very end: the last moments of a short clip are more likely to be a fade-out or a stopping
    point than a representative one.
    """
    t = _THUMBNAIL_SECONDS if duration_seconds >= _THUMBNAIL_SECONDS else duration_seconds / 2
    thumbnail_path = output_path.with_name("thumbnail.jpg")
    process = await asyncio.create_subprocess_exec(
        ffmpeg_path,
        "-y",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(output_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(thumbnail_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await process.wait() != 0:
        raise RuntimeError("ffmpeg thumbnail extraction failed")
    return thumbnail_path


@dataclass
class ClipSpec:
    start_seconds: float
    length_seconds: float


def compute_clip_specs(duration_seconds: float) -> list[ClipSpec]:
    """Up to 10 clips, 1.5s each, one starting at each even 10%-of-duration mark (FR-005);
    reduced so none overlap and none run past the video's end (FR-006) -- `N` clips spaced
    `duration_seconds / N` apart stays evenly spread across the *entire* video even when `N`
    is reduced below 10, rather than just dropping some of the original 10 marks.

    A video shorter than one full clip (FR-009, Edge Cases) falls back to a single clip
    covering its whole duration, not a 1.5s clip that would run past the end.
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if duration_seconds < _CLIP_SECONDS:
        return [ClipSpec(start_seconds=0.0, length_seconds=duration_seconds)]
    count = max(1, min(_MAX_CLIPS, int(duration_seconds // _CLIP_SECONDS)))
    spacing = duration_seconds / count
    return [ClipSpec(start_seconds=i * spacing, length_seconds=_CLIP_SECONDS) for i in range(count)]


async def extract_preview_clips(
    ffmpeg_path: str, output_path: Path, duration_seconds: float
) -> list[Path]:
    """Silent, downscaled H.264 clips (research.md #2) -- browser-`<video>`-playable, unlike
    the graded output's own HEVC/`hvc1` tagging (spec 004), which targets macOS Quick Look,
    not browsers.
    """
    clip_paths = []
    for i, spec in enumerate(compute_clip_specs(duration_seconds)):
        clip_path = output_path.with_name(f"preview-{i}.mp4")
        process = await asyncio.create_subprocess_exec(
            ffmpeg_path,
            "-y",
            "-ss",
            f"{spec.start_seconds:.3f}",
            "-i",
            str(output_path),
            "-t",
            f"{spec.length_seconds:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-an",
            "-vf",
            "scale=480:-2",
            str(clip_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if await process.wait() != 0:
            raise RuntimeError(f"ffmpeg preview clip {i} extraction failed")
        clip_paths.append(clip_path)
    return clip_paths
