from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from docparser.config import Settings
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository


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


RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
FileStoreDep = Annotated[FileStore, Depends(get_file_store)]
