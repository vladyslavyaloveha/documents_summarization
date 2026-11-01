import tomllib
from pathlib import Path
from typing import Any, Final

import pytest

from docparser.config import Settings
from docparser.parsers.base import ParsingError
from docparser.parsers.pypdf_parser import PyPdfParser

EXAMPLES: Final = Path(__file__).parent.parent / "examples"
CASES: Final[dict[str, dict[str, Any]]] = tomllib.loads(
    (EXAMPLES / "expected.toml").read_text(encoding="utf-8")
)


def _expectations(case: dict[str, Any], parser: str) -> dict[str, Any]:
    shared = {key: value for key, value in case.items() if not isinstance(value, dict)}
    override: dict[str, Any] = case.get(parser, {})
    return shared | override


def test_every_example_has_expectations() -> None:
    assert {path.stem for path in EXAMPLES.glob("*.pdf")} == set(CASES)


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(name, marks=[pytest.mark.slow] if case.get("slow") else [])
        for name, case in sorted(CASES.items())
    ],
)
async def test_pypdf_matches_expectations(name: str, settings: Settings) -> None:
    expected = _expectations(CASES[name], "pypdf")
    parser = PyPdfParser(settings)

    if "error" in expected:
        with pytest.raises(ParsingError, match=expected["error"]):
            await parser.parse(EXAMPLES / f"{name}.pdf")
        return

    pages = await parser.parse(EXAMPLES / f"{name}.pdf")
    text = "\n".join(page.markdown for page in pages)

    assert len(pages) == expected["pages"]
    assert [page.number for page in pages] == list(range(1, len(pages) + 1))
    for number in expected.get("blank_pages", []):
        assert pages[number - 1].markdown.strip() == ""
    for fragment in expected.get("contains", []):
        assert fragment in text
    for fragment in expected.get("absent", []):
        assert fragment not in text
    positions = [text.index(fragment) for fragment in expected.get("order", [])]
    assert positions == sorted(positions)
