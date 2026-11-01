from typing import Final

from google.genai.types import HttpRetryOptions
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from docparser.config import Settings

RETRYABLE_STATUS_CODES: Final[list[int]] = [408, 429, 500, 502, 503, 504]


def build_gemini_model(settings: Settings) -> GoogleModel | None:
    if (
        settings.gemini_api_key is None
        or not settings.gemini_api_key.get_secret_value()
    ):
        return None
    provider = GoogleProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        retry_options=HttpRetryOptions(
            attempts=5,
            initial_delay=5.0,
            max_delay=60.0,
            exp_base=2.0,
            http_status_codes=RETRYABLE_STATUS_CODES,
        ),
    )
    return GoogleModel(settings.gemini_model, provider=provider)
