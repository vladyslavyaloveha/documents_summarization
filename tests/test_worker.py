import asyncio

from redis.asyncio import Redis

from docparser.config import Settings
from docparser.queue import (
    StreamMessage,
    ensure_consumer_group,
    read_new_messages,
    renew_leases,
)
from docparser.worker.main import Worker


async def _pending_count(redis: Redis, settings: Settings) -> int:
    summary = await redis.xpending(settings.stream_name, settings.consumer_group)
    return int(summary["pending"])


async def _crashed_consumer_takes(redis: Redis, settings: Settings) -> None:
    await read_new_messages(
        redis,
        settings.stream_name,
        settings.consumer_group,
        "crashed-consumer",
        count=10,
        block_ms=10,
    )


async def test_consumer_group_creation_is_idempotent(
    redis: Redis, settings: Settings
) -> None:
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)

    groups = await redis.xinfo_groups(settings.stream_name)
    assert [group["name"] for group in groups] == [settings.consumer_group]


async def test_poll_hands_message_to_handler_and_acknowledges(
    redis: Redis, settings: Settings
) -> None:
    received: list[StreamMessage] = []

    async def handler(message: StreamMessage) -> None:
        received.append(message)

    worker = Worker(redis, settings, "consumer-1", handler)
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    await redis.xadd(settings.stream_name, {"doc_id": "doc-1"})

    assert await worker.poll_once() == 1
    await worker.drain()

    assert [message.fields for message in received] == [{"doc_id": "doc-1"}]
    assert await _pending_count(redis, settings) == 0
    assert settings.worker_heartbeat_path.exists()


async def test_failed_handler_leaves_message_pending(
    redis: Redis, settings: Settings
) -> None:
    async def failing_handler(message: StreamMessage) -> None:
        raise RuntimeError("boom")

    worker = Worker(redis, settings, "consumer-1", failing_handler)
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    await redis.xadd(settings.stream_name, {"doc_id": "doc-1"})

    await worker.poll_once()
    await worker.drain()

    assert await _pending_count(redis, settings) == 1


async def test_jobs_added_before_group_creation_are_consumed(
    redis: Redis, settings: Settings
) -> None:
    received: list[StreamMessage] = []

    async def handler(message: StreamMessage) -> None:
        received.append(message)

    await redis.xadd(settings.stream_name, {"doc_id": "early"})
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)

    worker = Worker(redis, settings, "consumer-1", handler)
    await worker.poll_once()
    await worker.drain()

    assert [message.fields for message in received] == [{"doc_id": "early"}]


async def test_processes_at_most_the_configured_number_of_jobs_at_once(
    redis: Redis, settings: Settings
) -> None:
    release = asyncio.Event()
    started: list[str] = []

    async def slow_handler(message: StreamMessage) -> None:
        started.append(message.fields["doc_id"])
        await release.wait()

    worker = Worker(
        redis, settings.model_copy(update={"worker_concurrency": 2}), "c1", slow_handler
    )
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    for doc_id in ("a", "b", "c"):
        await redis.xadd(settings.stream_name, {"doc_id": doc_id})

    assert await worker.poll_once() == 2
    await asyncio.sleep(0)
    assert started == ["a", "b"]

    release.set()
    await worker.drain()
    assert await worker.poll_once() == 1
    await worker.drain()
    assert started == ["a", "b", "c"]


async def test_reclaims_job_abandoned_by_crashed_consumer(
    redis: Redis, settings: Settings
) -> None:
    received: list[StreamMessage] = []

    async def handler(message: StreamMessage) -> None:
        received.append(message)

    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    await redis.xadd(settings.stream_name, {"doc_id": "orphan"})
    await _crashed_consumer_takes(redis, settings)

    worker = Worker(
        redis, settings.model_copy(update={"reclaim_idle_ms": 0}), "c1", handler
    )
    await worker.poll_once()
    await worker.drain()

    assert [message.fields for message in received] == [{"doc_id": "orphan"}]
    assert await _pending_count(redis, settings) == 0


async def test_moves_repeatedly_delivered_job_to_dead_letter_stream(
    redis: Redis, settings: Settings
) -> None:
    handled: list[StreamMessage] = []
    dead: list[StreamMessage] = []

    async def handler(message: StreamMessage) -> None:
        handled.append(message)

    async def dead_letter_handler(message: StreamMessage) -> None:
        dead.append(message)

    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    await redis.xadd(settings.stream_name, {"doc_id": "poison"})
    await _crashed_consumer_takes(redis, settings)

    limited = settings.model_copy(update={"reclaim_idle_ms": 0, "max_deliveries": 1})
    worker = Worker(redis, limited, "c1", handler, dead_letter_handler)
    await worker.poll_once()
    await worker.drain()

    assert handled == []
    assert [message.fields for message in dead] == [{"doc_id": "poison"}]
    assert await _pending_count(redis, settings) == 0
    dead_letters = await redis.xrange(settings.dead_letter_stream)
    assert [fields["doc_id"] for _, fields in dead_letters] == ["poison"]


async def test_renewing_a_lease_resets_idle_time(
    redis: Redis, settings: Settings
) -> None:
    await ensure_consumer_group(redis, settings.stream_name, settings.consumer_group)
    message_id = await redis.xadd(settings.stream_name, {"doc_id": "busy"})
    await _crashed_consumer_takes(redis, settings)
    await asyncio.sleep(0.05)

    await renew_leases(
        redis,
        settings.stream_name,
        settings.consumer_group,
        "crashed-consumer",
        [message_id],
    )

    [entry] = await redis.xpending_range(
        settings.stream_name, settings.consumer_group, message_id, message_id, 1
    )
    assert entry["time_since_delivered"] < 50
    assert entry["times_delivered"] == 1
