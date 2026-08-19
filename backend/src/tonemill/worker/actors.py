import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from tonemill.config import get_settings
from tonemill.logging_config import configure_logging
from tonemill.worker.pipeline import run_job

configure_logging()

_settings = get_settings()
_broker = RedisBroker(url=_settings.redis_url)
dramatiq.set_broker(_broker)


@dramatiq.actor(max_retries=0)
def grade_video(job_id: str) -> None:
    """Dispatches each submitted job to the async pipeline (FR-003). Dramatiq's worker
    threads call actors synchronously and never await a returned coroutine, so `run_job`
    (I/O-bound: storage, Redis, ffmpeg) is bridged with asyncio.run() rather than declared
    directly as `async def` here. Concurrency is controlled by `dramatiq --processes N`
    (see docker/worker.Dockerfile), driven by TONEMILL_GPU_CONCURRENCY (FR-018).
    """
    asyncio.run(run_job(job_id))
