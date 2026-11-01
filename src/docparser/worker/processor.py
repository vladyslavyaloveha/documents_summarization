import logging
from collections.abc import Sequence
from uuid import UUID

from pydantic_ai.exceptions import ModelHTTPError

from docparser.config import Settings
from docparser.llm.summarizer import Summarizer
from docparser.models import CachedResult, DocumentStatus, Page, ParserType
from docparser.parsers import get_parser
from docparser.parsers.base import ParsingError
from docparser.queue import StreamMessage
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        repository: DocumentRepository,
        file_store: FileStore,
        settings: Settings,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._repository = repository
        self._file_store = file_store
        self._settings = settings
        self._summarizer = summarizer

    async def handle(self, message: StreamMessage) -> None:
        document_id = _document_id(message)
        if document_id is None:
            logger.error(
                "Dropping malformed job %s: %s", message.message_id, message.fields
            )
            return

        document = await self._repository.get(document_id)
        if document is None:
            logger.warning(
                "Skipping job %s: document %s not found",
                message.message_id,
                document_id,
            )
            return
        if document.status in (DocumentStatus.DONE, DocumentStatus.FAILED):
            logger.info(
                "Skipping document %s: already %s", document_id, document.status
            )
            return

        await self._repository.mark_parsing(document_id)
        cached = await self._repository.get_cached_result(
            document.sha256, document.parser
        )
        if cached is None:
            pages = await self._parse(document_id, document.parser)
            if pages is None:
                return
            summary = None
        else:
            logger.info("Document %s served from the result cache", document_id)
            pages, summary = cached.pages, cached.summary

        await self._repository.save_pages(document_id, pages)
        summary_error = None
        if summary is None:
            summary, summary_error = await self._summarize(
                document_id, document.parser, pages
            )
        await self._repository.cache_result(
            document.sha256, document.parser, CachedResult(pages=pages, summary=summary)
        )
        await self._repository.mark_done(
            document_id, summary=summary, summary_error=summary_error
        )
        await self._file_store.delete(document_id)
        logger.info("Document %s done: %d pages", document_id, len(pages))

    async def handle_dead_letter(self, message: StreamMessage) -> None:
        document_id = _document_id(message)
        if document_id is not None:
            await self._repository.mark_failed(
                document_id,
                "Processing failed repeatedly; the job was moved to the dead-letter queue",
            )

    async def _parse(
        self, document_id: UUID, parser_type: ParserType
    ) -> list[Page] | None:
        parser = get_parser(parser_type, self._settings)
        try:
            return await parser.parse(self._file_store.path_for(document_id))
        except ParsingError as exc:
            logger.info("Document %s failed to parse: %s", document_id, exc)
            await self._repository.mark_failed(document_id, str(exc))
        except Exception:
            logger.exception("Unexpected error while parsing document %s", document_id)
            await self._repository.mark_failed(
                document_id, "Internal error while parsing the document"
            )
        return None

    async def _summarize(
        self, document_id: UUID, parser: ParserType, pages: Sequence[Page]
    ) -> tuple[str | None, str | None]:
        if self._summarizer is None:
            return None, "Summarization is disabled: GEMINI_API_KEY is not set"
        text = "\n\n".join(page.markdown for page in pages).strip()
        if not text:
            if parser == ParserType.PYPDF:
                return None, "No extractable text to summarize; try the Gemini parser"
            return None, "No text found in the document to summarize"
        try:
            return await self._summarizer.summarize(text), None
        except ModelHTTPError as exc:
            logger.warning("Gemini API error for document %s: %s", document_id, exc)
            return None, f"Gemini API error (HTTP {exc.status_code})"
        except Exception:
            logger.exception("Summarization failed for document %s", document_id)
            return None, "Summarization failed"


def _document_id(message: StreamMessage) -> UUID | None:
    try:
        return UUID(message.fields["doc_id"])
    except (KeyError, ValueError):
        return None
