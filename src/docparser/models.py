from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ParserType(StrEnum):
    PYPDF = "pypdf"
    GEMINI = "gemini"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    SUMMARIZING = "summarizing"
    DONE = "done"
    FAILED = "failed"


class Page(BaseModel):
    number: int
    markdown: str


class Document(BaseModel):
    id: UUID
    filename: str
    parser: ParserType
    status: DocumentStatus
    sha256: str
    error: str | None = None
    page_count: int | None = None
    summary: str | None = None
    summary_error: str | None = None
    language: str | None = None
    mixed_languages: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(Document):
    pages: list[Page]


class CachedResult(BaseModel):
    pages: list[Page]
    summary: str | None
