from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from docparser.api.routes import health
from docparser.config import get_settings
from docparser.log import configure_logging
from docparser.redis_client import create_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.redis = create_redis(settings)
    try:
        yield
    finally:
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Document Parser", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
