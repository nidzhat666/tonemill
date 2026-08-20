from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tonemill.api.dependencies import get_storage_client
from tonemill.dependencies import get_folder_store, get_video_store
from tonemill.storage.s3_client import S3StorageClient
from tonemill.videos.relocate import relocate_video
from tonemill.videos.store import Folder, FolderStore, Video, VideoStatus, VideoStore

router = APIRouter(prefix="/videos", tags=["videos"])


class VideoResponse(BaseModel):
    video_id: str
    display_name: str
    profile: str
    recorded_created_at: datetime
    folder_id: str | None
    result_url: str


class MoveVideosRequest(BaseModel):
    video_ids: list[str]
    folder_id: str | None = None


class MoveVideosResponse(BaseModel):
    moved: int


async def _to_video_response(video: Video, storage: S3StorageClient) -> VideoResponse:
    """Only ever called for `status=done` videos (FR-007) -- `display_name`/`result_key`/
    `recorded_created_at` are guaranteed set by that point (data-model.md).
    """
    assert video.display_name is not None
    assert video.result_key is not None
    assert video.recorded_created_at is not None
    return VideoResponse(
        video_id=video.id,
        display_name=video.display_name,
        profile=video.profile,
        recorded_created_at=video.recorded_created_at,
        folder_id=video.folder_id,
        result_url=await storage.presign_get_object(video.result_key),
    )


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    video_store: Annotated[VideoStore, Depends(get_video_store)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> list[VideoResponse]:
    videos = await video_store.list_all(status=VideoStatus.DONE)
    return [await _to_video_response(video, storage) for video in videos]


@router.post("/move", response_model=MoveVideosResponse)
async def move_videos(
    body: MoveVideosRequest,
    video_store: Annotated[VideoStore, Depends(get_video_store)],
    folder_store: Annotated[FolderStore, Depends(get_folder_store)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> MoveVideosResponse:
    target_folder: Folder | None = None
    if body.folder_id is not None:
        target_folder = await folder_store.get(body.folder_id)
        if target_folder is None:
            raise HTTPException(status_code=404, detail="folder not found")

    moved = 0
    for video_id in body.video_ids:
        video = await video_store.get(video_id)
        if video is None:
            continue
        await relocate_video(video, target_folder, video_store, storage)
        moved += 1
    return MoveVideosResponse(moved=moved)
