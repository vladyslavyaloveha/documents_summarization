import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import TypeAdapter
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.typing import EncodableT, FieldT

from docparser.config import Settings
from docparser.models import Document, DocumentStatus, Page, ParserType

type HashFields = dict[FieldT, EncodableT]

_PAGES = TypeAdapter(list[Page])


def events_channel(document_id: UUID) -> str:
    return f"doc:{document_id}:events"


def _document_key(document_id: UUID) -> str:
    return f"doc:{document_id}"


def _pages_key(document_id: UUID) -> str:
    return f"doc:{document_id}:pages"


def _cache_key(sha256: str, parser: ParserType) -> str:
    return f"result:{parser.value}:{sha256}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _publish_status(pipe: Pipeline, document_id: UUID, status: DocumentStatus) -> None:
    pipe.publish(
        events_channel(document_id),
        json.dumps({"id": str(document_id), "status": status.value}),
    )


class DocumentRepository:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    async def submit(self, documents: Sequence[Document]) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            for document in documents:
                key = _document_key(document.id)
                fields = document.model_dump(mode="json", exclude_none=True)
                pipe.hset(key, mapping=cast(HashFields, fields))
                pipe.expire(key, self._settings.document_ttl_seconds)
                pipe.xadd(
                    self._settings.stream_name,
                    {"doc_id": str(document.id), "parser": document.parser.value},
                    maxlen=self._settings.stream_max_length,
                    approximate=True,
                )
            await pipe.execute()

    async def get(self, document_id: UUID) -> Document | None:
        fields = await self._redis.hgetall(_document_key(document_id))
        return Document.model_validate(fields) if fields else None

    async def get_pages(self, document_id: UUID) -> list[Page]:
        raw = await self._redis.get(_pages_key(document_id))
        return _PAGES.validate_json(raw) if raw else []

    async def get_cached_pages(
        self, sha256: str, parser: ParserType
    ) -> list[Page] | None:
        raw = await self._redis.get(_cache_key(sha256, parser))
        return _PAGES.validate_json(raw) if raw else None

    async def cache_pages(
        self, sha256: str, parser: ParserType, pages: Sequence[Page]
    ) -> None:
        await self._redis.set(
            _cache_key(sha256, parser),
            _PAGES.dump_json(list(pages)),
            ex=self._settings.document_ttl_seconds,
        )

    async def mark_parsing(self, document_id: UUID) -> None:
        await self._update(document_id, DocumentStatus.PARSING, {})

    async def mark_failed(self, document_id: UUID, error: str) -> None:
        await self._update(document_id, DocumentStatus.FAILED, {"error": error})

    async def mark_done(self, document_id: UUID, pages: Sequence[Page]) -> None:
        ttl = self._settings.document_ttl_seconds
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(_pages_key(document_id), _PAGES.dump_json(list(pages)), ex=ttl)
            self._queue_update(
                pipe, document_id, DocumentStatus.DONE, {"page_count": len(pages)}
            )
            pipe.expire(_document_key(document_id), ttl)
            await pipe.execute()

    async def _update(
        self, document_id: UUID, status: DocumentStatus, fields: HashFields
    ) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            self._queue_update(pipe, document_id, status, fields)
            await pipe.execute()

    def _queue_update(
        self,
        pipe: Pipeline,
        document_id: UUID,
        status: DocumentStatus,
        fields: HashFields,
    ) -> None:
        pipe.hset(
            _document_key(document_id),
            mapping={**fields, "status": status.value, "updated_at": _now()},
        )
        _publish_status(pipe, document_id, status)
