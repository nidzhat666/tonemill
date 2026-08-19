"""D-Log M profile: known future need, registered so clients get a clear "not implemented"
response (FR-015), but its actual grading pipeline is explicitly out of scope for v1.
"""

from tonemill.profiles.base import NotImplementedProfile


class DLogMProfile(NotImplementedProfile):
    name = "d-log-m"
    source_format = "D-Log M"
