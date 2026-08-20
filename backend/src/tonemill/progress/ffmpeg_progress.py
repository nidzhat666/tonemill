import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


async def probe_duration_ms(ffprobe_path: str, source_path: str) -> int:
    """Probe the source's duration once, up front -- percentage is out_time_ms / this."""
    process = await asyncio.create_subprocess_exec(
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        source_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe exited with code {process.returncode}")
    return int(float(stdout.decode().strip()) * 1000)


@dataclass
class SourceInfo:
    duration_ms: int
    recorded_created_at: datetime | None


async def probe_source_info(ffprobe_path: str, source_path: str) -> SourceInfo:
    """Probes duration and the source's own recorded creation date in one combined ffprobe
    call (FR-017, research.md #4) -- one source read, not two. `recorded_created_at` is None
    when the source has no `creation_time` tag; the caller falls back to the job's own
    submission time in that case.
    """
    process = await asyncio.create_subprocess_exec(
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration:format_tags=creation_time",
        "-of",
        "json",
        source_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe exited with code {process.returncode}")
    fmt = json.loads(stdout.decode())["format"]
    duration_ms = int(float(fmt["duration"]) * 1000)
    creation_time = fmt.get("tags", {}).get("creation_time")
    return SourceInfo(
        duration_ms=duration_ms,
        recorded_created_at=_parse_creation_time(creation_time) if creation_time else None,
    )


def _parse_creation_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def iter_progress_percent(
    stream: asyncio.StreamReader, duration_ms: int
) -> AsyncIterator[float]:
    """Parse ffmpeg's `-progress pipe:1` machine-readable key=value stream (FR-005) --
    NOT the human-readable stderr status line, per the validated operational constraint.
    Yields a running percentage (0-100) as `out_time_us=` lines arrive, and yields exactly
    100.0 once when `progress=end` is seen.

    Uses `out_time_us`, not `out_time_ms` -- confirmed on real output (research.md #12) that
    ffmpeg's `out_time_ms` field is actually microseconds despite its name (a long-standing
    ffmpeg quirk: both fields print the identical raw number). Dividing that by a true
    milliseconds duration inflated every job to ~100% almost immediately, then held it there
    for the rest of the real run -- invisible on the short clips this was validated against
    (the whole job finished before anyone would notice), only actually visible once real jobs
    started taking minutes (peak_detect=true, research.md #12).
    """
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")
    duration_us = duration_ms * 1000
    async for raw_line in stream:
        line = raw_line.decode().strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key == "out_time_us":
            try:
                out_time_us = int(value)
            except ValueError:
                continue
            yield min(99.9, max(0.0, (out_time_us / duration_us) * 100))
        elif key == "progress" and value == "end":
            yield 100.0
            return
