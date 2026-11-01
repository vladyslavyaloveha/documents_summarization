from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from docparser.api.deps import get_redis
from docparser.api.main import create_app


async def test_health_is_ok_without_dependencies(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_redis_answers(api_client: AsyncClient) -> None:
    response = await api_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_not_ready_when_redis_is_unreachable() -> None:
    app = create_app()
    app.dependency_overrides[get_redis] = lambda: FakeAsyncRedis(connected=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
