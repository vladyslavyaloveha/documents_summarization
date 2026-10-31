from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedisConnection, FakeServer
from httpx import ASGITransport, AsyncClient
from redis.asyncio import ConnectionPool, Redis

from docparser.api.deps import get_redis
from docparser.api.main import create_app
from docparser.config import Settings
from docparser.redis_client import CLIENT_OPTIONS
from docparser.storage.files import FileStore
from docparser.storage.repository import DocumentRepository

FIXTURES = Path(__file__).parent / "fixtures"

type ApiClientFactory = Callable[[Settings], AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        upload_dir=tmp_path / "uploads",
        worker_heartbeat_path=tmp_path / "heartbeat",
        worker_block_ms=10,
    )


@pytest.fixture
def sample_pdf() -> bytes:
    return (FIXTURES / "sample.pdf").read_bytes()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    pool = ConnectionPool(
        connection_class=FakeAsyncRedisConnection, server=FakeServer(), **CLIENT_OPTIONS
    )
    client = Redis(connection_pool=pool)
    yield client
    await client.aclose(close_connection_pool=True)


@pytest.fixture
def repository(redis: Redis, settings: Settings) -> DocumentRepository:
    return DocumentRepository(redis, settings)


@pytest.fixture
def file_store(settings: Settings) -> FileStore:
    return FileStore(settings.upload_dir)


@pytest.fixture
def make_api_client(redis: Redis) -> ApiClientFactory:
    @asynccontextmanager
    async def factory(settings: Settings) -> AsyncIterator[AsyncClient]:
        app = create_app(settings)
        app.dependency_overrides[get_redis] = lambda: redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    return factory


@pytest.fixture
async def api_client(
    make_api_client: ApiClientFactory, settings: Settings
) -> AsyncIterator[AsyncClient]:
    async with make_api_client(settings) as client:
        yield client
