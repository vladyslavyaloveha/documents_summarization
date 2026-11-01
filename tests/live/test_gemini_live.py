import re
from pathlib import Path
from typing import Final

import pytest

from docparser.config import Settings
from docparser.language import detect_language
from docparser.llm.summarizer import Summarizer, build_summarizer
from docparser.parsers.pypdf_parser import PyPdfParser

pytestmark = pytest.mark.live

EXAMPLES: Final = Path(__file__).parent.parent.parent / "examples"
LANGUAGE_MARKERS: Final[dict[str, re.Pattern[str]]] = {
    "text": re.compile(r"\b(the|and|of)\b", re.IGNORECASE),
    "german": re.compile(r"\b(der|die|und|das)\b", re.IGNORECASE),
    "italian": re.compile(r"\b(della|dei|il|che)\b", re.IGNORECASE),
}
ENGLISH_WORDS: Final = re.compile(r"\b(the|and|which)\b", re.IGNORECASE)
SETTINGS: Final = Settings()


def _summarizer() -> Summarizer:
    summarizer = build_summarizer(SETTINGS)
    if summarizer is None:
        pytest.fail("Set GEMINI_API_KEY in .env to run live tests")
    return summarizer


async def test_gemini_summarizes_text() -> None:
    summary = await _summarizer().summarize(
        "Redis Streams is an append-only log data structure. Consumer groups let "
        "several workers share the entries of one stream, and every entry stays "
        "pending until a worker acknowledges it with XACK.",
        "EN",
    )

    assert "stream" in summary.lower()


@pytest.mark.parametrize("name", sorted(LANGUAGE_MARKERS))
async def test_summary_uses_the_document_language(name: str) -> None:
    pages = await PyPdfParser(SETTINGS).parse(EXAMPLES / f"{name}.pdf")
    text = "\n\n".join(page.markdown for page in pages)

    language = detect_language(pages)
    summary = await _summarizer().summarize(text, language.code)

    assert LANGUAGE_MARKERS[name].search(summary)
    if name != "text":
        assert not ENGLISH_WORDS.search(summary)
