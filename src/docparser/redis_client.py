from typing import Any, Final

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialWithJitterBackoff

from docparser.config import Settings

CLIENT_OPTIONS: Final[dict[str, Any]] = {
    "decode_responses": True,
    "protocol": 3,
    "legacy_responses": False,
}
SOCKET_TIMEOUT_MARGIN_SECONDS: Final[float] = 5.0
RETRY_ATTEMPTS: Final[int] = 5


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        **CLIENT_OPTIONS,
        socket_timeout=settings.worker_block_ms / 1000 + SOCKET_TIMEOUT_MARGIN_SECONDS,
        retry=Retry(ExponentialWithJitterBackoff(base=0.1, cap=5), RETRY_ATTEMPTS),
    )
