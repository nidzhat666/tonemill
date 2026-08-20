from tonemill.logging_config import get_logger
from tonemill.storage.s3_client import S3StorageClient
from tonemill.videos.store import Folder, Video, VideoStore

_logger = get_logger(__name__)


async def relocate_video(
    video: Video,
    target_folder: Folder | None,
    video_store: VideoStore,
    storage: S3StorageClient,
) -> None:
    """Moves one `done` video into `target_folder` (or unsorted, if None) -- re-keys its
    stored object to mirror the target folder using a human-readable name (FR-019,
    research.md #5), updating the `Video` document only once the copy succeeds. Shared by
    `POST /videos/move` and `DELETE /folders/{id}` (which moves every affected video to
    unsorted before deleting the folder) rather than duplicated (DRY).

    A video already in the target folder is a no-op storage-wise; the caller still counts it
    as moved (contracts/api.md).
    """
    target_folder_id = target_folder.id if target_folder else None
    if video.folder_id == target_folder_id:
        return
    assert video.result_key is not None
    assert video.display_name is not None
    folder_slug = _slugify(target_folder.name) if target_folder else "unsorted"
    new_key = f"results/{folder_slug}/{video.display_name}"
    if new_key != video.result_key:
        await storage.copy_object(source_key=video.result_key, dest_key=new_key)
        await storage.delete_object(video.result_key)
    await video_store.update(video.id, folder_id=target_folder_id, result_key=new_key)
    _logger.info("video moved", video_id=video.id, folder_id=target_folder_id, result_key=new_key)


def _slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unsorted"
