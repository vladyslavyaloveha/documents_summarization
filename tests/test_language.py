from typing import Final

from docparser.language import DetectedLanguage, detect_language
from docparser.models import Page

ENGLISH: Final = (
    "Whereas recognition of the inherent dignity and of the equal and inalienable "
    "rights of all members of the human family is the foundation of freedom."
)
GERMAN: Final = (
    "Da die Anerkennung der angeborenen Würde und der gleichen und unveräußerlichen "
    "Rechte aller Mitglieder der Gemeinschaft der Menschen die Grundlage bildet."
)
ITALIAN: Final = (
    "Considerato che il riconoscimento della dignità inerente a tutti i membri della "
    "famiglia umana costituisce il fondamento della libertà e della giustizia."
)


def _pages(*texts: str) -> list[Page]:
    return [Page(number=index, markdown=text) for index, text in enumerate(texts, 1)]


def test_single_language_document() -> None:
    assert detect_language(_pages(GERMAN, GERMAN)) == DetectedLanguage(code="DE")


def test_clear_majority_wins() -> None:
    pages = _pages(ENGLISH, ITALIAN, ITALIAN, ITALIAN)

    assert detect_language(pages) == DetectedLanguage(code="IT")


def test_near_tie_picks_the_language_seen_first() -> None:
    pages = _pages(GERMAN, ITALIAN, GERMAN, ITALIAN)

    assert detect_language(pages) == DetectedLanguage(code="DE", mixed=["DE", "IT"])


def test_longer_pages_weigh_more() -> None:
    pages = _pages(ENGLISH, GERMAN + " " + GERMAN + " " + GERMAN)

    assert detect_language(pages).code == "DE"


def test_short_pages_are_ignored() -> None:
    pages = _pages("Seite 1", "Pagina 2", ENGLISH)

    assert detect_language(pages) == DetectedLanguage(code="EN")


def test_no_usable_text_falls_back_to_english() -> None:
    assert detect_language(_pages("", "12 34", "   ")) == DetectedLanguage(code="EN")
    assert detect_language([]) == DetectedLanguage(code="EN")
