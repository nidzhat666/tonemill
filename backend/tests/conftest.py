"""Session-wide fixtures shared across the test suite."""

import socket
import subprocess
import time
from collections.abc import Iterator

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError


@pytest.fixture(scope="session")
def mongo_url() -> Iterator[str]:
    """A real MongoDB, started once for the whole test session via Docker (research.md #1's
    testing philosophy: no `mongomock`, exercise the real unique-index/collation behavior the
    duplicate-detection and folder-naming logic actually depends on).
    """
    port = _free_port()
    container_id = subprocess.check_output(
        ["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{port}:27017", "mongo:7"],
        text=True,
    ).strip()
    url = f"mongodb://localhost:{port}"
    try:
        _wait_until_ready(url)
        yield url
    finally:
        subprocess.run(["docker", "stop", container_id], check=False, capture_output=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def _wait_until_ready(url: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: PyMongoError | None = None
    while time.monotonic() < deadline:
        try:
            MongoClient(url, serverSelectionTimeoutMS=500).admin.command("ping")
            return
        except PyMongoError as exc:  # noqa: PERF203 - startup poll, not a hot loop
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"mongo container never became ready: {last_error}")
