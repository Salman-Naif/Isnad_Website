"""
One result per hadith: the same hadith comes back from several books (and al-Bukhari repeats
one in several chapters), each copy with its own chain. The copies are shown once, under the
closest one, with the other books it is in.

Two texts are the same hadith when their own words (after the chain: from the first mention
of the Prophet ﷺ on) share at least SAME_SHARE of the shorter one's words.
"""

import re

from app.services.isnad import normalize

SAME_SHARE = 0.8
# A query this short names a subject («فضل الأم»): the database ranks its closest texts by the
# subject's words in them too, so its order is kept (not re-sorted by similarity alone).
SUBJECT_MAX_WORDS = 6
# Fewer words than this are compared whole: a few words in common don't make one hadith.
MIN_WORDS = 5
_PROPHET = re.compile(r"صلي الله عليه وسلم")
# The words that introduce the hadith's own words (compared normalized: ة → ه).
_LEAD = {"قال", "قالت", "فقال", "فقالت", "وقال", "يقول", "انه"}


def is_subject(query: str) -> bool:
    return 0 < len(query.split()) <= SUBJECT_MAX_WORDS


def _own_words(text: str) -> list[str]:
    words = [w for w in (normalize(w) for w in text.replace("ﷺ", " صلى الله عليه وسلم ").split()) if w]
    joined = " ".join(words)
    found = _PROPHET.search(joined)
    if not found:
        return words
    own = joined[found.end():].split()
    while own and own[0] in _LEAD:
        own.pop(0)
    return own


def same_hadith(a: str, b: str) -> bool:
    wa, wb = _own_words(a), _own_words(b)
    if min(len(wa), len(wb)) < MIN_WORDS:
        return wa == wb
    common = len(set(wa) & set(wb))
    return common / min(len(set(wa)), len(set(wb))) >= SAME_SHARE


def group(results: list, limit: int) -> list:
    """The results, closest first, each hadith once; its other copies' books in `also_in`."""
    kept: list = []
    words: list[str] = []
    for result in results:
        first = next((k for k, text in zip(kept, words, strict=True) if same_hadith(text, result.text)), None)
        if first is None:
            kept.append(result)
            words.append(result.text)
        elif result.source and result.source != first.source and result.source not in first.also_in:
            first.also_in.append(result.source)
    return kept[:limit]
