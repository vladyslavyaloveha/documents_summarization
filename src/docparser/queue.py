from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

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


async def acknowledge(redis: Redis, stream: str, group: str, message_id: str) -> None:
    await redis.xack(stream, group, message_id)
