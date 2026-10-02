"""Unit tests: the match type, the words that differ from the source, and merging isnad trees."""

import pytest

from app.models.schemas import Match, MatchType, Narrator, SanadNode, Verdict
from app.services import isnad
from app.services.verification import build_results, merged_isnad

SOURCE = "إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ، وَإِنَّمَا لِكُلِّ امْرِئٍ مَا نَوَى"


def chain(*names: str) -> SanadNode:
    return isnad.chain_tree([Narrator(name=n) for n in names])


def paths(node: SanadNode) -> list[str]:
    if not node.children:
        return [node.name]
    return [f"{node.name} > {rest}" for child in node.children for rest in paths(child)]


def test_words_are_compared_without_diacritics_or_letter_forms():
    words = isnad.compare_words("انما الاعمال بالنيه وانما لكل امرئ ما نوى", SOURCE)
    assert [w.word for w in words if w.changed] == ["بالنيه"]  # «بالنيات» in the source


def test_a_leading_waw_is_not_a_difference():
    assert not any(w.changed for w in isnad.compare_words("الأعمال وبالنيات", SOURCE))


def test_punctuation_alone_is_never_marked():
    assert not any(w.changed for w in isnad.compare_words("إنما الأعمال بالنيات ،", SOURCE))


@pytest.mark.parametrize(("similarity", "query", "same", "close", "expected"), [
    (1.0, "أي نص", True, False, MatchType.EXACT),  # a literal quote from the database
    (0.95, "إنما الأعمال بالنيات", True, False, MatchType.EXACT),  # every word is in the source
    (0.95, "إنما الأعمال بالنية", True, False, MatchType.CLOSE),
    (0.8, "إنما الأفعال بالنية", False, True, MatchType.REWORDED),
    (0.3, "كلام آخر", False, False, MatchType.NONE),
])
def test_match_type(similarity, query, same, close, expected):
    words = isnad.compare_words(query, SOURCE)
    assert isnad.match_type(similarity, words, same, close) == expected


def test_trees_of_one_hadith_in_two_books_share_their_common_narrators():
    bukhari = chain("النبي ﷺ", "عمر بن الخطاب", "علقمة بن وقاص", "محمد بن إبراهيم", "يحيى بن سعيد",
                    "سفيان", "الحميدي", "البخاري")
    muslim = chain("النبي ﷺ", "عمر بن الخطاب", "علقمة بن وقاص", "محمد بن إبراهيم", "يحيى بن سعيد",
                   "مالك", "عبد الله بن مسلمة", "مسلم")
    tree = isnad.merge_trees([bukhari, muslim])
    assert paths(tree) == [
        "النبي ﷺ > عمر بن الخطاب > علقمة بن وقاص > محمد بن إبراهيم > يحيى بن سعيد > سفيان > الحميدي > البخاري",
        "النبي ﷺ > عمر بن الخطاب > علقمة بن وقاص > محمد بن إبراهيم > يحيى بن سعيد > مالك > عبد الله بن مسلمة > مسلم",
    ]


def test_names_written_differently_are_one_narrator():
    tree = isnad.merge_trees([chain("النبي ﷺ", "أبي هريرة", "الأعرج"), chain("النبي ﷺ", "ابي هريره", "أعرج")])
    assert paths(tree) == ["النبي ﷺ > أبي هريرة > الأعرج"]


def test_a_name_given_in_full_in_one_book_joins_the_shorter_one():
    tree = isnad.merge_trees([chain("النبي ﷺ", "عمر", "يحيى بن سعيد", "سفيان"),
                              chain("النبي ﷺ", "عمر", "يحيى بن سعيد الأنصاري", "مالك")])
    assert paths(tree) == ["النبي ﷺ > عمر > يحيى بن سعيد الأنصاري > سفيان",
                           "النبي ﷺ > عمر > يحيى بن سعيد الأنصاري > مالك"]
    # One word is not enough to say it is the same man.
    tree = isnad.merge_trees([chain("النبي ﷺ", "سفيان"), chain("النبي ﷺ", "سفيان بن عيينة")])
    assert len(tree.children) == 2


def test_a_chain_that_starts_elsewhere_is_left_out():
    tree = isnad.merge_trees([chain("النبي ﷺ", "أنس"), chain("عبد الله بن عمر", "نافع")])
    assert paths(tree) == ["النبي ﷺ > أنس"]
    assert isnad.merge_trees([]) is None


def match(similarity, source, *names, extracted=False):
    return Match(id=source, text=SOURCE, similarity=similarity, kind="structured_hadith", hukm="صحيح",
                 source=source, sanad_tree=chain(*names), sanad_extracted=extracted)


def test_the_page_gets_one_tree_for_the_books_that_have_the_same_text():
    results = build_results([
        match(1.0, "صحيح البخاري", "النبي ﷺ", "عمر بن الخطاب", "البخاري", extracted=True),
        match(0.97, "صحيح مسلم", "النبي ﷺ", "عمر بن الخطاب", "مسلم", extracted=True),
        match(0.7, "سنن النسائي", "النبي ﷺ", "أنس", "النسائي"),  # a different hadith
    ], query="إنما الأعمال بالنيات")
    tree, sources, extracted = merged_isnad(results)
    assert paths(tree) == ["النبي ﷺ > عمر بن الخطاب > البخاري", "النبي ﷺ > عمر بن الخطاب > مسلم"]
    assert sources == ["صحيح البخاري", "صحيح مسلم"]
    assert extracted


def test_a_reworded_text_shows_only_the_tree_of_its_closest_source():
    results = build_results([
        match(0.8, "صحيح البخاري", "النبي ﷺ", "عمر بن الخطاب", "البخاري"),
        match(0.78, "صحيح مسلم", "النبي ﷺ", "عمر بن الخطاب", "مسلم"),
    ], query="إنما الأفعال بالنية")
    assert results[0].verdict == Verdict.DISTORTED
    tree, sources, extracted = merged_isnad(results)
    assert paths(tree) == ["النبي ﷺ > عمر بن الخطاب > البخاري"]
    assert sources == ["صحيح البخاري"] and not extracted


def test_no_tree_without_a_match_or_a_sanad():
    assert merged_isnad([]) == (None, [], False)
    plain = Match(id="d", text="نص", similarity=0.95, kind="document", source="كتاب.pdf")
    assert merged_isnad(build_results([plain])) == (None, [], False)


def test_a_flat_sanad_becomes_a_one_chain_tree():
    [result] = build_results([Match(id="h", text=SOURCE, similarity=0.95, kind="structured_hadith",
                                    sanad=[Narrator(name="النبي ﷺ"), Narrator(name="عمر", grade="صحابي")])])
    assert paths(result.sanad_tree) == ["النبي ﷺ > عمر"]
    assert result.sanad_tree.children[0].grade == "صحابي"
    assert result.sanad_extracted is False
