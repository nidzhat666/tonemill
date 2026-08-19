import shutil

import pytest

from tonemill.profiles.registry import detect_gpu_encoder_available

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs real ffmpeg")


@requires_ffmpeg
async def test_reports_unavailable_for_an_unknown_encoder_name():
    # Given an encoder name that doesn't exist in any ffmpeg build
    # When checking availability
    # Then it's reported unavailable rather than raising
    assert await detect_gpu_encoder_available("ffmpeg", "not-a-real-encoder") is False


@requires_ffmpeg
async def test_reports_available_for_an_encoder_that_can_genuinely_initialize():
    # Given a software encoder every ffmpeg build actually supports (no GPU/driver needed)
    # When checking availability
    # Then it's reported available -- this is the "genuinely usable" case, not just
    # "listed in -encoders" (see detect_gpu_encoder_available's docstring for why that
    # distinction matters: it's what caused auto to wrongly pick hlg-gpu on a non-GPU host)
    assert await detect_gpu_encoder_available("ffmpeg", "libx264") is True
