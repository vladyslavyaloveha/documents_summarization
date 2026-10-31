import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    stream_name: str = "docs:jobs"
    consumer_group: str = "parsers"
    worker_block_ms: PositiveInt = 5000
    worker_heartbeat_path: Path = (
        Path(tempfile.gettempdir()) / "docparser-worker.heartbeat"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
