"""
English queries: told apart from Arabic ones, and turned into Arabic to be searched.

The books are Arabic. An English text is searched through an Arabic rendering made by the chat
model — of the visitor's text only: the page then shows what the sources hold (the hadith's own
Arabic words, its book and its ruling), never a translation of a hadith. Measured on 41 hadiths
as they circulate in English and 26 sayings that none of the books holds: 38 found with the right
hadith first, 25 reported as not in the sources (docs/evaluation/verification.md). Searching the
English text directly found far fewer (its similarities to hadiths and to unrelated texts
overlap), so it is only the fallback when the model can't be reached.
"""

import re
from collections import OrderedDict
from threading import Lock
from typing import Literal

Lang = Literal["ar", "en"]

_LATIN = re.compile(r"[A-Za-z]")
_ARABIC = re.compile(r"[ء-ي]")
MIN_LATIN_LETTERS = 3

TRANSLATION_PROMPT = (
    "Translate the user's text into Arabic, to be searched for in the books of hadith. If it renders "
    "a hadith or a saying attributed to the Prophet ﷺ, write it the way it is worded in Arabic; "
    "otherwise translate it literally. Do not replace it with a different hadith that only resembles "
    "it in meaning. Do not add, explain or correct anything, and do not say whether it is authentic. "
    "Reply with the Arabic text only."
)
# A question is not a text to find: rendered word for word. Rendered with the prompt above,
# «Who narrated the hadith about intentions?» became the words of another hadith
# («من عمل عملًا ليس عليه أمرنا فهو رد»), and the chat searched for that one.
QUESTION_PROMPT = (
    "Translate the user's question into Arabic, word for word, to search the books of hadith with. "
    "Keep any hadith or topic it mentions as it names it, and never replace the question with the "
    "text of a hadith. Do not answer it, explain it or say whether anything is authentic. Reply "
    "with the Arabic question only."
)


def language_of(text: str) -> Lang:
    """English when Latin letters outnumber Arabic ones; Arabic otherwise (the default)."""
    latin = len(_LATIN.findall(text))
    return "en" if latin >= MIN_LATIN_LETTERS and latin > len(_ARABIC.findall(text)) else "ar"


def looks_arabic(text: str) -> bool:
    """A rendering worth searching: mostly Arabic letters."""
    return len(_ARABIC.findall(text)) > len(_LATIN.findall(text))


class TranslationCache:
    """The last renderings made, so a repeated query costs no second model call."""

    def __init__(self, size: int = 512) -> None:
        self._items: OrderedDict[str, str] = OrderedDict()
        self._size = size
        self._lock = Lock()

    def get(self, text: str) -> str | None:
        with self._lock:
            if text in self._items:
                self._items.move_to_end(text)
                return self._items[text]
        return None

    def put(self, text: str, arabic: str) -> None:
        with self._lock:
            self._items[text] = arabic
            self._items.move_to_end(text)
            while len(self._items) > self._size:
                self._items.popitem(last=False)
