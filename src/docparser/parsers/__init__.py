from docparser.config import Settings
from docparser.models import ParserType
from docparser.parsers.base import BaseParser
from docparser.parsers.gemini_parser import GeminiParser
from docparser.parsers.pypdf_parser import PyPdfParser


def get_parser(parser_type: ParserType, settings: Settings) -> BaseParser:
    match parser_type:
        case ParserType.PYPDF:
            return PyPdfParser(settings)
        case ParserType.GEMINI:
            return GeminiParser(settings)


def available_parsers(settings: Settings) -> list[ParserType]:
    has_gemini_key = settings.gemini_api_key is not None and bool(
        settings.gemini_api_key.get_secret_value()
    )
    return [
        parser
        for parser in ParserType
        if parser is not ParserType.GEMINI or has_gemini_key
    ]
