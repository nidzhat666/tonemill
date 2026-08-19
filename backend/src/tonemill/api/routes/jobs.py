from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tonemill.api.dependencies import get_storage_client
from tonemill.dependencies import get_job_store, get_registry
from tonemill.jobs.store import Job, JobStore
from tonemill.profiles.registry import ProfileRegistry
from tonemill.storage.s3_client import S3StorageClient
from tonemill.worker.actors import grade_video

router = APIRouter(tags=["jobs"])


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


@router.post("/jobs", response_model=SubmitJobResponse, status_code=201)
async def submit_job(
    body: SubmitJobRequest,
    job_store: Annotated[JobStore, Depends(get_job_store)],
    registry: Annotated[ProfileRegistry, Depends(get_registry)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> SubmitJobResponse:
    if not await storage.object_exists(body.s3_key):
        raise HTTPException(status_code=400, detail="s3_key does not reference a completed upload")

    if body.profile != "auto":
        _validate_explicit_profile(registry, body.profile, max_quality=body.max_quality)

    job = await job_store.create(
        source_key=body.s3_key, requested_profile=body.profile, max_quality=body.max_quality
    )
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
