"""
Verification logic — turning the similarity of the best match into a verdict for the visitor.

The same search produces either a "verified result" or a "distortion warning" depending on
where the similarity falls relative to THRESHOLD_HIGH / THRESHOLD_MID.

A near-exact match is only "verified" when it hits a structured hadith that carries a
scholar's ruling. A near-exact match against an uploaded book only proves the text appears
in that book (which may itself list weak or fabricated narrations), so it is "found".
"""

from app.config import get_settings
from app.models.schemas import Match, SanadNode, SearchResult, Verdict
from app.services import isnad


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


def verdict_message(verdict: Verdict) -> str:
    """Arabic text shown to the visitor.

    VERIFIED means "we have a documented ruling for this text", not "this hadith is
    authentic" — the ruling itself may be weak or fabricated, so the message points to it.
    """
    return {
        Verdict.VERIFIED: "وُجد هذا النص في المصادر — حكمه موضّح أدناه",
        Verdict.FOUND: "النص موجود في المصادر، لكن لا يتوفر له حكم موثّق",
        Verdict.DISTORTED: "تنبيه: هذا يشبه نصًا معروفًا بصياغة مختلفة",
        Verdict.NO_MATCH: "لا يوجد تطابق قوي في المصادر المعتمدة",
    }[verdict]


def build_results(matches: list[Match], query: str = "") -> list[SearchResult]:
    """Display-ready results, best match first."""
    results = []
    for m in matches:
        similarity = min(1.0, max(0.0, m.similarity))
        verdict = classify(similarity, has_ruling=bool(m.hukm), word_overlap=m.word_overlap)
        words = isnad.compare_words(query, m.text) if query else []
        same_text = verdict in (Verdict.VERIFIED, Verdict.FOUND)
        results.append(SearchResult(
            text=m.text,
            similarity=round(similarity, 4),
            word_overlap=m.word_overlap,
            match_type=isnad.match_type(similarity, words, same_text, verdict == Verdict.DISTORTED),
            verdict=verdict,
            verdict_message=verdict_message(verdict),
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
