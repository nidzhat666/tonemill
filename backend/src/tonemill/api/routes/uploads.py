import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tonemill.api.dependencies import get_storage_client
from tonemill.dependencies import get_upload_store
from tonemill.storage.s3_client import S3StorageClient, UploadSessionState, UploadSessionStore

router = APIRouter(prefix="/uploads", tags=["uploads"])

_PART_SIZE_BYTES = 16 * 1024 * 1024  # 16 MiB; S3 multipart parts must be >=5 MiB except the last.


class InitiateUploadRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class InitiateUploadResponse(BaseModel):
    upload_id: str
    s3_key: str
    part_size_bytes: int
    part_count: int


class PartUrlResponse(BaseModel):
    part_number: int
    upload_url: str


class PartInfo(BaseModel):
    part_number: int
    etag: str
    size_bytes: int


class ListPartsResponse(BaseModel):
    parts: list[PartInfo]


class CompletedPart(BaseModel):
    part_number: int
    etag: str


class CompleteUploadRequest(BaseModel):
    parts: list[CompletedPart]


class CompleteUploadResponse(BaseModel):
    s3_key: str
    status: str


def _safe_key(filename: str) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"sources/{uuid.uuid4()}/{safe_name}"


async def _get_session_or_404(store: UploadSessionStore, upload_id: str) -> dict[str, str]:
    session = await store.get(upload_id)
    if session is None:
        raise HTTPException(status_code=404, detail="upload not found")
    return session


@router.post("", response_model=InitiateUploadResponse, status_code=201)
async def initiate_upload(
    body: InitiateUploadRequest,
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    upload_store: Annotated[UploadSessionStore, Depends(get_upload_store)],
) -> InitiateUploadResponse:
    key = _safe_key(body.filename)
    upload_id = await storage.create_multipart_upload(key)
    await upload_store.create(upload_id=upload_id, target_key=key)
    part_count = max(1, math.ceil(body.size_bytes / _PART_SIZE_BYTES))
    return InitiateUploadResponse(
        upload_id=upload_id,
        s3_key=key,
        part_size_bytes=_PART_SIZE_BYTES,
        part_count=part_count,
    )


@router.post("/{upload_id}/parts/{part_number}", response_model=PartUrlResponse)
async def get_part_upload_url(
    upload_id: str,
    part_number: int,
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    upload_store: Annotated[UploadSessionStore, Depends(get_upload_store)],
) -> PartUrlResponse:
    session = await _get_session_or_404(upload_store, upload_id)
    url = await storage.presign_upload_part(
        key=session["target_key"], upload_id=upload_id, part_number=part_number
    )
    return PartUrlResponse(part_number=part_number, upload_url=url)


@router.get("/{upload_id}/parts", response_model=ListPartsResponse)
async def list_received_parts(
    upload_id: str,
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    upload_store: Annotated[UploadSessionStore, Depends(get_upload_store)],
) -> ListPartsResponse:
    """Lets a client with lost local upload state discover what's already been received,
    so resume never depends solely on client-side memory (FR-034).
    """
    session = await _get_session_or_404(upload_store, upload_id)
    parts = await storage.list_parts(key=session["target_key"], upload_id=upload_id)
    return ListPartsResponse(
        parts=[
            PartInfo(part_number=p.part_number, etag=p.etag, size_bytes=p.size_bytes) for p in parts
        ]
    )


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_upload(
    upload_id: str,
    body: CompleteUploadRequest,
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    upload_store: Annotated[UploadSessionStore, Depends(get_upload_store)],
) -> CompleteUploadResponse:
    session = await _get_session_or_404(upload_store, upload_id)
    parts = [{"PartNumber": p.part_number, "ETag": p.etag} for p in body.parts]
    await storage.complete_multipart_upload(
        key=session["target_key"], upload_id=upload_id, parts=parts
    )
    await upload_store.mark_state(upload_id, UploadSessionState.COMPLETED)
    return CompleteUploadResponse(s3_key=session["target_key"], status="completed")


@router.post("/{upload_id}/abort", status_code=204)
async def abort_upload(
    upload_id: str,
    storage: Annotated[S3StorageClient, Depends(get_storage_client)],
    upload_store: Annotated[UploadSessionStore, Depends(get_upload_store)],
) -> None:
    session = await _get_session_or_404(upload_store, upload_id)
    await storage.abort_multipart_upload(key=session["target_key"], upload_id=upload_id)
    await upload_store.mark_state(upload_id, UploadSessionState.ABORTED)
