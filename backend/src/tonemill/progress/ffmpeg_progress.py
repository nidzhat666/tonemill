import asyncio
from collections.abc import AsyncIterator


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


async def iter_progress_percent(
    stream: asyncio.StreamReader, duration_ms: int
) -> AsyncIterator[float]:
    """Parse ffmpeg's `-progress pipe:1` machine-readable key=value stream (FR-005) --
    NOT the human-readable stderr status line, per the validated operational constraint.
    Yields a running percentage (0-100) as `out_time_ms=` lines arrive, and yields exactly
    100.0 once when `progress=end` is seen.
    """
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")
    async for raw_line in stream:
        line = raw_line.decode().strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key == "out_time_ms":
            try:
                out_time_ms = int(value)
            except ValueError:
                continue
            yield min(99.9, max(0.0, (out_time_ms / duration_ms) * 100))
        elif key == "progress" and value == "end":
            yield 100.0
            return
