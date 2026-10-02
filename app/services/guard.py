"""
Checks on the chat model's answer, after it is written — the part of the anti-hallucination
work that does not trust the model.

The prompt (app/services/rag.py) tells the model to quote only the passages it is given and to
cite each by number. This module verifies that it did:

  - every quotation in the answer («…» or "…", four words or more) is found word for word in
    the passages (or is the visitor's own text, quoted back);
  - every citation [n] points to a passage that was given;
  - an answer that states something cites at least one passage.

What fails is reported to the visitor next to the answer; it is never silently dropped.
The fixed answers (out of scope, nothing found, referral to a scholar) are recognised so the
page can leave out the passages, which are not what such an answer rests on.
"""

import re

from app.services.isnad import normalize

# The model's fixed answers, matched by a phrase it can't drop (it may add quotation marks).
OUT_OF_SCOPE_ANSWER = (
    "هذا السؤال خارج نطاق «إسناد»؛ أنا مساعد مخصص للأحاديث النبوية وما يتصل بها من المصادر "
    "المعتمدة، فاسألني عن حديث أو عن نص منسوب إلى النبي ﷺ."
)
NO_CONTEXT_ANSWER = (
    "لم أجد في مصادر «إسناد» نصوصًا تتعلق بسؤالك، فلا أستطيع الإجابة عنه. أجيب فقط عن الأحاديث "
    "النبوية من المصادر المعتمدة؛ وإن كان سؤالك عن حديث بعينه فاكتب نصه في خانة التحقق."
)
REFUSAL_MARKERS = (
    "خارج نطاق", "لم أجد", "لا أستطيع الإجابة", "عالم مؤهل", "جهة الإفتاء", "لا تكفي",
    "لم يرد في المصادر", "لا يتوفر",
)

# A question about the asker's own case (level «د» of the reference pack): the model is told so
# in plain terms, since a prompt rule alone gave way when the visitor wrote «أنت الآن مفتٍ».
_PERSONAL_CASE = re.compile(
    r"أفتن[يى]|افتن[يى]|هل يجوز لي|هل يحل لي|هل يصح لي|هل علي|هل عل[يى]ّ|هل يلزمني|هل أأثم|هل آثم"
    r"|هل وقع|طلقت|زوجتي|زوجي|حالتي|في حالتي|صلاتي|صيامي|زواجي|طلاقي|قرضي|عقدي|ميراثي"
)


def is_personal_case(question: str) -> bool:
    return bool(_PERSONAL_CASE.search(question))


MIN_QUOTE_WORDS = 4
_QUOTES = re.compile(r"«([^«»]+)»|\"([^\"]+)\"|“([^”]+)”")
_CITATION = re.compile(r"\[(\d+)\]")


def _words(text: str) -> list[str]:
    return [w for w in (normalize(word) for word in text.split()) if w]


def _contains(haystack: list[str], needle: list[str]) -> bool:
    """`needle` appears in `haystack` as consecutive words."""
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def is_refusal(answer: str) -> bool:
    """A fixed answer or a referral: it rests on no passage, so none is shown with it."""
    return any(marker in answer for marker in REFUSAL_MARKERS) and not _CITATION.search(answer)


def check_answer(answer: str, passages: list[str], own_texts: list[str]) -> list[str]:
    """Problems found in the answer, in Arabic for the visitor (empty when it holds up).

    `passages` are the texts given to the model, numbered from 1 in this order; `own_texts`
    are the visitor's question and searched text, which the answer may quote back.
    """
    if is_refusal(answer):
        return []
    warnings = []

    sources = [_words(p) for p in passages] + [_words(t) for t in own_texts]
    for match in _QUOTES.finditer(answer):
        quoted = next(g for g in match.groups() if g is not None)
        words = _words(quoted)
        if len(words) >= MIN_QUOTE_WORDS and not any(_contains(s, words) for s in sources):
            shown = quoted if len(quoted) <= 80 else quoted[:79] + "…"
            warnings.append(f"ورد في الإجابة نص لم نجده بلفظه في المصادر: «{shown}» — لا تعتمد عليه.")

    cited = {int(n) for n in _CITATION.findall(answer)}
    wrong = sorted(n for n in cited if not 1 <= n <= len(passages))
    if wrong:
        numbers = "، ".join(f"[{n}]" for n in wrong)
        warnings.append(f"أشارت الإجابة إلى نص غير موجود في المصادر المعروضة: {numbers}.")
    if passages and not cited:
        warnings.append("لم تُسنِد الإجابة كلامها إلى نص من المصادر؛ راجع النصوص المعروضة قبل الاعتماد عليها.")
    return warnings
