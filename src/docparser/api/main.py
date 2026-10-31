from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from docparser.api.routes import documents, health
from docparser.config import Settings, get_settings
from docparser.log import configure_logging
from docparser.redis_client import create_redis

MULTIPART_OVERHEAD_BYTES: Final[int] = 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    app.state.redis = create_redis(settings)
    try:
        yield
    finally:
        await app.state.redis.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Document Parser", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_size=settings.max_files_per_upload * settings.max_upload_size_bytes
        + MULTIPART_OVERHEAD_BYTES,
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    return app


app = create_app()
