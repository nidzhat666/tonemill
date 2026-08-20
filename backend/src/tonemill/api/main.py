from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from tonemill.api.routes.folders import router as folders_router
from tonemill.api.routes.jobs import router as jobs_router
from tonemill.api.routes.uploads import router as uploads_router
from tonemill.api.routes.videos import router as videos_router
from tonemill.config import get_settings
from tonemill.dependencies import get_folder_store, get_video_store
from tonemill.logging_config import configure_logging, get_logger
from tonemill.profiles.registry import UnknownProfileError
from tonemill.storage.s3_client import open_storage_client

configure_logging()
_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with open_storage_client(get_settings()) as storage_client:
        app.state.storage_client = storage_client
        await get_video_store().ensure_indexes()
        await get_folder_store().ensure_indexes()
        _logger.info("api starting up")
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="Tonemill API", lifespan=lifespan)

    app.include_router(uploads_router)
    app.include_router(jobs_router)
    app.include_router(videos_router)
    app.include_router(folders_router)

    @app.exception_handler(UnknownProfileError)
    async def _unknown_profile_handler(_: Request, exc: UnknownProfileError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": f"unknown profile: {exc}"})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
