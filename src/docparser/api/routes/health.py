import asyncio
import logging
from typing import Final, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.exceptions import RedisError

from docparser.api.deps import RedisDep

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

READINESS_TIMEOUT_SECONDS: Final[int] = 10


class HealthStatus(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get("/health")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready", responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthStatus}}
)
async def ready(redis: RedisDep, response: Response) -> HealthStatus:
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
            await redis.ping()
    except (RedisError, TimeoutError):
        logger.warning("Readiness check failed: Redis is unreachable", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="unavailable")
    return HealthStatus(status="ok")
