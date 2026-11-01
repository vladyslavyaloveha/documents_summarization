import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from docparser.config import Settings
from docparser.models import Page
from docparser.parsers.base import ParsingError
from docparser.parsers.pypdf_parser import PyPdfParser


async def test_extracts_text_page_by_page(
    tmp_path: Path, settings: Settings, sample_pdf: bytes
) -> None:
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(sample_pdf)

    pages = await PyPdfParser(settings).parse(pdf_path)

    assert pages == [
        Page(number=1, markdown="Hello from the first page"),
        Page(number=2, markdown="Hello from the second page"),
    ]


async def test_rejects_password_protected_pdf(
    tmp_path: Path, settings: Settings, sample_pdf: bytes
) -> None:
    writer = PdfWriter(clone_from=io.BytesIO(sample_pdf))
    writer.encrypt(user_password="secret", algorithm="AES-256")
    pdf_path = tmp_path / "locked.pdf"
    writer.write(pdf_path)

    with pytest.raises(ParsingError, match="password"):
        await PyPdfParser(settings).parse(pdf_path)


async def test_rejects_corrupted_pdf(tmp_path: Path, settings: Settings) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nthis is not a real pdf")

    with pytest.raises(ParsingError, match="readable"):
        await PyPdfParser(settings).parse(pdf_path)
