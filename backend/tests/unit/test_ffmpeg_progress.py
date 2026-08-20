import asyncio

import pytest

from tonemill.progress.ffmpeg_progress import iter_progress_percent


def _stream_from_lines(lines: list[str]) -> asyncio.StreamReader:
    stream = asyncio.StreamReader()
    stream.feed_data(("\n".join(lines) + "\n").encode())
    stream.feed_eof()
    return stream


async def test_uses_out_time_us_not_out_time_ms():
    # Given ffmpeg's real output, where out_time_ms is actually microseconds (confirmed on
    # real output, research.md #12) and prints the same raw number as out_time_us
    stream = _stream_from_lines(["out_time_us=5000000", "out_time_ms=5000000", "progress=continue"])

    # When computing percentage against a real 20-second (20000ms) duration
    percents = [p async for p in iter_progress_percent(stream, duration_ms=20_000)]

    # Then it's 25% (5s / 20s) -- not ~25000% from misreading the misleadingly-named field
    assert percents == [25.0]


async def test_progress_end_yields_100():
    # Given a stream that reaches the end marker
    stream = _stream_from_lines(["out_time_us=1000000", "progress=continue", "progress=end"])

    # When iterating
    percents = [p async for p in iter_progress_percent(stream, duration_ms=10_000)]

    # Then the final yielded value is exactly 100.0, and iteration stops there
    assert percents[-1] == 100.0


async def test_clamps_to_99_9_before_end():
    # Given out_time_us that would compute to over 100% (e.g. ffmpeg overshoots slightly)
    stream = _stream_from_lines(["out_time_us=21000000", "progress=continue"])

    # When computing percentage against a 20-second duration
    percents = [p async for p in iter_progress_percent(stream, duration_ms=20_000)]

    # Then it's capped at 99.9, never shown as done before progress=end says so
    assert percents == [99.9]


async def test_rejects_non_positive_duration():
    stream = _stream_from_lines(["progress=end"])

    with pytest.raises(ValueError, match="duration_ms must be positive"):
        async for _ in iter_progress_percent(stream, duration_ms=0):
            pass
