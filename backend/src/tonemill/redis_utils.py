import redis.asyncio as redis
from redis.asyncio.client import Pipeline


async def hgetall_str(client: redis.Redis, key: str) -> dict[str, str]:
    """Typed hgetall.

    redis-py's stubs report bytes|str regardless of decode_responses=True; every client in
    this project sets it, so the result is genuinely dict[str, str] at runtime.
    """
    result: dict[str, str] = await client.hgetall(key)  # ty: ignore[invalid-assignment]
    return result


def hset_on_pipeline(pipeline: Pipeline, key: str, mapping: dict[str, str]) -> None:
    """Typed pipelined hset.

    redis-py's hset overloads don't resolve against Pipeline's sync/async union, even
    though this call (str keys/values, async client) is correct.
    """
    pipeline.hset(key, mapping=mapping)  # ty: ignore[no-matching-overload]
