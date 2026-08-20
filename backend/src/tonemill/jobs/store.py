import uuid
from datetime import UTC, datetime
from enum import StrEnum

import redis.asyncio as redis
from pydantic import BaseModel

from tonemill.redis_utils import hgetall_str, hset_on_pipeline

_KEY_PREFIX = "tonemill:job:"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStage(StrEnum):
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING_RESULT = "uploading_result"


class Job(BaseModel):
    job_id: str
    source_key: str
    requested_profile: str
    resolved_profile: str | None = None
    max_quality: bool = False
    status: JobStatus = JobStatus.QUEUED
    stage: JobStage | None = None
    progress_pct: float = 0.0
    result_key: str | None = None
    error: str | None = None
    created_at: datetime
    dismissed: bool = False


class JobNotFoundError(Exception):
    """Raised when a job's Redis record is missing -- never created, or its TTL expired."""


class JobNotDismissableError(Exception):
    """Raised when dismissing a job still `queued`/`running` (FR-004's "in progress" jobs
    can't be dismissed, individually or via "Dismiss all").
    """


_DISMISSABLE_STATUSES = frozenset({JobStatus.DONE, JobStatus.FAILED})


def _to_hash(job: Job) -> dict[str, str]:
    """Flatten a Job into Redis-hash-safe string fields (empty string means "unset")."""
    return {
        "job_id": job.job_id,
        "source_key": job.source_key,
        "requested_profile": job.requested_profile,
        "resolved_profile": job.resolved_profile or "",
        "max_quality": "1" if job.max_quality else "0",
        "status": job.status.value,
        "stage": job.stage.value if job.stage else "",
        "progress_pct": str(job.progress_pct),
        "result_key": job.result_key or "",
        "error": job.error or "",
        "created_at": job.created_at.isoformat(),
        "dismissed": "1" if job.dismissed else "0",
    }


def _from_hash(data: dict[str, str]) -> Job:
    return Job(
        job_id=data["job_id"],
        source_key=data["source_key"],
        requested_profile=data["requested_profile"],
        resolved_profile=data["resolved_profile"] or None,
        max_quality=data["max_quality"] == "1",
        status=JobStatus(data["status"]),
        stage=JobStage(data["stage"]) if data["stage"] else None,
        progress_pct=float(data["progress_pct"]),
        result_key=data["result_key"] or None,
        error=data["error"] or None,
        created_at=datetime.fromisoformat(data["created_at"]),
        dismissed=data.get("dismissed") == "1",
    )


class JobStore:
    """Redis-backed job state (FR-004, FR-005, FR-007, FR-019, FR-033). One hash per job;
    TTL is (re-)applied on every write, so a job's record survives as long as it's actively
    updated and then counts down from its last update, not from creation.
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    def _key(self, job_id: str) -> str:
        return f"{_KEY_PREFIX}{job_id}"

    async def create(self, *, source_key: str, requested_profile: str, max_quality: bool) -> Job:
        job = Job(
            job_id=str(uuid.uuid4()),
            source_key=source_key,
            requested_profile=requested_profile,
            max_quality=max_quality,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        await self._write(job)
        return job

    async def get(self, job_id: str) -> Job | None:
        data = await hgetall_str(self._redis, self._key(job_id))
        if not data:
            return None
        return _from_hash(data)

    async def list_all(self, *, include_dismissed: bool = False) -> list[Job]:
        """Every non-expired job in Redis, newest first -- not scoped to any one client.
        Excludes dismissed jobs by default (FR-002-FR-006): dismissal is applied here, not
        left for callers to filter.
        """
        jobs: list[Job] = []
        async for key in self._redis.scan_iter(match=f"{_KEY_PREFIX}*"):
            data = await hgetall_str(self._redis, key)
            if data:
                jobs.append(_from_hash(data))
        if not include_dismissed:
            jobs = [job for job in jobs if not job.dismissed]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs

    async def update(self, job_id: str, **fields: object) -> Job:
        job = await self.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        updated = job.model_copy(update=fields)
        await self._write(updated)
        return updated

    async def dismiss(self, job_id: str) -> Job:
        job = await self.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status not in _DISMISSABLE_STATUSES:
            raise JobNotDismissableError(job_id)
        return await self.update(job_id, dismissed=True)

    async def dismiss_all(self) -> int:
        """Dismisses every `done`/`failed`, not-yet-dismissed job (FR-003). Returns the count
        actually dismissed -- 0 when there's nothing eligible, never an error.
        """
        eligible = [
            job
            for job in await self.list_all(include_dismissed=True)
            if not job.dismissed and job.status in _DISMISSABLE_STATUSES
        ]
        for job in eligible:
            await self.update(job.job_id, dismissed=True)
        return len(eligible)

    async def _write(self, job: Job) -> None:
        key = self._key(job.job_id)
        pipeline = self._redis.pipeline()
        hset_on_pipeline(pipeline, key, _to_hash(job))
        pipeline.expire(key, self._ttl_seconds)
        await pipeline.execute()
