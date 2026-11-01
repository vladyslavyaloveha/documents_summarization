from collections.abc import Sequence
from typing import Final

from fast_langdetect.infer import detect
from pydantic import BaseModel

from docparser.models import Page

FALLBACK_LANGUAGE: Final[str] = "EN"
MIN_PAGE_CHARS: Final[int] = 50
MIN_CONFIDENCE: Final[float] = 0.5
TIE_RATIO: Final[float] = 0.9


class DetectedLanguage(BaseModel):
    code: str
    mixed: list[str] = []


def detect_language(pages: Sequence[Page]) -> DetectedLanguage:
    weights: dict[str, int] = {}
    first_page: dict[str, int] = {}
    for index, page in enumerate(pages):
        text = " ".join(page.markdown.split())
        if len(text) < MIN_PAGE_CHARS:
            continue
        best = detect(text, model="lite")[0]
        if float(best["score"]) < MIN_CONFIDENCE:
            continue
        code = str(best["lang"]).upper()
        weights[code] = weights.get(code, 0) + len(text)
        first_page.setdefault(code, index)

    if not weights:
        return DetectedLanguage(code=FALLBACK_LANGUAGE)
    top_weight = max(weights.values())
    leaders = sorted(
        (code for code, weight in weights.items() if weight >= top_weight * TIE_RATIO),
        key=first_page.__getitem__,
    )
    if len(leaders) == 1:
        return DetectedLanguage(code=leaders[0])
    return DetectedLanguage(code=leaders[0], mixed=leaders)
