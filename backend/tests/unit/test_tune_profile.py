import numpy as np

from tonemill.tools.tune_profile import Candidate, worst_case_clip_fraction


def test_worst_case_clip_fraction_no_clipping():
    # Given frames with no pixel near the clip level
    frames = np.full((2, 4, 4, 3), 100, dtype=np.uint8)

    # When measuring worst-case clipping
    # Then it's zero
    assert worst_case_clip_fraction(frames) == 0.0


def test_worst_case_clip_fraction_full_clip_in_one_channel():
    # Given every pixel clipped, but only in the red channel
    frames = np.zeros((1, 2, 2, 3), dtype=np.uint8)
    frames[..., 0] = 255

    # When measuring worst-case clipping
    # Then it reports 100%, driven by that one channel
    assert worst_case_clip_fraction(frames) == 1.0


def test_worst_case_clip_fraction_partial_clip_takes_worst_channel():
    # Given half the pixels clipped, only in the green channel
    frames = np.zeros((1, 1, 4, 3), dtype=np.uint8)
    frames[0, 0, :2, 1] = 255

    # When measuring worst-case clipping
    # Then it reports the worst channel's fraction, not an average across channels
    assert worst_case_clip_fraction(frames) == 0.5


def test_candidate_is_hashable_and_comparable():
    # Given two candidates with identical values
    a = Candidate(1.12, 1.10)
    b = Candidate(1.12, 1.10)

    # Then they compare equal
    assert a == b
