import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.collation import Collation
from pymongo.errors import DuplicateKeyError

_VIDEOS_COLLECTION = "videos"
_FOLDERS_COLLECTION = "folders"
_CASE_INSENSITIVE = Collation(locale="en", strength=2)


class VideoStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class Video(BaseModel):
    id: str
    fingerprint: str
    source_key: str
    original_filename: str
    profile: str
    max_quality: bool
    status: VideoStatus = VideoStatus.IN_PROGRESS
    recorded_created_at: datetime | None = None
    display_name: str | None = None
    result_key: str | None = None
    folder_id: str | None = None
    created_at: datetime
    updated_at: datetime


class Folder(BaseModel):
    id: str
    name: str
    created_at: datetime


def _video_from_doc(doc: dict) -> Video:
    return Video(
        id=doc["_id"],
        fingerprint=doc["fingerprint"],
        source_key=doc["source_key"],
        original_filename=doc["original_filename"],
        profile=doc["profile"],
        max_quality=doc["max_quality"],
        status=VideoStatus(doc["status"]),
        recorded_created_at=doc.get("recorded_created_at"),
        display_name=doc.get("display_name"),
        result_key=doc.get("result_key"),
        folder_id=doc.get("folder_id"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _folder_from_doc(doc: dict) -> Folder:
    return Folder(id=doc["_id"], name=doc["name"], created_at=doc["created_at"])


class VideoStore:
    """MongoDB-backed store for `Video` documents (data-model.md) -- created once per job
    submission (status=in_progress) and updated in place as the job resolves/completes/fails.
    Durable, unlike `jobs.store.JobStore`'s TTL-bound Redis hashes (research.md #1): this is
    the source of truth for the video library, folder assignment, and duplicate-fingerprint
    detection, all of which must outlive a job's 24h Redis record.
    """

    def __init__(self, database: AsyncDatabase) -> None:
        self._collection = database[_VIDEOS_COLLECTION]

    async def ensure_indexes(self) -> None:
        """Idempotent -- safe to call from every process that might start first (API, worker).

        The fingerprint index is scoped to `in_progress`/`done` only (data-model.md): a
        `failed` attempt must never block a resubmission (FR-024), so it's deliberately left
        out of the partial filter rather than unique-constrained alongside the others.
        """
        active_statuses = [VideoStatus.IN_PROGRESS, VideoStatus.DONE]
        await self._collection.create_index(
            [("fingerprint", 1), ("profile", 1), ("max_quality", 1)],
            unique=True,
            partialFilterExpression={"status": {"$in": active_statuses}},
        )
        await self._collection.create_index(
            "display_name",
            unique=True,
            partialFilterExpression={"display_name": {"$type": "string"}},
        )
        await self._collection.create_index("folder_id")

    async def create(
        self,
        *,
        video_id: str,
        fingerprint: str,
        source_key: str,
        original_filename: str,
        profile: str,
        max_quality: bool,
    ) -> Video:
        """Raises `pymongo.errors.DuplicateKeyError` if `(fingerprint, profile, max_quality)`
        already matches an `in_progress`/`done` document -- the race-closing half of duplicate
        detection (FR-021, Edge Cases); the caller is expected to translate that into the same
        friendly rejection as the pre-check query (`find_by_fingerprint`).
        """
        now = datetime.now(UTC)
        doc = {
            "_id": video_id,
            "fingerprint": fingerprint,
            "source_key": source_key,
            "original_filename": original_filename,
            "profile": profile,
            "max_quality": max_quality,
            "status": VideoStatus.IN_PROGRESS.value,
            "recorded_created_at": None,
            "display_name": None,
            "result_key": None,
            "folder_id": None,
            "created_at": now,
            "updated_at": now,
        }
        await self._collection.insert_one(doc)
        return _video_from_doc(doc)

    async def get(self, video_id: str) -> Video | None:
        doc = await self._collection.find_one({"_id": video_id})
        return _video_from_doc(doc) if doc else None

    async def update(self, video_id: str, **fields: object) -> Video:
        """Generic `$set` update, mirroring `JobStore.update`'s shape. Raises
        `pymongo.errors.DuplicateKeyError` if a changed `display_name` collides with another
        document (FR-018) -- callers that set `display_name` are expected to retry with a
        disambiguating suffix on that error.
        """
        values = dict(fields)
        if "status" in values and isinstance(values["status"], VideoStatus):
            values["status"] = values["status"].value
        values["updated_at"] = datetime.now(UTC)
        doc = await self._collection.find_one_and_update(
            {"_id": video_id}, {"$set": values}, return_document=ReturnDocument.AFTER
        )
        if doc is None:
            raise VideoNotFoundError(video_id)
        return _video_from_doc(doc)

    async def list_all(self, *, status: VideoStatus | None = None) -> list[Video]:
        query = {} if status is None else {"status": status.value}
        cursor = self._collection.find(query).sort("created_at", -1)
        return [_video_from_doc(doc) async for doc in cursor]

    async def find_by_fingerprint(
        self, *, fingerprint: str, profile: str, max_quality: bool
    ) -> Video | None:
        """Pre-check used by the duplicate-rejection path (FR-021-FR-025) -- scoped to the
        same `in_progress`/`done` statuses as the unique index (research.md #3), so a failed
        prior attempt never blocks a resubmission.
        """
        doc = await self._collection.find_one(
            {
                "fingerprint": fingerprint,
                "profile": profile,
                "max_quality": max_quality,
                "status": {"$in": [VideoStatus.IN_PROGRESS.value, VideoStatus.DONE.value]},
            }
        )
        return _video_from_doc(doc) if doc else None


class VideoNotFoundError(Exception):
    """Raised when a `Video` document's `_id` doesn't exist -- never created, or deleted."""


class FolderNameConflictError(Exception):
    """Raised when a folder name already exists (case-insensitively)."""


class FolderNotFoundError(Exception):
    """Raised when a folder's `_id` doesn't exist -- never created, or already deleted."""


class FolderStore:
    """MongoDB-backed store for `Folder` documents (data-model.md) -- flat containers users
    create within the video library (FR-008, FR-009).
    """

    def __init__(self, database: AsyncDatabase) -> None:
        self._collection = database[_FOLDERS_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("name", unique=True, collation=_CASE_INSENSITIVE)

    async def create(self, *, name: str) -> Folder:
        doc = {"_id": str(uuid.uuid4()), "name": name, "created_at": datetime.now(UTC)}
        try:
            await self._collection.insert_one(doc)
        except DuplicateKeyError as exc:
            raise FolderNameConflictError(name) from exc
        return _folder_from_doc(doc)

    async def get(self, folder_id: str) -> Folder | None:
        doc = await self._collection.find_one({"_id": folder_id})
        return _folder_from_doc(doc) if doc else None

    async def list_all(self) -> list[Folder]:
        cursor = self._collection.find().sort("created_at", 1)
        return [_folder_from_doc(doc) async for doc in cursor]

    async def delete(self, folder_id: str) -> None:
        result = await self._collection.delete_one({"_id": folder_id})
        if result.deleted_count == 0:
            raise FolderNotFoundError(folder_id)
