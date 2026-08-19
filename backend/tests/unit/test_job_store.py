import fakeredis

from tonemill.jobs.store import JobStore


def _store() -> JobStore:
    return JobStore(fakeredis.FakeAsyncRedis(decode_responses=True), ttl_seconds=60)


async def test_list_all_returns_every_job_newest_first():
    # Given three jobs created in order
    store = _store()
    first = await store.create(source_key="sources/a", requested_profile="auto", max_quality=False)
    second = await store.create(source_key="sources/b", requested_profile="auto", max_quality=False)
    third = await store.create(source_key="sources/c", requested_profile="auto", max_quality=False)

    # When listing all jobs
    jobs = await store.list_all()

    # Then all three come back, newest first, regardless of lookup-by-id ever happening
    assert [job.job_id for job in jobs] == [third.job_id, second.job_id, first.job_id]


async def test_list_all_is_empty_when_no_jobs_exist():
    # Given a store with nothing written to it
    store = _store()

    # When listing all jobs
    jobs = await store.list_all()

    # Then the result is an empty list, not an error
    assert jobs == []
