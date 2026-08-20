import asyncio
import tempfile
import time
import uuid
from pathlib import Path

import redis.asyncio as redis
import structlog

from tonemill.config import Settings, get_settings
from tonemill.dependencies import build_registry
from tonemill.jobs.store import Job, JobNotFoundError, JobStage, JobStatus, JobStore
from tonemill.logging_config import get_logger
from tonemill.profiles.base import GradingProfile
from tonemill.profiles.registry import ProfileRegistry, resolve_auto
from tonemill.progress.ffmpeg_progress import iter_progress_percent, probe_duration_ms
from tonemill.storage.s3_client import S3StorageClient, open_storage_client

_PROGRESS_UPDATE_INTERVAL_SECONDS = 1.5
_logger = get_logger(__name__)


async def _resolve_profile(requested_profile: str, registry: ProfileRegistry) -> GradingProfile:
    if requested_profile == "auto":
        return await resolve_auto(registry)
    return registry.get(requested_profile)


async def _fail(job_store: JobStore, job_id: str, message: str) -> None:
    _logger.warning("job failed", reason=message)
    await job_store.update(job_id, status=JobStatus.FAILED, error=message)


async def _reject_if_unrunnable(
    job_store: JobStore, job_id: str, job: Job, profile: GradingProfile
) -> bool:
    """Fails the job and returns True if the resolved profile can't actually run it:
    unavailable on this host (FR-013), or max_quality-incompatible (FR-029). Neither is
    silently substituted or downgraded.
    """
    if not await profile.is_available():
        await _fail(job_store, job_id, f"profile '{profile.name}' is not available")
        return True
    if job.max_quality and profile.execution_path != "gpu":
        await _fail(job_store, job_id, "max_quality requires a GPU-accelerated profile")
        return True
    return False


async def _grade(
    job_store: JobStore,
    storage: S3StorageClient,
    settings: Settings,
    job_id: str,
    source_key: str,
    profile: GradingProfile,
    max_quality: bool,
) -> None:
    """Downloads the source, runs the profile's ffmpeg command with live progress, and
    uploads the result -- the part of run_job that touches the filesystem/subprocess.
    """
    with tempfile.TemporaryDirectory(prefix="tonemill-") as tmpdir:
        source_path = Path(tmpdir) / "source"
        output_path = Path(tmpdir) / "output.mp4"

        try:
            await storage.download_file(source_key, str(source_path))
        except Exception as exc:  # noqa: BLE001 - surface any storage failure as job failure
            await _fail(job_store, job_id, f"download failed: {exc}")
            return

        try:
            duration_ms = await probe_duration_ms(settings.ffprobe_path, str(source_path))
        except Exception as exc:  # noqa: BLE001
            await _fail(job_store, job_id, f"could not probe source: {exc}")
            return
        if duration_ms <= 0:
            await _fail(job_store, job_id, "source has zero or unmeasurable duration")
            return

        await job_store.update(job_id, stage=JobStage.PROCESSING, progress_pct=0.0)

        command = await profile.build_command(source_path, output_path, max_quality=max_quality)
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        if process.stdout is None:
            await _fail(job_store, job_id, "ffmpeg process has no stdout pipe")
            return

        last_update = 0.0
        async for pct in iter_progress_percent(process.stdout, duration_ms):
            now = time.monotonic()
            if now - last_update >= _PROGRESS_UPDATE_INTERVAL_SECONDS or pct >= 100.0:
                await job_store.update(job_id, progress_pct=pct)
                last_update = now
        returncode = await process.wait()

        if returncode != 0:
            await _fail(job_store, job_id, f"ffmpeg exited with code {returncode}")
            return

        await job_store.update(job_id, stage=JobStage.UPLOADING_RESULT, progress_pct=100.0)

        result_key = f"results/{job_id}/{uuid.uuid4()}.mp4"
        try:
            await storage.upload_file(str(output_path), result_key)
        except Exception as exc:  # noqa: BLE001
            await _fail(job_store, job_id, f"result upload failed: {exc}")
            return

        await job_store.update(
            job_id, status=JobStatus.DONE, stage=None, result_key=result_key, progress_pct=100.0
        )
        _logger.info("job done", result_key=result_key)


async def run_job(job_id: str) -> None:
    """Entry point for one job: resolve its profile, then download/grade/upload (FR-003).

    A job whose Redis record expires mid-run (JobNotFoundError) is logged and left alone --
    there's nothing meaningful left to report to, and the client already sees it as expired.
    """
    settings = get_settings()
    registry = build_registry(settings)

    with structlog.contextvars.bound_contextvars(job_id=job_id):
        try:
            async with open_storage_client(settings) as storage:
                job_store = JobStore(
                    redis.Redis.from_url(settings.redis_url, decode_responses=True),
                    ttl_seconds=settings.job_ttl_seconds,
                )
                job = await job_store.get(job_id)
                if job is None:
                    _logger.warning("job expired/unknown before pickup")
                    return

                _logger.info(
                    "job picked up",
                    requested_profile=job.requested_profile,
                    max_quality=job.max_quality,
                )

                try:
                    profile = await _resolve_profile(job.requested_profile, registry)
                except RuntimeError as exc:
                    await _fail(job_store, job_id, str(exc))
                    return

                await job_store.update(job_id, resolved_profile=profile.name)
                if await _reject_if_unrunnable(job_store, job_id, job, profile):
                    return

                await job_store.update(job_id, status=JobStatus.RUNNING, stage=JobStage.DOWNLOADING)
                await _grade(
                    job_store, storage, settings, job_id, job.source_key, profile, job.max_quality
                )
        except JobNotFoundError:
            _logger.warning("job record expired mid-run")
