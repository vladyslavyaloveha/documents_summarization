import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from redis.typing import EncodableT, FieldT

logger = logging.getLogger(__name__)

type XReadGroupReply = dict[str, list[tuple[str, dict[str, str]]]]


@dataclass(frozen=True, slots=True)
class StreamMessage:
    message_id: str
    fields: dict[str, str]


async def ensure_consumer_group(redis: Redis, stream: str, group: str) -> None:
    try:
        await redis.xgroup_create(stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if not str(exc).startswith("BUSYGROUP"):
            raise


async def read_new_messages(
    redis: Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    count: int,
    block_ms: int,
) -> list[StreamMessage]:
    reply = cast(
        XReadGroupReply,
        await redis.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms
        ),
    )
    return [
        StreamMessage(message_id, fields)
        for message_id, fields in reply.get(stream, [])
    ]


async def claim_stale_messages(
    redis: Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    min_idle_ms: int,
    count: int,
) -> list[StreamMessage]:
    reply = await redis.xautoclaim(
        stream, group, consumer, min_idle_time=min_idle_ms, count=count
    )
    deleted_ids = reply[2] if len(reply) > 2 else []
    if deleted_ids:
        logger.warning("Pending jobs trimmed from %s: %s", stream, deleted_ids)
    return [StreamMessage(message_id, fields) for message_id, fields in reply[1]]


async def renew_leases(
    redis: Redis, stream: str, group: str, consumer: str, message_ids: Sequence[str]
) -> None:
    if message_ids:
        await redis.xclaim(
            stream,
            group,
            consumer,
            min_idle_time=0,
            message_ids=list(message_ids),
            justid=True,
        )


async def delivery_count(redis: Redis, stream: str, group: str, message_id: str) -> int:
    entries = await redis.xpending_range(stream, group, message_id, message_id, 1)
    return int(entries[0]["times_delivered"]) if entries else 0


async def acknowledge(redis: Redis, stream: str, group: str, message_id: str) -> None:
    await redis.xack(stream, group, message_id)


async def move_to_dead_letter(
    redis: Redis,
    stream: str,
    group: str,
    dead_letter_stream: str,
    message: StreamMessage,
) -> None:
    fields: dict[FieldT, EncodableT] = {k: v for k, v in message.fields.items()}
    fields["source_id"] = message.message_id
    async with redis.pipeline(transaction=True) as pipe:
        pipe.xadd(dead_letter_stream, fields)
        pipe.xack(stream, group, message.message_id)
        await pipe.execute()
