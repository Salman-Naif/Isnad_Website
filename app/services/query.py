"""
What a visitor's text is searched as: Arabic as written, English through an Arabic rendering
(app/services/language.py). If the model can't make one, the English text is searched as it
is, and only a strong match counts (see app/services/verification.py).

A chat question is rendered word for word (never as the hadith it asks about), and what it is
about is searched too: «من روى حديث النية؟» names «النية», while its own words («روى»، «حديث»)
land near the scholars' notes on chains («وروى شيبان…») rather than on the hadith.
"""

import re

from app.services.language import Lang, language_of
from app.services.rag import RAGError, RAGService

SUBJECT_MAX_WORDS = 6  # the database's own limit for a subject (grouping.SUBJECT_MAX_WORDS)

# Words that frame a question about hadith rather than name its subject, after _bare().
_FRAMING = {
    "من", "ما", "ماذا", "هل", "كيف", "لماذا", "لم", "متي", "اين", "كم", "اي", "ايش", "وش",
    "روي", "رواه", "رواها", "يروي", "اخرج", "اخرجه", "خرجه", "صحح", "صححه", "ضعف", "ضعفه",
    "حديث", "الحديث", "احاديث", "الاحاديث", "حديثا", "نص", "النص", "لفظ", "لفظه",
    "حكم", "حكمه", "معني", "معناه", "شرح", "تفسير", "درجه", "درجته", "صحه", "صحيح", "ضعيف", "سند", "سنده",
    "ورد", "وردت", "جاء", "جاءت", "يوجد", "هناك", "في", "عن", "علي", "الي", "او", "و",
    "النبي", "الرسول", "رسول", "هذا", "هذه", "ذلك", "تلك", "الذي", "التي", "قال", "يقول", "قول", "قوله",
    "اذكر", "اعطني", "اريد", "ابي", "ابغي", "ممكن", "لو", "سمحت",
}
_PROPHET = re.compile(r"ﷺ|صلي الله عليه وسلم|رسول الله")
_DIACRITICS = re.compile(r"[ً-ٰٟ]")
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""})


def _bare(text: str) -> str:
    return _DIACRITICS.sub("", text).translate(_LETTERS)


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


def for_question(question: str, rag: RAGService) -> str:
    """A chat question to search with: Arabic as written, English rendered word for word."""
    if language_of(question) == "ar":
        return question
    try:
        return rag.to_arabic(question, question=True)
    except RAGError:
        return question


def subject_of(question: str) -> str:
    """What an Arabic question is about, without the words that frame it: «من روى حديث النية؟»
    → «النية». Empty when nothing is left («من رواه؟») or too much to be a subject."""
    words = re.sub(r"[^\w\s]", " ", _PROPHET.sub(" ", _bare(question))).split()
    # «وما», «ومن»: the conjunction joined to a framing word frames too.
    subject = [w for w in words if w not in _FRAMING and not (w[0] == "و" and w[1:] in _FRAMING)]
    if not subject or len(subject) > SUBJECT_MAX_WORDS:
        return ""
    return " ".join(subject)
