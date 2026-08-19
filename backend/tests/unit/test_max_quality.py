from pathlib import Path

from tonemill.config import Settings
from tonemill.profiles.hlg_cpu import HlgCpuProfile
from tonemill.profiles.hlg_gpu import HlgGpuProfile


def test_max_quality_swaps_cq_value_on_gpu_profile():
    # Given the GPU profile
    profile = HlgGpuProfile(Settings())

    # When building the command with max_quality off vs. on
    default_cmd = profile.build_command(Path("in.mov"), Path("out.mp4"), max_quality=False)
    near_lossless_cmd = profile.build_command(Path("in.mov"), Path("out.mp4"), max_quality=True)

    # Then only the encoder quality value changes -- grading (FR-028) stays identical
    default_cq = default_cmd[default_cmd.index("-cq") + 1]
    near_lossless_cq = near_lossless_cmd[near_lossless_cmd.index("-cq") + 1]
    assert default_cq == "20"
    assert near_lossless_cq == "1"
    assert (
        default_cmd[default_cmd.index("-vf") + 1]
        == near_lossless_cmd[near_lossless_cmd.index("-vf") + 1]
    )


def test_max_quality_is_a_single_pass_not_a_second_encode():
    # Given the GPU profile with max_quality on
    profile = HlgGpuProfile(Settings())

    # When building the command
    cmd = profile.build_command(Path("in.mov"), Path("out.mp4"), max_quality=True)

    # Then it's one ffmpeg invocation, not a second pass over already-encoded output
    assert cmd.count("-i") == 1


def test_cpu_profile_ignores_max_quality_without_error():
    # Given the CPU profile, which has no max_quality equivalent (FR-029 is GPU-only)
    profile = HlgCpuProfile(Settings())

    # When building the command with max_quality on anyway
    cmd = profile.build_command(Path("in.mov"), Path("out.mp4"), max_quality=True)

    # Then it's ignored rather than raising or silently changing quality
    assert "-crf" in cmd
    assert cmd[cmd.index("-crf") + 1] == "20"
