from datetime import datetime


def make_display_name(recorded_created_at: datetime, profile: str, *, attempt: int = 0) -> str:
    """`<recording date>_<profile>.mp4` (FR-016). `attempt` disambiguates a name collision
    (FR-018, research.md #4) -- the caller retries with an incrementing `attempt` on a
    `VideoStore` uniqueness conflict; `attempt=0` is the plain, unsuffixed name.
    """
    base = f"{recorded_created_at:%Y-%m-%d_%H-%M-%S}_{profile}"
    if attempt > 0:
        base = f"{base}-{attempt + 1}"
    return f"{base}.mp4"
