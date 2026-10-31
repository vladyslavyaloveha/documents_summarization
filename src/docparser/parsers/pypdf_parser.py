import asyncio
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PyPdfError

from docparser.models import Page
from docparser.parsers.base import BaseParser, ParsingError


class PyPdfParser(BaseParser):
    async def parse(self, pdf_path: Path) -> list[Page]:
        return await asyncio.to_thread(_extract_pages, pdf_path)


def _extract_pages(pdf_path: Path) -> list[Page]:
    try:
        reader = PdfReader(pdf_path)
        return [
            Page(number=number, markdown=page.extract_text())
            for number, page in enumerate(reader.pages, start=1)
        ]
    except FileNotDecryptedError as exc:
        raise ParsingError("The PDF is protected by a password") from exc
    except PyPdfError as exc:
        raise ParsingError("The file is not a readable PDF") from exc
