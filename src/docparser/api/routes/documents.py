from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Final
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from redis.exceptions import RedisError

from docparser.api.deps import (
    DocumentIdsDep,
    FileStoreDep,
    RepositoryDep,
    SettingsDep,
)
from docparser.models import Document, DocumentDetail, DocumentStatus, ParserType
from docparser.parsers import available_parsers
from docparser.storage.repository import DocumentRepository

router = APIRouter(prefix="/api", tags=["documents"])

PDF_SIGNATURE: Final[bytes] = b"%PDF-"
PDF_HEADER_SEARCH_BYTES: Final[int] = 1024
MAX_FILENAME_LENGTH: Final[int] = 255
DEFAULT_FILENAME: Final[str] = "document.pdf"


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    files: Annotated[list[UploadFile], File()],
    settings: SettingsDep,
    repository: RepositoryDep,
    file_store: FileStoreDep,
    parser: Annotated[ParserType, Form()] = ParserType.PYPDF,
) -> list[Document]:
    if parser not in available_parsers(settings):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Parser {parser} is not available: GEMINI_API_KEY is not set",
        )
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"At most {settings.max_files_per_upload} files per upload",
        )
    for upload in files:
        await _ensure_pdf_within_limit(upload, settings.max_upload_size_bytes)

    documents: list[Document] = []
    try:
        for upload in files:
            document_id = uuid4()
            sha256 = await file_store.save(
                document_id, upload.file, settings.max_upload_size_bytes
            )
            documents.append(
                _queued_document(document_id, upload.filename, parser, sha256)
            )
        await repository.submit(documents)
    except Exception as exc:
        for document in documents:
            await file_store.delete(document.id)
        if isinstance(exc, RedisError):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Document queue is unavailable"
            ) from exc
        raise
    return documents


@router.get("/documents")
async def get_documents(
    document_ids: DocumentIdsDep, repository: RepositoryDep
) -> list[DocumentDetail]:
    details = [await _detail(repository, document_id) for document_id in document_ids]
    return [detail for detail in details if detail is not None]


@router.get("/documents/{document_id}")
async def get_document(document_id: UUID, repository: RepositoryDep) -> DocumentDetail:
    detail = await _detail(repository, document_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return detail


async def _detail(
    repository: DocumentRepository, document_id: UUID
) -> DocumentDetail | None:
    document = await repository.get(document_id)
    if document is None:
        return None
    pages = await repository.get_pages(document_id)
    return DocumentDetail.model_validate({**document.model_dump(), "pages": pages})


@router.get("/parsers")
async def list_parsers(settings: SettingsDep) -> list[ParserType]:
    return available_parsers(settings)


async def _ensure_pdf_within_limit(upload: UploadFile, max_bytes: int) -> None:
    name = _display_name(upload.filename)
    if upload.size is not None and upload.size > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"{name} exceeds the {max_bytes} byte limit",
        )
    header = await upload.read(PDF_HEADER_SEARCH_BYTES)
    await upload.seek(0)
    if PDF_SIGNATURE not in header:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{name} is not a PDF"
        )


def _display_name(filename: str | None) -> str:
    name = PurePosixPath((filename or "").replace("\\", "/")).name.strip()
    return (name or DEFAULT_FILENAME)[:MAX_FILENAME_LENGTH]


def _queued_document(
    document_id: UUID, filename: str | None, parser: ParserType, sha256: str
) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=document_id,
        filename=_display_name(filename),
        parser=parser,
        status=DocumentStatus.QUEUED,
        sha256=sha256,
        created_at=now,
        updated_at=now,
    )
