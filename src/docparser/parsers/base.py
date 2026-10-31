from abc import ABC, abstractmethod
from pathlib import Path

from docparser.config import Settings
from docparser.models import Page


class ParsingError(Exception):
    pass


class BaseParser(ABC):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @abstractmethod
    async def parse(self, pdf_path: Path) -> list[Page]: ...
