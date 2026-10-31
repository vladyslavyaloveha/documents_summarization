from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedisConnection, FakeServer
from httpx import ASGITransport, AsyncClient
from redis.asyncio import ConnectionPool, Redis

from docparser.api.deps import get_redis
from docparser.api.main import create_app
from docparser.redis_client import CLIENT_OPTIONS


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    pool = ConnectionPool(
        connection_class=FakeAsyncRedisConnection, server=FakeServer(), **CLIENT_OPTIONS
    )
    client = Redis(connection_pool=pool)
    yield client
    await client.aclose(close_connection_pool=True)


@pytest.fixture
async def api_client(redis: Redis) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_redis] = lambda: redis
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
