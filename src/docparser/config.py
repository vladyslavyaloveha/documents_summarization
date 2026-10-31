import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import NonNegativeInt, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    stream_name: str = "docs:jobs"
    stream_max_length: PositiveInt = 10_000
    consumer_group: str = "parsers"
    document_ttl_seconds: PositiveInt = 7 * 24 * 60 * 60
    upload_dir: Path = Path("data/uploads")
    max_files_per_upload: PositiveInt = 20
    max_upload_size_bytes: PositiveInt = 50 * 1024 * 1024
    dead_letter_stream: str = "docs:jobs:dlq"
    worker_block_ms: PositiveInt = 5000
    worker_concurrency: PositiveInt = 4
    reclaim_idle_ms: NonNegativeInt = 60_000
    max_deliveries: PositiveInt = 3
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_pages_per_chunk: PositiveInt = 10
    summary_max_chars_per_call: PositiveInt = 400_000
    summary_chunk_overlap_chars: NonNegativeInt = 2_000
    worker_heartbeat_path: Path = (
        Path(tempfile.gettempdir()) / "docparser-worker.heartbeat"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
