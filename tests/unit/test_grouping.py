"""Unit tests: the same hadith from several books is one result."""

import pytest

from app.models.schemas import ExploreResult
from app.services.grouping import group, is_subject, same_hadith

pytestmark = pytest.mark.unit

MATN = "قال رسول الله ﷺ من أحق الناس بحسن صحابتي قال أمك ثم أمك ثم أمك ثم أبوك"


def result(text, source, similarity=0.8):
    return ExploreResult(text=text, similarity=similarity, kind="structured_hadith", source=source)


def test_the_same_words_under_different_chains_are_one_hadith():
    assert same_hadith("حدثنا قتيبة عن أبي هريرة " + MATN, "أخبرنا زهير عن أبي زرعة عن أبي هريرة " + MATN)


def test_different_hadiths_on_one_subject_are_not():
    assert not same_hadith(MATN, "قال النبي ﷺ الجنة تحت أقدام الأمهات وبر الوالدين من أعظم القربات")


def test_short_texts_must_be_the_same_words():
    assert same_hadith("قال ﷺ الدين النصيحة", "عن تميم أن النبي ﷺ قال الدين النصيحة")
    assert not same_hadith("قال ﷺ الدين النصيحة", "قال ﷺ الدين يسر")


def test_group_keeps_the_closest_copy_and_lists_the_other_books_once():
    results = group([result(MATN, "صحيح البخاري"), result(MATN, "صحيح مسلم"), result(MATN, "صحيح البخاري"),
                     result(MATN, "صحيح مسلم"), result("قال ﷺ الدين النصيحة", "صحيح مسلم")], limit=5)
    assert [(r.source, r.also_in) for r in results] == [("صحيح البخاري", ["صحيح مسلم"]), ("صحيح مسلم", [])]


def test_group_trims_to_the_limit():
    texts = ["قال ﷺ الدين النصيحة", "قال ﷺ الدين يسر", "قال ﷺ الحياء من الإيمان", "قال ﷺ الطهور شطر الإيمان"]
    assert len(group([result(text, "كتاب") for text in texts], limit=2)) == 2


def test_a_subject_is_a_few_words():
    assert is_subject("فضل الأم") and not is_subject("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى")
