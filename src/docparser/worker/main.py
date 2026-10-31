import asyncio
import contextlib
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from typing import Final

from redis.asyncio import Redis

from docparser.config import Settings, get_settings
from docparser.log import configure_logging
from docparser.queue import (
    StreamMessage,
    acknowledge,
    ensure_consumer_group,
    read_new_messages,
)
from docparser.redis_client import create_redis

logger = logging.getLogger(__name__)

READ_BATCH_SIZE: Final[int] = 10

type MessageHandler = Callable[[StreamMessage], Awaitable[None]]


async def log_message(message: StreamMessage) -> None:
    logger.info("Received message %s: %s", message.message_id, message.fields)


class Worker:
    def __init__(
        self,
        redis: Redis,
        settings: Settings,
        consumer_name: str,
        handler: MessageHandler,
    ) -> None:
        self._redis = redis
        self._settings = settings
        self._consumer_name = consumer_name
        self._handler = handler
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        await ensure_consumer_group(
            self._redis, self._settings.stream_name, self._settings.consumer_group
        )
        logger.info(
            "Worker %s consuming %s as group %s",
            self._consumer_name,
            self._settings.stream_name,
            self._settings.consumer_group,
        )
        while not self._stopping.is_set():
            await self.poll_once()
        logger.info("Worker %s stopped", self._consumer_name)

    async def poll_once(self) -> int:
        self._settings.worker_heartbeat_path.touch()
        messages = await read_new_messages(
            self._redis,
            self._settings.stream_name,
            self._settings.consumer_group,
            self._consumer_name,
            count=READ_BATCH_SIZE,
            block_ms=self._settings.worker_block_ms,
        )
        for message in messages:
            try:
                await self._handler(message)
            except Exception:
                logger.exception("Handler failed for message %s", message.message_id)
                continue
            await acknowledge(
                self._redis,
                self._settings.stream_name,
                self._settings.consumer_group,
                message.message_id,
            )
        return len(messages)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = create_redis(settings)
    worker = Worker(
        redis,
        settings,
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
        handler=log_message,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run()
    finally:
        await redis.aclose()
