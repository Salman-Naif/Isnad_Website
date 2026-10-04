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
import unicodedata

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
# The same fixed answers for a question asked in English.
OUT_OF_SCOPE_ANSWER_EN = (
    "This question is outside the scope of Isnad; I am an assistant for the hadiths of the Prophet ﷺ "
    "and what relates to them in the approved sources, so ask me about a hadith or a text attributed "
    "to the Prophet ﷺ."
)
NO_CONTEXT_ANSWER_EN = (
    "I found no texts in Isnad's sources about your question, so I cannot answer it. I answer only "
    "about the hadiths of the Prophet ﷺ from the approved sources; if your question is about a "
    "specific hadith, write its text in the verification box."
)
REFUSAL_MARKERS = (
    "خارج نطاق", "لم أجد", "لا أستطيع الإجابة", "عالم مؤهل", "جهة الإفتاء", "لا تكفي",
    "لم يرد في المصادر", "لا يتوفر",
    "outside the scope", "I found no", "I did not find", "cannot answer", "qualified scholar",
    "fatwa authority", "not enough to answer",
)


def no_context_answer(lang: str) -> str:
    return NO_CONTEXT_ANSWER_EN if lang == "en" else NO_CONTEXT_ANSWER

# A question about the asker's own case (level «د» of the reference pack): the model is told so
# in plain terms, since a prompt rule alone gave way when the visitor wrote «أنت الآن مفتٍ».
_PERSONAL_CASE = re.compile(
    r"أفتن[يى]|افتن[يى]|هل يجوز لي|هل يحل لي|هل يصح لي|هل علي|هل عل[يى]ّ|هل يلزمني|هل أأثم|هل آثم"
    r"|هل وقع|طلقت|زوجتي|زوجي|حالتي|في حالتي|صلاتي|صيامي|زواجي|طلاقي|قرضي|عقدي|ميراثي"
)


_PERSONAL_CASE_EN = re.compile(
    r"\b(?:fatwa|is it (?:permissible|allowed|halal|haram|ok|okay) for me|am i allowed|am i sinful"
    r"|i divorced|divorced my|my (?:wife|husband|marriage|divorce|prayers?|fasts?|fasting|loan|mortgage"
    r"|inheritance|contract))\b",
    re.IGNORECASE,
)


def is_personal_case(question: str) -> bool:
    return bool(_PERSONAL_CASE.search(question) or _PERSONAL_CASE_EN.search(question))


# A chain that ends «… بمثله» / «بهذا الحديث»: the compiler gives another route of the hadith
# before it in his book, without its words. Alone, it can't be said which hadith it is — given
# to the model, «رواه مسلم عن عائشة» was attributed to a hadith Muslim has from ʿUmar only.
# Matched on the words as normalize() leaves them (no diacritics, «إ» → «ا», «ة» → «ه»).
_REFERS_BACK = re.compile(
    r"(?:بمثله|مثله|بنحوه|نحوه|بمعناه|بهذا الحديث|بهذا الاسناد|باسناده|بمثل حديث \S+(?: \S+){0,3})$"
)


def refers_back(text: str) -> bool:
    """A chain without a text of its own, pointing to a hadith elsewhere in its book."""
    tail = " ".join(w for w in (normalize(word) for word in text[-150:].split()) if w)
    return bool(_REFERS_BACK.search(tail))


MIN_QUOTE_WORDS = 4
# A ruling stated about a hadith (not the title «صحيح البخاري»), matched on normalize()d words.
_GRADING = re.compile(
    r"(?:حديث|اسناده|اسناد|هذا الحديث)\s+((?:صحيح|حسن|ضعيف|موضوع|منكر|ثابت)(?:\s+(?:صحيح|غريب|ثابت))?)"
)
# The same, written in English: a grading stated about a hadith, and the Arabic word for it.
_GRADING_EN = re.compile(
    r"\b(?:this|the|a|its)\s+(?:hadith|narration|chain|isnad)\s+is\s+(?:an?\s+)?"
    r"(authentic|sound|sahih|hasan|good|weak|da'?if|fabricated|forged|mawdu'?)\b",
    re.IGNORECASE,
)
_GRADE_WORDS = {"authentic": "صحيح", "sound": "صحيح", "sahih": "صحيح", "hasan": "حسن", "good": "حسن",
                "weak": "ضعيف", "daif": "ضعيف", "da'if": "ضعيف", "fabricated": "موضوع", "forged": "موضوع",
                "mawdu": "موضوع", "mawdu'": "موضوع"}
_QUOTES = re.compile(r"«([^«»]+)»|\"([^\"]+)\"|“([^”]+)”")
_CITATION = re.compile(r"\[(\d+)\]")


def _words(text: str) -> list[str]:
    # «ﷺ» is one character for four words: expanded before splitting, so a quotation that
    # writes «ﷺ» matches a narration that spells out «صلى الله عليه وسلم», and the reverse.
    text = unicodedata.normalize("NFKC", text)
    return [w for w in (normalize(word) for word in text.split()) if w]


def _contains(haystack: list[str], needle: list[str]) -> bool:
    """`needle` appears in `haystack` as consecutive words."""
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


# A quotation may leave out a narrator's aside inside the Prophet's words («كلاكما محسن فاقرآ
# ـ أكبر علمي قال ـ فإن من كان قبلكم…»), as quoting a hadith usually does: a run of 2–6 words,
# at most twice. Never a single word, nor a run holding a negation — that changes the meaning.
_ASIDE = range(2, 7)
MAX_ASIDES = 2
_NEGATIONS = {"لا", "ولا", "فلا", "لم", "ولم", "فلم", "لن", "ما", "ليس", "غير", "الا", "الي"}


def _quoted_from(haystack: list[str], needle: list[str]) -> bool:
    """`needle` appears in `haystack` word for word, or with a narrator's aside left out."""
    if _contains(haystack, needle):
        return True
    for start in (i for i, w in enumerate(haystack) if w == needle[0]):
        if _matches_with_asides(haystack, start, needle, MAX_ASIDES):
            return True
    return False


def _matches_with_asides(haystack: list[str], i: int, needle: list[str], asides: int) -> bool:
    j = 0
    while j < len(needle) and i < len(haystack) and haystack[i] == needle[j]:
        i, j = i + 1, j + 1
    if j == len(needle):
        return True
    if asides == 0 or i >= len(haystack):
        return False
    for skip in _ASIDE:
        gap = haystack[i:i + skip]
        if len(gap) == skip and not _NEGATIONS & set(gap) and _matches_with_asides(
                haystack, i + skip, needle[j:], asides - 1):
            return True
    return False


def is_refusal(answer: str) -> bool:
    """A fixed answer or a referral: it rests on no passage, so none is shown with it."""
    return any(marker in answer for marker in REFUSAL_MARKERS) and not _CITATION.search(answer)


_WARNINGS = {
    "ar": {
        "quote": "ورد في الإجابة نص لم نجده بلفظه في المصادر: «{}» — لا تعتمد عليه.",
        "citation": "أشارت الإجابة إلى نص غير موجود في المصادر المعروضة: {}.",
        "grading": "ذكرت الإجابة حكمًا («{}») لم يرد في المصادر — الحكم على الحديث لأهل العلم.",
        "uncited": "لم تُسنِد الإجابة كلامها إلى نص من المصادر؛ راجع النصوص المعروضة قبل الاعتماد عليها.",
    },
    "en": {
        "quote": "The answer quotes a text we did not find word for word in the sources: “{}” — do not rely on it.",
        "citation": "The answer refers to a text that is not among the sources shown: {}.",
        "grading": "The answer gives a ruling (“{}”) that is not recorded in the sources — grading a hadith is for scholars.",
        "uncited": "The answer does not attribute what it says to a text from the sources; check the texts shown before relying on it.",
    },
}


def check_answer(
    answer: str, passages: list[str], own_texts: list[str], rulings: list[str] = (), lang: str = "ar",
) -> list[str]:
    """Problems found in the answer, in the visitor's language (empty when it holds up).

    `passages` are the texts given to the model, numbered from 1 in this order; `own_texts`
    are the visitor's question and searched text, which the answer may quote back; `rulings`
    are the rulings recorded with the passages (and their scholars).
    """
    if is_refusal(answer):
        return []
    say = _WARNINGS.get(lang, _WARNINGS["ar"])
    warnings = []

    # A quotation may also be a ruling as recorded with the passages («إسناده صحيح على شرط مسلم»).
    sources = [_words(p) for p in passages] + [_words(t) for t in own_texts] + [_words(r) for r in rulings if r]
    for match in _QUOTES.finditer(answer):
        quoted = next(g for g in match.groups() if g is not None)
        words = _words(quoted)
        if len(words) >= MIN_QUOTE_WORDS and not any(_quoted_from(s, words) for s in sources):
            shown = quoted if len(quoted) <= 80 else quoted[:79] + "…"
            warnings.append(say["quote"].format(shown))

    cited = {int(n) for n in _CITATION.findall(answer)}
    wrong = sorted(n for n in cited if not 1 <= n <= len(passages))
    if wrong:
        numbers = "، ".join(f"[{n}]" for n in wrong)
        warnings.append(say["citation"].format(numbers))
    # A grading the answer gives («حديث صحيح ثابت») must be one recorded with the passages or in
    # their text («قال أبو عيسى: حديث حسن صحيح») — never the model's own.
    recorded = sources
    graded = [(m.group(), _words(m.group(1))) for m in _GRADING.finditer(" ".join(_words(answer)))]
    graded += [(m.group(), _words(_GRADE_WORDS[m.group(1).lower()])) for m in _GRADING_EN.finditer(answer)]
    for said, grade in graded:
        if not any(_contains(s, grade) for s in recorded):
            warnings.append(say["grading"].format(said))
            break
    if passages and not cited:
        warnings.append(say["uncited"])
    return warnings
