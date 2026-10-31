import logging
from uuid import UUID

from docparser.config import Settings
from docparser.models import DocumentStatus
from docparser.parsers import get_parser
from docparser.parsers.base import ParsingError
from docparser.queue import StreamMessage
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self, repository: DocumentRepository, file_store: FileStore, settings: Settings
    ) -> None:
        self._repository = repository
        self._file_store = file_store
        self._settings = settings

    async def handle(self, message: StreamMessage) -> None:
        try:
            document_id = UUID(message.fields["doc_id"])
        except (KeyError, ValueError):
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
        cached = await self._repository.get_cached_pages(
            document.sha256, document.parser
        )
        if cached is not None:
            await self._repository.mark_done(document_id, cached)
            await self._file_store.delete(document_id)
            logger.info("Document %s served from the result cache", document_id)
            return

        parser = get_parser(document.parser, self._settings)
        try:
            pages = await parser.parse(self._file_store.path_for(document_id))
        except ParsingError as exc:
            logger.info("Document %s failed to parse: %s", document_id, exc)
            await self._repository.mark_failed(document_id, str(exc))
            return
        except Exception:
            logger.exception("Unexpected error while parsing document %s", document_id)
            await self._repository.mark_failed(
                document_id, "Internal error while parsing the document"
            )
            return

        await self._repository.cache_pages(document.sha256, document.parser, pages)
        await self._repository.mark_done(document_id, pages)
        await self._file_store.delete(document_id)
        logger.info("Document %s parsed: %d pages", document_id, len(pages))

    async def handle_dead_letter(self, message: StreamMessage) -> None:
        try:
            document_id = UUID(message.fields["doc_id"])
        except (KeyError, ValueError):
            return
        await self._repository.mark_failed(
            document_id,
            "Processing failed repeatedly; the job was moved to the dead-letter queue",
        )
