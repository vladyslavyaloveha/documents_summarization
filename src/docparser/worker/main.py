import asyncio
import contextlib
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis

from docparser.config import Settings, get_settings
from docparser.llm.summarizer import build_summarizer
from docparser.log import configure_logging
from docparser.queue import (
    StreamMessage,
    acknowledge,
    claim_stale_messages,
    delivery_count,
    ensure_consumer_group,
    move_to_dead_letter,
    read_new_messages,
    renew_leases,
)
from docparser.redis_client import create_redis
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository
from docparser.worker.processor import DocumentProcessor

logger = logging.getLogger(__name__)

type MessageHandler = Callable[[StreamMessage], Awaitable[None]]


class Worker:
    def __init__(
        self,
        redis: Redis,
        settings: Settings,
        consumer_name: str,
        handler: MessageHandler,
        dead_letter_handler: MessageHandler | None = None,
    ) -> None:
        self._redis = redis
        self._settings = settings
        self._consumer_name = consumer_name
        self._handler = handler
        self._dead_letter_handler = dead_letter_handler
        self._stopping = asyncio.Event()
        self._in_flight: dict[str, asyncio.Task[None]] = {}

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
        await self.drain()
        logger.info("Worker %s stopped", self._consumer_name)

    async def poll_once(self) -> int:
        self._settings.worker_heartbeat_path.touch()
        stream = self._settings.stream_name
        group = self._settings.consumer_group
        await renew_leases(
            self._redis, stream, group, self._consumer_name, list(self._in_flight)
        )
        free_slots = self._settings.worker_concurrency - len(self._in_flight)
        if free_slots <= 0:
            await asyncio.wait(
                self._in_flight.values(),
                timeout=self._settings.worker_block_ms / 1000,
                return_when=asyncio.FIRST_COMPLETED,
            )
            return 0
        messages = await claim_stale_messages(
            self._redis,
            stream,
            group,
            self._consumer_name,
            min_idle_ms=self._settings.reclaim_idle_ms,
            count=free_slots,
        )
        if not messages:
            messages = await read_new_messages(
                self._redis,
                stream,
                group,
                self._consumer_name,
                count=free_slots,
                block_ms=self._settings.worker_block_ms,
            )
        for message in messages:
            self._start(message)
        return len(messages)

    async def drain(self) -> None:
        if self._in_flight:
            await asyncio.gather(*self._in_flight.values(), return_exceptions=True)

    def _start(self, message: StreamMessage) -> None:
        task = asyncio.create_task(self._process(message))
        self._in_flight[message.message_id] = task
        task.add_done_callback(lambda _: self._in_flight.pop(message.message_id, None))

    async def _process(self, message: StreamMessage) -> None:
        stream = self._settings.stream_name
        group = self._settings.consumer_group
        try:
            deliveries = await delivery_count(
                self._redis, stream, group, message.message_id
            )
            if deliveries > self._settings.max_deliveries:
                await self._dead_letter(message, deliveries)
                return
            await self._handler(message)
        except Exception:
            logger.exception("Handler failed for message %s", message.message_id)
            return
        await acknowledge(self._redis, stream, group, message.message_id)

    async def _dead_letter(self, message: StreamMessage, deliveries: int) -> None:
        logger.error(
            "Moving message %s to %s after %d deliveries",
            message.message_id,
            self._settings.dead_letter_stream,
            deliveries,
        )
        if self._dead_letter_handler is not None:
            await self._dead_letter_handler(message)
        await move_to_dead_letter(
            self._redis,
            self._settings.stream_name,
            self._settings.consumer_group,
            self._settings.dead_letter_stream,
            message,
        )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = create_redis(settings)
    summarizer = build_summarizer(settings)
    if summarizer is None:
        logger.warning("GEMINI_API_KEY is not set: documents get no summary")
    processor = DocumentProcessor(
        DocumentRepository(redis, settings),
        FileStore(settings.upload_dir),
        settings,
        summarizer,
    )
    worker = Worker(
        redis,
        settings,
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
        handler=processor.handle,
        dead_letter_handler=processor.handle_dead_letter,
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)
    try:
        await worker.run()
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
