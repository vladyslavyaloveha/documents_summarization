from docparser.config import Settings
from docparser.models import ParserType
from docparser.parsers.base import BaseParser
from docparser.parsers.pypdf_parser import PyPdfParser


def get_parser(parser_type: ParserType, settings: Settings) -> BaseParser:
    match parser_type:
        case ParserType.PYPDF:
            return PyPdfParser(settings)
