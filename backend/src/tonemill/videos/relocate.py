from tonemill.logging_config import get_logger
from tonemill.videos.store import Video, VideoStore

_logger = get_logger(__name__)


async def relocate_video(
    video: Video, target_folder_id: str | None, video_store: VideoStore
) -> None:
    """Moves one `done` video into `target_folder_id` (or unsorted, if None). Folder
    organization is a `Video.folder_id` update only -- the object's storage key never changes
    (it's a permanent, opaque `results/{job_id}/{uuid}.mp4`, set once at grading time), so a
    move is a single cheap Mongo write, not an S3 copy+delete. Shared by `POST /videos/move`
    and `DELETE /folders/{id}` (which moves every affected video to unsorted before deleting
    the folder) rather than duplicated (DRY).

    A video already in the target folder is a no-op; the caller still counts it as moved
    (contracts/api.md).
    """
    if video.folder_id == target_folder_id:
        return
    await video_store.update(video.id, folder_id=target_folder_id)
    _logger.info("video moved", video_id=video.id, folder_id=target_folder_id)
