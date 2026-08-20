"""Shared factories the API and worker both use. FastAPI-request-scoped resources (the
aioboto3-backed storage client) live in api/dependencies.py instead -- they need a
Request to resolve, which the worker doesn't have.
"""

from functools import lru_cache

import redis.asyncio as redis
from pymongo import AsyncMongoClient

from tonemill.config import Settings, get_settings
from tonemill.jobs.store import JobStore
from tonemill.profiles.base import GradingProfile
from tonemill.profiles.dlog_m import DLogMProfile
from tonemill.profiles.hlg_cpu import HlgCpuProfile
from tonemill.profiles.hlg_gpu import HlgGpuProfile
from tonemill.profiles.registry import ProfileRegistry
from tonemill.storage.s3_client import UploadSessionStore
from tonemill.videos.store import FolderStore, VideoStore


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@lru_cache
def get_job_store() -> JobStore:
    settings = get_settings()
    return JobStore(get_redis_client(), ttl_seconds=settings.job_ttl_seconds)


@lru_cache
def get_upload_store() -> UploadSessionStore:
    return UploadSessionStore(get_redis_client())


@lru_cache
def get_mongo_client() -> AsyncMongoClient:
    settings = get_settings()
    return AsyncMongoClient(settings.mongo_url)


@lru_cache
def get_video_store() -> VideoStore:
    settings = get_settings()
    return VideoStore(get_mongo_client()[settings.mongo_db])


@lru_cache
def get_folder_store() -> FolderStore:
    settings = get_settings()
    return FolderStore(get_mongo_client()[settings.mongo_db])


def build_registry(settings: Settings) -> ProfileRegistry:
    """Registered once at process startup (FR-035) -- see profiles/registry.py."""
    registry = ProfileRegistry()
    profiles: list[GradingProfile] = [
        HlgGpuProfile(settings),
        HlgCpuProfile(settings),
        DLogMProfile(),
    ]
    for profile in profiles:
        registry.register(profile)
    return registry


@lru_cache
def get_registry() -> ProfileRegistry:
    return build_registry(get_settings())
