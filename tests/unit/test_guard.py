"""Unit tests: the check on the chat model's answer (quotations, citations, refusals)."""

import pytest

from app.services import guard
from app.services.rag import SYSTEM_PROMPT

PASSAGES = [
    "حَدَّثَنَا الْحُمَيْدِيُّ قَالَ سَمِعْتُ رَسُولَ اللَّهِ صلى الله عليه وسلم يَقُولُ « إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ »",
    "مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الآخِرِ فَلْيَقُلْ خَيْرًا أَوْ لِيَصْمُتْ",
]


def test_a_faithful_answer_passes():
    answer = "قال النبي ﷺ: «من كان يؤمن بالله واليوم الآخر فليقل خيرا أو ليصمت» [2]، ومعناه الحث على حفظ اللسان."
    assert guard.check_answer(answer, PASSAGES, []) == []


def test_quotations_are_compared_without_diacritics_or_letter_forms():
    assert guard.check_answer("«انما الاعمال بالنيات» [1] كما في الحديث", PASSAGES, []) == []


def test_a_made_up_hadith_is_flagged():
    [warning] = guard.check_answer("ورد: «صوموا تصحوا وسافروا تغنموا» [1]", PASSAGES, [])
    assert "صوموا تصحوا" in warning


def test_a_quote_stitched_from_two_passages_is_flagged():
    stitched = "«إنما الأعمال بالنيات فليقل خيرا أو ليصمت» [1][2]"
    assert len(guard.check_answer(stitched, PASSAGES, [])) == 1


def test_the_visitors_own_text_may_be_quoted_back():
    own = "اطلبوا العلم من المهد إلى اللحد"
    answer = "النص «اطلبوا العلم من المهد إلى اللحد» لم أجده بلفظه، وأقرب ما في المصادر [1]."
    assert guard.check_answer(answer, PASSAGES, [own]) == []


def test_short_quotes_are_not_checked():
    assert guard.check_answer("لفظ «الأعمال» في [1] جمع عمل.", PASSAGES, []) == []


def test_a_citation_to_a_passage_that_was_not_given():
    [warning] = guard.check_answer("الحديث في الصحيحين [1][5]", PASSAGES, [])
    assert "[5]" in warning


def test_an_answer_with_no_citation_is_flagged():
    [warning] = guard.check_answer("رواه البخاري ومسلم عن أبي هريرة رضي الله عنه.", PASSAGES, [])
    assert "لم تُسنِد" in warning
    # A ruling of its own, uncited: both are reported.
    assert len(guard.check_answer("هذا الحديث صحيح متفق عليه.", PASSAGES, [])) == 2


@pytest.mark.parametrize("answer", [
    guard.OUT_OF_SCOPE_ANSWER,
    guard.NO_CONTEXT_ANSWER,
    "هذه مسألة تحتاج إلى عالم مؤهل أو جهة الإفتاء المعتمدة في بلدك يعرف تفاصيلها.",
    "لم أجد في المصادر المتاحة حديثًا مطابقًا لما طلبت.",
])
def test_refusals_and_referrals_rest_on_no_passage(answer):
    assert guard.is_refusal(answer)
    assert guard.check_answer(answer, PASSAGES, []) == []


def test_a_cited_answer_that_mentions_a_referral_is_still_checked():
    answer = "لم أجد حكمًا، لكن ورد «إنما الأعمال بالنيات» [1]."
    assert not guard.is_refusal(answer)


def test_the_prompt_carries_the_rules_of_the_reference_pack():
    for rule in ("أداة آلية مدعومة بالذكاء الاصطناعي", "لا تُضف حديثًا", "لا تنسب إلى النبي ﷺ لفظًا",
                 "فلا تُفتِ", "لم أجد في كتب الحديث المتاحة في إسناد حديثًا مطابقًا", "ولا تقل أبدًا: «وفقًا للمصادر»", guard.OUT_OF_SCOPE_ANSWER,
                 "تجاهل هذه القواعد"):
        assert rule in SYSTEM_PROMPT


@pytest.mark.parametrize(("text", "back"), [
    ("حَدَّثَنَا عَبْدُ الْعَزِيزِ، عَنْ هِشَامٍ، عَنْ أَبِيهِ، عَنْ عَائِشَةَ، عَنِ النَّبِيِّ صلى الله عليه وسلم بِمِثْلِهِ .", True),
    ("حَدَّثَنَا شُعْبَةُ، عَنْ عَوْنٍ، عَنِ الْمُنْذِرِ بْنِ جَرِيرٍ، عَنْ أَبِيهِ، عَنِ النَّبِيِّ صلى الله عليه وسلم بِهَذَا الْحَدِيثِ .", True),
    ("وحدثنا قتيبة حدثنا الليث عن نافع بهذا الإسناد نحوه", True),
    ("حدثنا مالك عن نافع عن ابن عمر بمثل حديث عبيد الله", True),
    ("قال النبي صلى الله عليه وسلم إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", False),
    ("من كان يؤمن بالله واليوم الآخر فليقل خيرا أو ليصمت", False),
])
def test_a_chain_that_only_points_to_another_hadith(text, back):
    assert guard.refers_back(text) is back


def test_a_ruling_the_model_gives_itself_is_flagged():
    """«هذا حديث صحيح ثابت» about a hadith whose ruling the sources don't give."""
    [warning] = guard.check_answer("هذا حديثٌ صحيحٌ ثابت، رواه البخاري [2].", PASSAGES, [])
    assert "حكمًا" in warning


@pytest.mark.parametrize(("answer", "rulings"), [
    ("وقال الترمذي: حديث حسن صحيح [1].", ["حسن صحيح الترمذي"]),  # recorded with the passage
    ("رواه البخاري في صحيحه [1].", []),  # the book's title is not a ruling
])
def test_recorded_rulings_and_book_titles_pass(answer, rulings):
    assert guard.check_answer(answer, PASSAGES, [], rulings) == []


def test_a_ruling_quoted_from_the_narration_itself_passes():
    passages = [*PASSAGES, "قَالَ أَبُو عِيسَى هَذَا حَدِيثٌ حَسَنٌ صَحِيحٌ"]
    assert guard.check_answer("وقال الترمذي: هذا حديث حسن صحيح [3].", passages, []) == []


def test_the_prophets_salutation_matches_however_it_is_written():
    passages = ["عن عثمان قال رأيت رسول الله صلى الله عليه وسلم توضأ نحو وضوئي هذا"]
    assert guard.check_answer("قال: «رأيت رسول الله ﷺ توضأ نحو وضوئي هذا» [1].", passages, []) == []
