from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from tonemill.api.dependencies import get_storage_client
from tonemill.dependencies import get_job_store, get_registry, get_video_store
from tonemill.jobs.store import Job, JobNotDismissableError, JobNotFoundError, JobStatus, JobStore
from tonemill.logging_config import get_logger
from tonemill.profiles.registry import ProfileRegistry
from tonemill.storage.s3_client import S3StorageClient
from tonemill.videos.fingerprint import compute_fingerprint
from tonemill.videos.store import VideoStore
from tonemill.worker.actors import grade_video

router = APIRouter(tags=["jobs"])
_logger = get_logger(__name__)


class SubmitJobRequest(BaseModel):
    s3_key: str
    profile: str = "auto"
    max_quality: bool = False


class SubmitJobResponse(BaseModel):
    job_id: str
    status: str


class ProfileInfo(BaseModel):
    name: str
    source_format: str
    execution_path: str | None
    implemented: bool


class JobStatusResponse(BaseModel):
    job_id: str
    source_key: str
    status: str
    stage: str | None
    progress_pct: float
    requested_profile: str
    resolved_profile: str | None
    max_quality: bool
    result_url: str | None
    error: str | None


class DismissAllResponse(BaseModel):
    dismissed: int


@router.get("/profiles", response_model=list[ProfileInfo])
async def list_profiles(
    registry: Annotated[ProfileRegistry, Depends(get_registry)],
) -> list[ProfileInfo]:
    return [
        ProfileInfo(
            name=p.name,
            source_format=p.source_format,
            execution_path=p.execution_path if p.implemented else None,
            implemented=p.implemented,
        )
        for p in registry.list()
    ]


def _validate_explicit_profile(
    registry: ProfileRegistry, profile_name: str, *, max_quality: bool
) -> None:
    """Rejects an explicit (non-"auto") profile name that's unknown, not-yet-implemented, or
    structurally incompatible with max_quality -- the latter is knowable from registry
    metadata alone (FR-029), no runtime GPU/ffmpeg check needed.
    """
    if not registry.exists(profile_name):
        raise HTTPException(status_code=400, detail=f"unknown profile: {profile_name}")
    profile = registry.get(profile_name)
    if not profile.implemented:
        raise HTTPException(
            status_code=409, detail=f"profile '{profile_name}' is not yet implemented"
        )
    if max_quality and profile.execution_path != "gpu":
        raise HTTPException(
            status_code=400,
            detail=(
                f"max_quality requires a GPU-accelerated profile; "
                f"'{profile_name}' is {profile.execution_path}-only"
            ),
        )


def _original_filename(s3_key: str) -> str:
    """`sources/{uuid}/{original filename}` (uploads.py's `_safe_key`) -- the trailing
    segment is the part worth keeping for reference; the uuid directory exists purely to
    avoid same-name collisions across uploads and isn't itself meaningful.
    """
    return s3_key.rsplit("/", 1)[-1]


def _duplicate_detail(profile: str) -> str:
    return f'This file was already processed with the "{profile}" profile.'


@router.post("/jobs", response_model=SubmitJobResponse, status_code=201)
async def submit_job(
    body: SubmitJobRequest,
    job_store: Annotated[JobStore, Depends(get_job_store)],
    registry: Annotated[ProfileRegistry, Depends(get_registry)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    video_store: Annotated[VideoStore, Depends(get_video_store)],
) -> SubmitJobResponse:
    if not await storage.object_exists(body.s3_key):
        raise HTTPException(status_code=400, detail="s3_key does not reference a completed upload")

    if body.profile != "auto":
        _validate_explicit_profile(registry, body.profile, max_quality=body.max_quality)

    fingerprint = await compute_fingerprint(storage, body.s3_key)

    duplicate = await video_store.find_by_fingerprint(
        fingerprint=fingerprint, profile=body.profile, max_quality=body.max_quality
    )
    if duplicate is not None:
        _logger.info("duplicate submission rejected", profile=body.profile, s3_key=body.s3_key)
        raise HTTPException(status_code=409, detail=_duplicate_detail(body.profile))

    job = await job_store.create(
        source_key=body.s3_key, requested_profile=body.profile, max_quality=body.max_quality
    )
    try:
        await video_store.create(
            video_id=job.job_id,
            fingerprint=fingerprint,
            source_key=body.s3_key,
            original_filename=_original_filename(body.s3_key),
            profile=body.profile,
            max_quality=body.max_quality,
        )
    except DuplicateKeyError as exc:
        # Closes the race between two near-simultaneous submissions of the same file: both
        # could pass the find_by_fingerprint pre-check above before either's insert lands.
        # The Job record already exists at this point (Job/Video share an id, created in that
        # order) -- fail it explicitly rather than leaving an orphaned "queued" job that a
        # worker will never pick up (no grade_video.send() below this point).
        detail = _duplicate_detail(body.profile)
        await job_store.update(job.job_id, status=JobStatus.FAILED, error=detail)
        _logger.info("duplicate submission rejected (race)", profile=body.profile)
        raise HTTPException(status_code=409, detail=detail) from exc
    _logger.info("video created", video_id=job.job_id, profile=body.profile)
    grade_video.send(job.job_id)

    return SubmitJobResponse(job_id=job.job_id, status=job.status.value)


async def _to_status_response(job: Job, storage: S3StorageClient) -> JobStatusResponse:
    result_url = await storage.presign_get_object(job.result_key) if job.result_key else None
    return JobStatusResponse(
        job_id=job.job_id,
        source_key=job.source_key,
        status=job.status.value,
        stage=job.stage.value if job.stage else None,
        progress_pct=job.progress_pct,
        requested_profile=job.requested_profile,
        resolved_profile=job.resolved_profile,
        max_quality=job.max_quality,
        result_url=result_url,
        error=job.error,
    )


@router.get("/jobs", response_model=list[JobStatusResponse])
async def list_jobs(
    job_store: Annotated[JobStore, Depends(get_job_store)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> list[JobStatusResponse]:
    jobs = await job_store.list_all()
    return [await _to_status_response(job, storage) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    job_store: Annotated[JobStore, Depends(get_job_store)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> JobStatusResponse:
    job = await job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found or expired")
    return await _to_status_response(job, storage)


@router.post("/jobs/{job_id}/dismiss", status_code=204)
async def dismiss_job(
    job_id: str,
    job_store: Annotated[JobStore, Depends(get_job_store)],
) -> None:
    try:
        await job_store.dismiss(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="job not found or expired") from exc
    except JobNotDismissableError as exc:
        raise HTTPException(status_code=409, detail="job is still in progress") from exc
    _logger.info("job dismissed", job_id=job_id)


@router.post("/jobs/dismiss-all", response_model=DismissAllResponse)
async def dismiss_all_jobs(
    job_store: Annotated[JobStore, Depends(get_job_store)],
) -> DismissAllResponse:
    dismissed = await job_store.dismiss_all()
    _logger.info("jobs dismissed", count=dismissed)
    return DismissAllResponse(dismissed=dismissed)
