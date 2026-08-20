"""Smoke test: exercises the upload -> job submit -> status flow against a real (local)
moto S3 server and fakeredis, without a real ffmpeg/GPU. moto's mock_aws decorator doesn't
support aiobotocore's async response objects, so this runs moto as an actual local HTTP
server instead -- aioboto3 then just talks normal HTTP to it, no mocking magic needed.
"""

import uuid

import boto3
import fakeredis
import pytest
from fastapi.testclient import TestClient
from moto.server import ThreadedMotoServer
from pymongo import AsyncMongoClient

import tonemill.api.main as api_main
import tonemill.dependencies as shared_dependencies
from tonemill.config import Settings

_BUCKET = "tonemill-test"


@pytest.fixture
def client(monkeypatch, mongo_url):
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    endpoint = f"http://{host}:{port}"

    settings = Settings(
        s3_endpoint_url=endpoint,
        s3_access_key_id="test",
        s3_secret_access_key="test",
        s3_bucket=_BUCKET,
        s3_region="us-east-1",
        mongo_url=mongo_url,
        mongo_db=f"tonemill_test_{uuid.uuid4().hex}",
    )
    boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).create_bucket(Bucket=_BUCKET)

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    for cached in (
        shared_dependencies.get_redis_client,
        shared_dependencies.get_job_store,
        shared_dependencies.get_upload_store,
        shared_dependencies.get_registry,
        shared_dependencies.get_mongo_client,
        shared_dependencies.get_video_store,
        shared_dependencies.get_folder_store,
    ):
        cached.cache_clear()
    monkeypatch.setattr(shared_dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(shared_dependencies, "get_redis_client", lambda: fake_redis)
    # A fresh AsyncMongoClient per test, not the process-cached one (research.md #1's
    # per-job-run rationale applies here too: it binds to the event loop it's created on, and
    # each test's TestClient portal runs its own).
    monkeypatch.setattr(
        shared_dependencies, "get_mongo_client", lambda: AsyncMongoClient(mongo_url)
    )
    monkeypatch.setattr(api_main, "get_settings", lambda: settings)

    with TestClient(api_main.create_app()) as test_client:
        yield test_client

    server.stop()


def test_list_profiles(client):
    # Given the app is running with the default profile registry
    # When listing profiles
    response = client.get("/profiles")

    # Then all three registered profiles are returned
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"hlg-gpu", "hlg-cpu", "d-log-m"}


def test_submit_job_rejects_unknown_profile(client):
    # Given a completed upload exists
    _put_source(client)

    # When submitting a job against a profile name the registry doesn't know
    response = client.post("/jobs", json={"s3_key": _source_key(), "profile": "nonexistent"})

    # Then the request is rejected
    assert response.status_code == 400


def test_submit_job_rejects_dlog_m(client):
    # Given a completed upload exists
    _put_source(client)

    # When submitting a job against the registered-but-not-implemented d-log-m profile
    response = client.post("/jobs", json={"s3_key": _source_key(), "profile": "d-log-m"})

    # Then it's rejected as not-yet-implemented, not accepted into the queue
    assert response.status_code == 409


def test_submit_job_rejects_missing_source(client):
    # Given no object exists at the referenced key
    # When submitting a job against it
    response = client.post("/jobs", json={"s3_key": "sources/does-not-exist", "profile": "hlg-cpu"})

    # Then the request is rejected rather than queued to fail later
    assert response.status_code == 400


def test_upload_flow_initiate_and_list_parts(client):
    # Given a client initiating a new upload
    response = client.post(
        "/uploads", json={"filename": "clip.mp4", "content_type": "video/mp4", "size_bytes": 100}
    )

    # Then it gets a single-part upload session
    assert response.status_code == 201
    body = response.json()
    assert body["part_count"] == 1

    # When listing received parts before any part is uploaded
    parts_response = client.get(f"/uploads/{body['upload_id']}/parts")

    # Then none are reported yet
    assert parts_response.status_code == 200
    assert parts_response.json() == {"parts": []}


async def test_list_jobs_returns_jobs_not_created_via_this_client(client):
    # Given a job that exists in the job store but was never fetched by id through this client
    # (e.g. it was submitted from a different browser/tab)
    job_store = shared_dependencies.get_job_store()
    job = await job_store.create(
        source_key=_source_key(), requested_profile="hlg-cpu", max_quality=False
    )

    # When listing all jobs
    response = client.get("/jobs")

    # Then it's included, without ever being requested by id
    assert response.status_code == 200
    job_ids = {j["job_id"] for j in response.json()}
    assert job.job_id in job_ids


def test_job_not_found_returns_404(client):
    # Given no job was ever submitted with this id
    # When polling its status
    response = client.get("/jobs/does-not-exist")

    # Then the client gets an unambiguous 404, not a stale or default response
    assert response.status_code == 404


def _source_key() -> str:
    return "sources/x/clip.mp4"


def _put_source(client: TestClient) -> None:
    settings: Settings = api_main.get_settings()
    boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    ).put_object(Bucket=_BUCKET, Key=_source_key(), Body=b"data")
