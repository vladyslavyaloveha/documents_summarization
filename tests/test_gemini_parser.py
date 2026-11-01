from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from docparser.config import Settings
from docparser.models import Page
from docparser.parsers.base import ParsingError
from docparser.parsers.gemini_parser import GeminiParser, _split_pages


async def test_converts_each_chunk_and_numbers_pages(
    tmp_path: Path, settings: Settings, sample_pdf: bytes
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(sample_pdf)
    one_page_chunks = settings.model_copy(update={"gemini_pages_per_chunk": 1})
    model = TestModel(custom_output_text="=== PAGE 1 ===\n# Greeting\n")

    pages = await GeminiParser(one_page_chunks, model).parse(pdf_path)

    assert pages == [
        Page(number=1, markdown="# Greeting"),
        Page(number=2, markdown="# Greeting"),
    ]


async def test_is_unavailable_without_api_key(
    tmp_path: Path, settings: Settings, sample_pdf: bytes
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(sample_pdf)

    with pytest.raises(ParsingError, match="GEMINI_API_KEY"):
        await GeminiParser(settings).parse(pdf_path)


def test_splits_output_on_page_markers() -> None:
    output = "=== PAGE 1 ===\n# One\n=== PAGE 2 ===\n\n=== PAGE 3 ===\nThree"

    assert _split_pages(output, 3) == ["# One", "", "Three"]


def test_output_without_markers_goes_to_the_first_page() -> None:
    assert _split_pages("Just text", 2) == ["Just text", ""]


async def test_api_error_in_any_chunk_fails_the_document(
    tmp_path: Path, settings: Settings, sample_pdf: bytes
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(sample_pdf)
    one_page_chunks = settings.model_copy(update={"gemini_pages_per_chunk": 1})

    def unavailable(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=503, model_name="gemini")

    with pytest.raises(ParsingError, match="HTTP 503"):
        await GeminiParser(one_page_chunks, FunctionModel(unavailable)).parse(pdf_path)
