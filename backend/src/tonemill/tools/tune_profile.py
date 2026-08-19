"""Measurement-based grading-parameter tuning tool (FR-017).

Sweeps candidate contrast/saturation values for a color-transform filter chain across
multiple reference scenes, measures worst-case highlight/channel clipping per candidate
(the % of sampled pixels, in the worst-performing color channel, that are at or above a
near-max threshold), and reports the highest candidate value where the worst scene across
all reference clips stays under the clipping threshold.

This is the tool the hlg-gpu profile's contrast=1.12/saturation=1.10 values (FR-009,
FR-011) were originally derived with -- run it, don't guess, whenever a profile's cosmetic
parameters need validating or re-tuning (dev-only; not installed in API/worker images).

Usage:
    uv run python -m tonemill.tools.tune_profile \\
        --filter-template "eq=contrast={contrast}:saturation={saturation}" \\
        --scene overcast_road.mp4 --scene bright_sky_sea.mp4 \\
        --scene dusk_people.mp4 --scene white_rooftops.mp4 \\
        --contrast 1.06,1.08,1.10,1.12,1.14,1.16 \\
        --saturation 1.10 \\
        --clip-threshold 0.003
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass
from itertools import product

import numpy as np

_CLIP_LEVEL_8BIT = 254  # near-max (of 255); "highlight/channel clipping" per spec wording.
_SAMPLE_FPS = 1  # sampling rate for frame extraction -- enough for a stable estimate, fast.


@dataclass(frozen=True)
class Candidate:
    contrast: float
    saturation: float


def _probe_dimensions(ffprobe_path: str, video_path: str) -> tuple[int, int]:
    result = subprocess.run(  # noqa: S603
        [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    width_str, height_str = result.stdout.strip().split("x")
    return int(width_str), int(height_str)


def _extract_frames(
    ffmpeg_path: str, video_path: str, filter_expr: str, width: int, height: int
) -> np.ndarray:
    """Run `filter_expr` over the scene and return sampled frames as (N, H, W, 3) uint8."""
    cmd = [
        ffmpeg_path,
        "-y",
        "-i",
        video_path,
        "-vf",
        f"{filter_expr},fps={_SAMPLE_FPS}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300, check=True)  # noqa: S603
    frame_bytes = width * height * 3
    raw = result.stdout
    usable_len = (len(raw) // frame_bytes) * frame_bytes
    frames = np.frombuffer(raw[:usable_len], dtype=np.uint8).reshape(-1, height, width, 3)
    return frames


def worst_case_clip_fraction(frames: np.ndarray, clip_level: int = _CLIP_LEVEL_8BIT) -> float:
    """Fraction of sampled pixels at/above clip_level, in whichever of R/G/B is worst."""
    per_channel = (frames >= clip_level).mean(axis=(0, 1, 2))
    return float(per_channel.max())


def evaluate_candidate(
    ffmpeg_path: str,
    ffprobe_path: str,
    scenes: list[str],
    filter_template: str,
    candidate: Candidate,
) -> tuple[float, dict[str, float]]:
    """Returns (worst-case clipping fraction across all scenes, per-scene breakdown)."""
    filter_expr = filter_template.format(
        contrast=candidate.contrast, saturation=candidate.saturation
    )
    per_scene: dict[str, float] = {}
    for scene in scenes:
        width, height = _probe_dimensions(ffprobe_path, scene)
        frames = _extract_frames(ffmpeg_path, scene, filter_expr, width, height)
        per_scene[scene] = worst_case_clip_fraction(frames)
    return max(per_scene.values()), per_scene


def find_best_candidate(
    ffmpeg_path: str,
    ffprobe_path: str,
    scenes: list[str],
    filter_template: str,
    contrast_values: list[float],
    saturation_values: list[float],
    clip_threshold: float,
) -> Candidate | None:
    """Sweeps candidates (highest contrast first) and returns the first (highest) one whose
    worst-scene clipping stays under the threshold, or None if every candidate exceeds it.
    """
    candidates = sorted(
        (Candidate(c, s) for c, s in product(contrast_values, saturation_values)),
        key=lambda c: (c.contrast, c.saturation),
        reverse=True,
    )
    for candidate in candidates:
        worst, per_scene = evaluate_candidate(
            ffmpeg_path, ffprobe_path, scenes, filter_template, candidate
        )
        status = "OK" if worst < clip_threshold else "exceeds threshold"
        print(
            f"contrast={candidate.contrast} saturation={candidate.saturation} "
            f"worst-case clipping={worst:.4%} ({status})",
            file=sys.stderr,
        )
        for scene, value in per_scene.items():
            print(f"  {scene}: {value:.4%}", file=sys.stderr)
        if worst < clip_threshold:
            return candidate
    return None


def _parse_float_list(raw: str) -> list[float]:
    return [float(v) for v in raw.split(",")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--filter-template",
        required=True,
        help="ffmpeg -vf expression with {contrast}/{saturation} placeholders, e.g. "
        '"eq=contrast={contrast}:saturation={saturation}"',
    )
    parser.add_argument(
        "--scene", action="append", required=True, dest="scenes", help="path to a reference clip"
    )
    parser.add_argument("--contrast", required=True, type=_parse_float_list)
    parser.add_argument("--saturation", required=True, type=_parse_float_list)
    parser.add_argument("--clip-threshold", type=float, default=0.003)
    parser.add_argument("--ffmpeg-path", default="ffmpeg")
    parser.add_argument("--ffprobe-path", default="ffprobe")
    args = parser.parse_args(argv)

    if len(args.scenes) < 2:
        print(
            "warning: tuning against fewer than 2 reference scenes is not representative",
            file=sys.stderr,
        )

    best = find_best_candidate(
        args.ffmpeg_path,
        args.ffprobe_path,
        args.scenes,
        args.filter_template,
        args.contrast,
        args.saturation,
        args.clip_threshold,
    )
    if best is None:
        print("No candidate stayed under the clipping threshold.", file=sys.stderr)
        return 1

    print(f"Best candidate: contrast={best.contrast} saturation={best.saturation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
