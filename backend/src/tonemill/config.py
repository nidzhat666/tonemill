from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env-driven settings. All TONEMILL_* env vars; see docker-compose*.yml for defaults."""

    model_config = SettingsConfigDict(env_prefix="TONEMILL_")

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str | None = Field(
        default=None,
        description=(
            "Internal endpoint for every direct API<->storage call (create/complete/abort/"
            "list/head/upload/download). In Docker this is typically an internal service DNS"
            " name (e.g. http://minio:9000) that only resolves inside the compose network."
        ),
    )
    s3_public_endpoint_url: str | None = Field(
        default=None,
        description=(
            "Endpoint baked into presigned URLs (upload parts, result downloads), which a"
            " browser outside the Docker network must be able to resolve directly. Falls"
            " back to s3_endpoint_url when unset -- correct for real AWS S3 (one endpoint),"
            " but MUST be overridden for local MinIO (see docker-compose.dev.yml, where the"
            " internal name is http://minio:9000 but the browser needs http://localhost:9000)."
        ),
    )
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str = "tonemill"
    s3_region: str = "us-east-1"

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"

    gpu_concurrency: int = Field(
        default=1,
        description=(
            "GPU worker concurrency (FR-018): default 1, at most 2, per GPU. A single GPU"
            " saturates almost immediately on this workload (~8% gain from 1->6 concurrent"
            " jobs) -- scale by adding GPU hosts, not raising this value."
        ),
    )
    job_ttl_seconds: int = Field(
        default=86400, description="Job/upload-session record retention (FR-019)."
    )
    presigned_url_ttl_seconds: int = Field(
        default=3600, description="Lifetime of presigned upload-part and result-download URLs."
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
