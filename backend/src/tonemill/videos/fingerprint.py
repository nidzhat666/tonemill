import hashlib

from tonemill.storage.s3_client import S3StorageClient

_SAMPLE_BYTES = 1024 * 1024


async def compute_fingerprint(storage: S3StorageClient, key: str) -> str:
    """A cheap, non-cryptographic duplicate-submission signal (research.md #3): the object's
    total size plus its first and last `_SAMPLE_BYTES`, hashed together. Two small ranged
    `GET`s regardless of source size -- deliberately not a full-file hash, since this is a UX
    safeguard against accidental re-submission, not a security boundary.
    """
    size = await storage.object_size(key)
    if size == 0:
        first = last = b""
    else:
        first_end = min(_SAMPLE_BYTES, size) - 1
        first = await storage.read_range(key, start=0, end=first_end)
        last_start = max(0, size - _SAMPLE_BYTES)
        last = (
            first
            if last_start == 0
            else await storage.read_range(key, start=last_start, end=size - 1)
        )

    digest = hashlib.sha256()
    digest.update(size.to_bytes(8, "big"))
    digest.update(first)
    digest.update(last)
    return digest.hexdigest()
