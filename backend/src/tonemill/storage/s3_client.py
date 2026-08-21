from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import aioboto3
import redis.asyncio as redis
from botocore.client import Config as BotoConfig

from tonemill.config import Settings
from tonemill.redis_utils import hgetall_str

_UPLOAD_KEY_PREFIX = "tonemill:upload:"


@dataclass
class Part:
    part_number: int
    etag: str
    size_bytes: int


class S3StorageClient:
    """Presigned + multipart primitives (FR-001, FR-030-FR-032, FR-034). Bytes always flow
    client<->storage directly; this class only mints URLs and relays create/complete/abort
    calls. Two underlying clients are wrapped: one for direct calls (may use an
    internal-only endpoint), one for minting presigned URLs (must use an endpoint the
    end-user's browser can resolve -- see config.py's s3_public_endpoint_url).
    """

    def __init__(self, client, presign_client, bucket: str, presigned_url_ttl_seconds: int) -> None:
        self._client = client
        self._presign_client = presign_client
        self._bucket = bucket
        self._ttl = presigned_url_ttl_seconds

    async def object_exists(self, key: str) -> bool:
        try:
            await self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - boto raises provider-specific ClientError
            return False

    async def create_multipart_upload(self, key: str) -> str:
        resp = await self._client.create_multipart_upload(Bucket=self._bucket, Key=key)
        return resp["UploadId"]

    async def presign_upload_part(self, *, key: str, upload_id: str, part_number: int) -> str:
        return await self._presign_client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=self._ttl,
        )

    async def list_parts(self, *, key: str, upload_id: str) -> list[Part]:
        """Backs GET /uploads/{id}/parts (FR-034) -- S3/MinIO already tracks received parts
        natively, so this is a passthrough rather than duplicated state.
        """
        parts: list[Part] = []
        marker: int | None = None
        while True:
            kwargs = {"Bucket": self._bucket, "Key": key, "UploadId": upload_id}
            if marker is not None:
                kwargs["PartNumberMarker"] = marker
            resp = await self._client.list_parts(**kwargs)
            parts.extend(
                Part(part_number=p["PartNumber"], etag=p["ETag"], size_bytes=p["Size"])
                for p in resp.get("Parts", [])
            )
            if not resp.get("IsTruncated"):
                break
            marker = resp.get("NextPartNumberMarker")
        return parts

    async def complete_multipart_upload(
        self, *, key: str, upload_id: str, parts: list[dict[str, str | int]]
    ) -> None:
        await self._client.complete_multipart_upload(
            Bucket=self._bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    async def abort_multipart_upload(self, *, key: str, upload_id: str) -> None:
        await self._client.abort_multipart_upload(Bucket=self._bucket, Key=key, UploadId=upload_id)

    async def presign_get_object(self, key: str, *, filename: str | None = None) -> str:
        """`filename`, when given, sets the response's `Content-Disposition` so the browser
        saves the download under that readable name (FR-016) regardless of the object's own
        (opaque, permanent) storage key -- no object rename/copy needed to rename a download.
        """
        params: dict[str, str] = {"Bucket": self._bucket, "Key": key}
        if filename is not None:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return await self._presign_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=self._ttl,
        )

    async def download_file(self, key: str, destination: str) -> None:
        await self._client.download_file(self._bucket, key, destination)

    async def upload_file(self, source: str, key: str) -> None:
        await self._client.upload_file(source, self._bucket, key)

    async def delete_object(self, key: str) -> None:
        """Backs permanent video deletion (specs/005-library-tree-thumbnails, FR-021) --
        deleting an already-missing key is not an error (S3/MinIO semantics), which callers
        rely on to tolerate a video missing one of its optional assets (e.g. no thumbnail yet).
        """
        await self._client.delete_object(Bucket=self._bucket, Key=key)

    async def object_size(self, key: str) -> int:
        """Backs the content-fingerprint helper (research.md #3), which needs the object's
        total size before it can compute a "last N bytes" range.
        """
        resp = await self._client.head_object(Bucket=self._bucket, Key=key)
        return resp["ContentLength"]

    async def read_range(self, key: str, *, start: int, end: int) -> bytes:
        """Reads an inclusive byte range `[start, end]` without downloading the whole object
        -- backs the content-fingerprint helper (research.md #3), which only ever needs a
        source's size plus its first/last 1 MiB, regardless of how large the source is.
        """
        resp = await self._client.get_object(
            Bucket=self._bucket, Key=key, Range=f"bytes={start}-{end}"
        )
        return await resp["Body"].read()


@asynccontextmanager
async def open_storage_client(settings: Settings) -> AsyncIterator[S3StorageClient]:
    """Opens the aioboto3 client(s) an S3StorageClient needs and tears them down on exit.
    Used both as a long-lived resource (API, via FastAPI's lifespan) and a short-lived one
    (worker, once per job).
    """
    session = aioboto3.Session()
    config = BotoConfig(signature_version="s3v4")
    async with session.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=config,
    ) as client:
        public_endpoint = settings.s3_public_endpoint_url or settings.s3_endpoint_url
        if public_endpoint == settings.s3_endpoint_url:
            yield S3StorageClient(
                client, client, settings.s3_bucket, settings.presigned_url_ttl_seconds
            )
            return
        async with session.client(
            "s3",
            endpoint_url=public_endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=config,
        ) as presign_client:
            yield S3StorageClient(
                client, presign_client, settings.s3_bucket, settings.presigned_url_ttl_seconds
            )


class UploadSessionState:
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class UploadSessionStore:
    """Maps an upload_id to its target object key and lifecycle state (data-model.md
    "Upload Session"). Per-part tracking is answered live via S3StorageClient.list_parts.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    def _key(self, upload_id: str) -> str:
        return f"{_UPLOAD_KEY_PREFIX}{upload_id}"

    async def create(self, *, upload_id: str, target_key: str) -> None:
        await self._redis.hset(
            self._key(upload_id),
            mapping={
                "upload_id": upload_id,
                "target_key": target_key,
                "state": UploadSessionState.IN_PROGRESS,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    async def get(self, upload_id: str) -> dict[str, str] | None:
        data = await hgetall_str(self._redis, self._key(upload_id))
        return data or None

    async def mark_state(self, upload_id: str, state: str) -> None:
        await self._redis.hset(self._key(upload_id), "state", state)
