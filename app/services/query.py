"""
What a visitor's text is searched as: Arabic as written, English through an Arabic rendering
(app/services/language.py). If the model can't make one, the English text is searched as it
is, and only a strong match counts (see app/services/verification.py).
"""

from app.services.language import Lang, language_of
from app.services.rag import RAGError, RAGService


def for_search(text: str, rag: RAGService) -> tuple[str, Lang, str | None]:
    """(the text to search, the visitor's language, the Arabic rendering searched, if any)."""
    lang = language_of(text)
    if lang == "ar":
        return text, lang, None
    try:
        arabic = rag.to_arabic(text)
    except RAGError:
        return text, lang, None
    return arabic, lang, arabic
