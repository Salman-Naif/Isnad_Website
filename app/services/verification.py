"""
Verification logic — turning the similarity of the best match into a verdict for the visitor.

The same search produces either a "verified result" or a "distortion warning" depending on
where the similarity falls relative to THRESHOLD_HIGH / THRESHOLD_MID.

A near-exact match is only "verified" when it hits a structured hadith that carries a
scholar's ruling. A near-exact match against an uploaded book only proves the text appears
in that book (which may itself list weak or fabricated narrations), so it is "found".
"""

from app.config import get_settings
from app.models.schemas import Match, MatchType, SanadNode, SearchResult, Verdict
from app.services import isnad


def classify_english(similarity: float, has_ruling: bool, word_overlap: float | None, translated: bool) -> Verdict:
    """An English text: searched through its Arabic rendering, the hadith found is the meaning of
    what the visitor wrote, not the same text; searched as it is, only a strong match counts."""
    if translated:
        verdict = classify(similarity, has_ruling, word_overlap)
        return Verdict.MEANING if verdict in (Verdict.VERIFIED, Verdict.FOUND) else verdict
    return Verdict.DISTORTED if similarity >= get_settings().threshold_cross_lingual else Verdict.NO_MATCH


def classify(similarity: float, has_ruling: bool, word_overlap: float | None = None) -> Verdict:
    settings = get_settings()
    if similarity >= settings.threshold_high:
        return Verdict.VERIFIED if has_ruling else Verdict.FOUND
    if similarity >= settings.threshold_strong:
        return Verdict.DISTORTED
    if similarity >= settings.threshold_mid and (
        word_overlap is None or word_overlap >= settings.min_word_overlap
    ):
        return Verdict.DISTORTED
    return Verdict.NO_MATCH


_MESSAGES = {
    "ar": {
        Verdict.VERIFIED: "وُجد هذا النص في المصادر — حكمه موضّح أدناه",
        Verdict.FOUND: "النص موجود في المصادر، لكن لا يتوفر له حكم موثّق",
        Verdict.DISTORTED: "تنبيه: هذا يشبه نصًا معروفًا بصياغة مختلفة",
        Verdict.MEANING: "وُجد في المصادر حديث بهذا المعنى — هذا لفظه العربي من مصدره",
        Verdict.NO_MATCH: "لا يوجد تطابق قوي في المصادر المعتمدة",
    },
    "en": {
        Verdict.VERIFIED: "This text is in the sources — its ruling is shown below",
        Verdict.FOUND: "This text is in the sources, but no documented ruling is available for it",
        Verdict.DISTORTED: "Caution: this resembles a known hadith, with a different wording or meaning",
        Verdict.MEANING: "A hadith with this meaning is in the sources — shown in its Arabic words, from its source",
        Verdict.NO_MATCH: "No hadith with this meaning was found in the approved sources",
    },
}


def verdict_message(verdict: Verdict, lang: str = "ar") -> str:
    """The verdict in the visitor's language.

    VERIFIED means "we have a documented ruling for this text", not "this hadith is
    authentic" — the ruling itself may be weak or fabricated, so the message points to it.
    """
    return _MESSAGES.get(lang, _MESSAGES["ar"])[verdict]


def build_results(matches: list[Match], query: str = "", lang: str = "ar", translated: bool = False) -> list[SearchResult]:
    """Display-ready results, best match first. For an English text (`lang` "en"), `query` is the
    Arabic it was searched with when `translated`; the visitor's words are not compared with the
    hadith's, which are in another language."""
    results = []
    for m in matches:
        similarity = min(1.0, max(0.0, m.similarity))
        if lang == "en":
            verdict = classify_english(similarity, bool(m.hukm), m.word_overlap, translated)
            words = []
            kind = {Verdict.MEANING: MatchType.MEANING, Verdict.DISTORTED: MatchType.REWORDED}.get(verdict, MatchType.NONE)
        else:
            verdict = classify(similarity, has_ruling=bool(m.hukm), word_overlap=m.word_overlap)
            words = isnad.compare_words(query, m.text) if query else []
            same_text = verdict in (Verdict.VERIFIED, Verdict.FOUND)
            kind = isnad.match_type(similarity, words, same_text, verdict == Verdict.DISTORTED)
        results.append(SearchResult(
            text=m.text,
            similarity=round(similarity, 4),
            word_overlap=m.word_overlap,
            match_type=kind,
            verdict=verdict,
            verdict_message=verdict_message(verdict, lang),
            kind=m.kind,
            hukm=m.hukm,
            mohaddith=m.mohaddith,
            sanad=m.sanad,
            sanad_tree=m.sanad_tree or isnad.chain_tree(m.sanad),
            sanad_extracted=m.sanad_extracted and m.sanad_tree is not None,
            words=words,
            topic=m.topic,
            source=m.source,
            compiler=m.compiler,
        ))
    # A stable sort: equal similarities keep the database's order — a quote found word for word in
    # several books comes in the books' order (al-Bukhari, Muslim, then the Sunan…).
    return sorted(results, key=lambda r: r.similarity, reverse=True)


def merged_isnad(results: list[SearchResult]) -> tuple[SanadNode | None, list[str], bool]:
    """The best match's isnad, merged with the other books' chains of the same text.

    (tree, the books whose chains are in it, whether any chain was read from the wording)
    """
    if not results or results[0].verdict == Verdict.NO_MATCH or results[0].sanad_tree is None:
        return None, [], False
    best = results[0]
    high = get_settings().threshold_high
    # Other books' copies of the same text: only when the best match is that text too.
    same = [best]
    if best.similarity >= high:
        same += [r for r in results[1:] if r.sanad_tree is not None and r.similarity >= high]
    tree = isnad.merge_trees([r.sanad_tree for r in same])
    used = [r for r in same if isnad.same_root(r.sanad_tree, tree)]
    sources = list(dict.fromkeys(r.source for r in used if r.source))
    return tree, sources, any(r.sanad_extracted for r in used)
