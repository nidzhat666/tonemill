from fastapi import Request

from tonemill.storage.s3_client import S3StorageClient


def get_storage_client(request: Request) -> S3StorageClient:
    """Opened once in the app's lifespan (main.py) -- aioboto3 clients are async context
    managers tied to the running event loop, so a request-scoped Depends() just reads it
    back from app.state rather than opening a new one per request.
    """
    return request.app.state.storage_client
