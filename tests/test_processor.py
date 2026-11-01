import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic_ai.models.test import TestModel

from docparser.config import Settings
from docparser.llm.summarizer import Summarizer
from docparser.models import CachedResult, Document, DocumentStatus, Page, ParserType
from docparser.queue import StreamMessage
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository
from docparser.worker.processor import DocumentProcessor


async def _queue_document(
    repository: DocumentRepository,
    file_store: FileStore,
    pdf: bytes,
    parser: ParserType = ParserType.PYPDF,
) -> Document:
    document_id = uuid4()
    sha256 = await file_store.save(document_id, io.BytesIO(pdf), max_bytes=len(pdf))
    now = datetime.now(UTC)
    document = Document(
        id=document_id,
        filename="doc.pdf",
        parser=parser,
        status=DocumentStatus.QUEUED,
        sha256=sha256,
        created_at=now,
        updated_at=now,
    )
    await repository.submit([document])
    return document


def _job(document: Document) -> StreamMessage:
    return StreamMessage("1-0", {"doc_id": str(document.id), "parser": document.parser})


async def test_parses_document_and_removes_the_upload(
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    document = await _queue_document(repository, file_store, sample_pdf)

    await DocumentProcessor(repository, file_store, settings).handle(_job(document))

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.DONE
    assert stored.page_count == 2
    assert [page.markdown for page in await repository.get_pages(document.id)] == [
        "Hello from the first page",
        "Hello from the second page",
    ]
    assert not file_store.path_for(document.id).exists()
    assert stored.summary is None
    assert stored.summary_error is not None and "GEMINI_API_KEY" in stored.summary_error
    assert stored.language is None


async def test_summarizes_parsed_text(
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    document = await _queue_document(repository, file_store, sample_pdf)
    summarizer = Summarizer(TestModel(custom_output_text="Two greetings."), 10_000)

    await DocumentProcessor(repository, file_store, settings, summarizer).handle(
        _job(document)
    )

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.DONE
    assert stored.summary == "Two greetings."
    assert stored.summary_error is None
    assert stored.language == "EN"
    assert stored.mixed_languages is None


@pytest.mark.parametrize(
    ("parser", "expected_error"),
    [
        (ParserType.PYPDF, "No extractable text to summarize; try the Gemini parser"),
        (ParserType.GEMINI, "No text found in the document to summarize"),
    ],
)
async def test_document_without_text_gets_no_summary(
    parser: ParserType,
    expected_error: str,
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    document = await _queue_document(repository, file_store, sample_pdf, parser)
    blank = CachedResult(pages=[Page(number=1, markdown="  ")], summary=None)
    await repository.cache_result(document.sha256, document.parser, blank)
    summarizer = Summarizer(TestModel(custom_output_text="unused"), 10_000)

    await DocumentProcessor(repository, file_store, settings, summarizer).handle(
        _job(document)
    )

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.DONE
    assert stored.summary_error == expected_error


async def test_marks_unreadable_pdf_as_failed_and_keeps_the_file(
    repository: DocumentRepository, file_store: FileStore, settings: Settings
) -> None:
    document = await _queue_document(
        repository, file_store, b"%PDF-1.4\nnot really a pdf"
    )

    await DocumentProcessor(repository, file_store, settings).handle(_job(document))

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.FAILED
    assert stored.error is not None and "readable" in stored.error
    assert file_store.path_for(document.id).exists()


async def test_skips_document_that_is_already_done(
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    document = await _queue_document(repository, file_store, sample_pdf)
    await repository.save_pages(
        document.id, [Page(number=1, markdown="already parsed")]
    )
    await repository.mark_done(document.id, summary="done before", summary_error=None)

    await DocumentProcessor(repository, file_store, settings).handle(_job(document))

    pages = await repository.get_pages(document.id)
    assert pages == [Page(number=1, markdown="already parsed")]


async def test_ignores_job_for_unknown_document(
    repository: DocumentRepository, file_store: FileStore, settings: Settings
) -> None:
    job = StreamMessage("1-0", {"doc_id": str(uuid4()), "parser": "pypdf"})

    await DocumentProcessor(repository, file_store, settings).handle(job)


async def test_ignores_malformed_job(
    repository: DocumentRepository, file_store: FileStore, settings: Settings
) -> None:
    job = StreamMessage("1-0", {"doc_id": "not-a-uuid"})

    await DocumentProcessor(repository, file_store, settings).handle(job)


async def test_reuses_cached_result_for_identical_content(
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    first = await _queue_document(repository, file_store, sample_pdf)
    processor = DocumentProcessor(repository, file_store, settings)
    await processor.handle(_job(first))
    second = await _queue_document(repository, file_store, sample_pdf)
    file_store.path_for(second.id).write_bytes(b"%PDF-1.4\nnot parsed again")

    await processor.handle(_job(second))

    stored = await repository.get(second.id)
    assert stored is not None
    assert stored.status == DocumentStatus.DONE
    assert await repository.get_pages(second.id) == await repository.get_pages(first.id)


async def test_dead_lettered_job_marks_document_failed(
    repository: DocumentRepository,
    file_store: FileStore,
    settings: Settings,
    sample_pdf: bytes,
) -> None:
    document = await _queue_document(repository, file_store, sample_pdf)

    await DocumentProcessor(repository, file_store, settings).handle_dead_letter(
        _job(document)
    )

    stored = await repository.get(document.id)
    assert stored is not None
    assert stored.status == DocumentStatus.FAILED
    assert stored.error is not None and "dead-letter" in stored.error
