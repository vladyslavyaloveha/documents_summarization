import json
from datetime import UTC, datetime
from uuid import uuid4

from redis.asyncio import Redis

from docparser.config import Settings
from docparser.models import CachedResult, Document, DocumentStatus, Page, ParserType
from docparser.storage.repository import DocumentRepository


def _document() -> Document:
    now = datetime.now(UTC)
    return Document(
        id=uuid4(),
        filename="doc.pdf",
        parser=ParserType.PYPDF,
        status=DocumentStatus.QUEUED,
        sha256="0" * 64,
        created_at=now,
        updated_at=now,
    )


async def test_submit_stores_document_with_ttl_and_queues_job(
    repository: DocumentRepository, redis: Redis, settings: Settings
) -> None:
    document = _document()

    await repository.submit([document])

    assert await repository.get(document.id) == document
    assert 0 < await redis.ttl(f"doc:{document.id}") <= settings.document_ttl_seconds
    jobs = await redis.xrange(settings.stream_name)
    assert [fields for _, fields in jobs] == [
        {"doc_id": str(document.id), "parser": "pypdf"}
    ]


async def test_mark_failed_records_the_error(repository: DocumentRepository) -> None:
    document = _document()
    await repository.submit([document])

    await repository.mark_failed(document.id, "The file is not a readable PDF")

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.FAILED
    assert stored.error == "The file is not a readable PDF"


async def test_get_unknown_document_returns_none(
    repository: DocumentRepository,
) -> None:
    assert await repository.get(uuid4()) is None


async def test_status_changes_are_published(
    repository: DocumentRepository, redis: Redis
) -> None:
    document = _document()
    await repository.submit([document])
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"doc:{document.id}:events")
    await pubsub.get_message(timeout=1)

    await repository.mark_parsing(document.id)

    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message is not None
    assert json.loads(message["data"]) == {"id": str(document.id), "status": "parsing"}
    await pubsub.aclose()


async def test_cached_results_are_keyed_by_parser_and_content(
    repository: DocumentRepository,
) -> None:
    result = CachedResult(pages=[Page(number=1, markdown="cached")], summary="short")

    await repository.cache_result("abc", ParserType.PYPDF, result)

    assert await repository.get_cached_result("abc", ParserType.PYPDF) == result
    assert await repository.get_cached_result("other", ParserType.PYPDF) is None


async def test_unreadable_cache_entry_is_a_miss(
    repository: DocumentRepository, redis: Redis
) -> None:
    await redis.set("result:v2:pypdf:abc", '[{"number": 1, "markdown": "old format"}]')

    assert await repository.get_cached_result("abc", ParserType.PYPDF) is None
