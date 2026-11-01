import os
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from docparser.config import Settings
from docparser.queue import StreamMessage, ensure_consumer_group, read_new_messages
from docparser.redis_client import create_redis
from docparser.worker.main import Worker

pytestmark = pytest.mark.integration


@pytest.fixture
async def real_redis(settings: Settings) -> AsyncIterator[Redis]:
    url = os.environ.get("INTEGRATION_REDIS_URL", "redis://localhost:6379/15")
    client = create_redis(settings.model_copy(update={"redis_url": url}))
    try:
        await client.ping()
    except RedisError as exc:
        pytest.fail(
            f"Redis at {url} is unreachable; start it with docker compose: {exc}"
        )
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def test_worker_consumes_and_acknowledges_on_real_redis(
    real_redis: Redis, settings: Settings
) -> None:
    received: list[StreamMessage] = []

    async def handler(message: StreamMessage) -> None:
        received.append(message)

    await ensure_consumer_group(
        real_redis, settings.stream_name, settings.consumer_group
    )
    await real_redis.xadd(settings.stream_name, {"doc_id": "real"})
    worker = Worker(real_redis, settings, "c1", handler)

    await worker.poll_once()
    await worker.drain()

    assert [message.fields for message in received] == [{"doc_id": "real"}]
    summary = await real_redis.xpending(settings.stream_name, settings.consumer_group)
    assert summary["pending"] == 0


async def test_crashed_consumer_job_is_reclaimed_then_dead_lettered(
    real_redis: Redis, settings: Settings
) -> None:
    attempts: list[str] = []
    dead: list[StreamMessage] = []

    async def failing_handler(message: StreamMessage) -> None:
        attempts.append(message.message_id)
        raise RuntimeError("worker bug")

    async def dead_letter_handler(message: StreamMessage) -> None:
        dead.append(message)

    stream, group = settings.stream_name, settings.consumer_group
    await ensure_consumer_group(real_redis, stream, group)
    await real_redis.xadd(stream, {"doc_id": "poison"})
    await read_new_messages(real_redis, stream, group, "crashed", count=1, block_ms=10)
    limited = settings.model_copy(update={"reclaim_idle_ms": 0, "max_deliveries": 2})
    worker = Worker(real_redis, limited, "c1", failing_handler, dead_letter_handler)

    await worker.poll_once()
    await worker.drain()
    await worker.poll_once()
    await worker.drain()

    assert len(attempts) == 1
    assert [message.fields for message in dead] == [{"doc_id": "poison"}]
    dead_letters = await real_redis.xrange(settings.dead_letter_stream)
    assert [fields["doc_id"] for _, fields in dead_letters] == ["poison"]
    summary = await real_redis.xpending(stream, group)
    assert summary["pending"] == 0
