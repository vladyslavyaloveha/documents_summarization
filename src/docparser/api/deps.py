from typing import Annotated, Final
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis

from docparser.config import Settings
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository

MAX_IDS_PER_REQUEST: Final[int] = 50


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def get_repository(redis: RedisDep, settings: SettingsDep) -> DocumentRepository:
    return DocumentRepository(redis, settings)


def get_file_store(settings: SettingsDep) -> FileStore:
    return FileStore(settings.upload_dir)


def get_document_ids(
    ids: Annotated[str, Query(description="Comma-separated document IDs")],
) -> list[UUID]:
    try:
        parsed = [UUID(part.strip()) for part in ids.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "ids must be comma-separated UUIDs"
        ) from exc
    if not parsed or len(parsed) > MAX_IDS_PER_REQUEST:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Provide between 1 and {MAX_IDS_PER_REQUEST} ids",
        )
    return list(dict.fromkeys(parsed))


RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
FileStoreDep = Annotated[FileStore, Depends(get_file_store)]
DocumentIdsDep = Annotated[list[UUID], Depends(get_document_ids)]
