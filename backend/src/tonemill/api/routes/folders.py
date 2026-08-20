from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tonemill.api.dependencies import get_storage_client
from tonemill.dependencies import get_folder_store, get_video_store
from tonemill.storage.s3_client import S3StorageClient
from tonemill.videos.relocate import relocate_video
from tonemill.videos.store import (
    FolderNameConflictError,
    FolderNotFoundError,
    FolderStore,
    VideoStatus,
    VideoStore,
)

router = APIRouter(prefix="/folders", tags=["folders"])


class FolderResponse(BaseModel):
    folder_id: str
    name: str
    video_count: int


class CreateFolderRequest(BaseModel):
    name: str


@router.get("", response_model=list[FolderResponse])
async def list_folders(
    folder_store: Annotated[FolderStore, Depends(get_folder_store)],
    video_store: Annotated[VideoStore, Depends(get_video_store)],
) -> list[FolderResponse]:
    folders = await folder_store.list_all()
    videos = await video_store.list_all(status=VideoStatus.DONE)
    counts = Counter(video.folder_id for video in videos if video.folder_id is not None)
    return [
        FolderResponse(folder_id=folder.id, name=folder.name, video_count=counts[folder.id])
        for folder in folders
    ]


@router.post("", response_model=FolderResponse, status_code=201)
async def create_folder(
    body: CreateFolderRequest,
    folder_store: Annotated[FolderStore, Depends(get_folder_store)],
) -> FolderResponse:
    try:
        folder = await folder_store.create(name=body.name)
    except FolderNameConflictError as exc:
        raise HTTPException(
            status_code=409, detail=f"a folder named '{body.name}' already exists"
        ) from exc
    return FolderResponse(folder_id=folder.id, name=folder.name, video_count=0)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    folder_store: Annotated[FolderStore, Depends(get_folder_store)],
    video_store: Annotated[VideoStore, Depends(get_video_store)],
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
) -> None:
    """Every video in the folder is relocated to unsorted (FR-015, FR-019) before the folder
    document itself is removed -- deleting a folder never deletes a video.
    """
    folder = await folder_store.get(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="folder not found")

    videos = await video_store.list_all(status=VideoStatus.DONE)
    for video in videos:
        if video.folder_id == folder_id:
            await relocate_video(video, None, video_store, storage)

    try:
        await folder_store.delete(folder_id)
    except FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="folder not found") from exc
