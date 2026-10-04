"""Unit tests: English texts — told apart from Arabic, their verdicts, the chat's rules and checks."""

import pytest

from app.models.schemas import Match, Verdict
from app.services import guard, rag
from app.services.language import TranslationCache, language_of, looks_arabic
from app.services.verification import build_results, classify_english, verdict_message


@pytest.mark.parametrize(("text", "lang"), [
    ("Actions are but by intentions", "en"),
    ("إنما الأعمال بالنيات", "ar"),
    ("قال رسول الله ﷺ: إنما الأعمال بالنيات (Bukhari 1)", "ar"),  # mostly Arabic
    ("ok", "ar"),  # too few letters to tell
    ("12345 ...", "ar"),
])
def test_the_language_of_a_text(text, lang):
    assert language_of(text) == lang


def test_a_rendering_must_be_arabic():
    assert looks_arabic("إنما الأعمال بالنيات") and not looks_arabic("Sorry, I can't")


def test_the_cache_keeps_the_latest_renderings():
    cache = TranslationCache(size=2)
    cache.put("a", "أ")
    cache.put("b", "ب")
    cache.get("a")  # «a» used again: «b» is now the oldest
    cache.put("c", "ج")
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == ("أ", None, "ج")


@pytest.mark.parametrize(("similarity", "overlap", "verdict"), [
    (1.0, 1.0, Verdict.MEANING),  # its Arabic rendering is a hadith word for word
    (0.95, 0.9, Verdict.MEANING),
    (0.8, 0.3, Verdict.DISTORTED),  # close to a hadith, not it
    (0.65, 0.2, Verdict.NO_MATCH),
])
def test_an_english_text_found_through_its_rendering_is_never_the_same_text(similarity, overlap, verdict):
    assert classify_english(similarity, True, overlap, translated=True) == verdict


@pytest.mark.parametrize(("similarity", "verdict"), [(0.8, Verdict.DISTORTED), (0.74, Verdict.NO_MATCH)])
def test_an_english_text_searched_as_it_is_needs_a_strong_match(similarity, verdict):
    assert classify_english(similarity, True, 1.0, translated=False) == verdict


def test_english_results_compare_no_words_and_speak_english():
    match = Match(id="1", text="من غشنا فليس منا", similarity=1.0, word_overlap=1.0, kind="structured_hadith",
                  hukm="صحيح")
    [result] = build_results([match], "من غشنا فليس منا", "en", translated=True)
    assert (result.verdict, result.match_type, result.words) == (Verdict.MEANING, "meaning", [])
    assert result.verdict_message == verdict_message(Verdict.MEANING, "en")
    assert verdict_message(Verdict.NO_MATCH, "en").startswith("No hadith")


def test_an_english_question_is_answered_in_english_with_the_hadith_in_arabic():
    match = Match(id="1", text="من غشنا فليس منا", similarity=0.8, kind="structured_hadith", source="صحيح مسلم")
    [_, user] = rag._messages("Who narrated it?", [match], None, "Whoever cheats us is not one of us")
    assert rag.ENGLISH_NOTE in user["content"] and "Meaning (an explanation, not a translation" in user["content"]
    [_, arabic] = rag._messages("من رواه؟", [match], None, "")
    assert rag.ENGLISH_NOTE not in arabic["content"]


@pytest.mark.parametrize("question", [
    "Is it permissible for me to take a loan with interest?", "I divorced my wife in anger, is it valid?",
    "Give me a fatwa about my prayers",
])
def test_an_english_personal_case_is_recognised(question):
    assert guard.is_personal_case(question)


def test_an_english_question_about_a_hadith_is_not_a_personal_case():
    assert not guard.is_personal_case("Can I know who narrated this hadith?")


def test_english_fixed_answers_are_refusals():
    assert guard.is_refusal(guard.OUT_OF_SCOPE_ANSWER_EN) and guard.is_refusal(guard.NO_CONTEXT_ANSWER_EN)
    assert guard.no_context_answer("en") == guard.NO_CONTEXT_ANSWER_EN
    assert guard.no_context_answer("ar") == guard.NO_CONTEXT_ANSWER


PASSAGE = "حدثنا قتيبة عن أبي هريرة أن رسول الله صلى الله عليه وسلم قال من غشنا فليس منا"


def test_an_english_translation_presented_as_a_quotation_is_flagged_in_english():
    answer = 'Narrated by Muslim [1]: "Whoever cheats us is not one of us and will be punished".'
    [warning] = guard.check_answer(answer, [PASSAGE], ["Who narrated it?"], lang="en")
    assert warning.startswith("The answer quotes a text we did not find word for word")


def test_an_english_grading_must_be_one_recorded():
    graded = "Narrated by Muslim «من غشنا فليس منا» [1]. This hadith is authentic."
    assert guard.check_answer(graded, [PASSAGE], [], ["صحيح الألباني"], "en") == []
    [warning] = guard.check_answer(graded, [PASSAGE], [], ["ضعيف الألباني"], "en")
    assert "not recorded in the sources" in warning


def test_a_ruling_quoted_as_recorded_is_not_flagged():
    answer = "Narrated by Ahmad «من غشنا فليس منا» [1]. Ruling: «إسناده صحيح على شرط مسلم» — Shu'ayb al-Arna'ut."
    assert guard.check_answer(answer, [PASSAGE], [], ["إسناده صحيح على شرط مسلم شعيب الأرنؤوط"], "en") == []
    assert guard.check_answer(answer, [PASSAGE], [], ["حسن"], "en")  # a ruling not recorded is still flagged


def test_equal_matches_keep_the_order_the_database_gives():
    books = ["صحيح البخاري", "صحيح مسلم", "سنن ابن ماجه"]
    matches = [Match(id=b, text="من غشنا فليس منا", similarity=1.0, kind="structured_hadith", source=b) for b in books]
    assert [r.source for r in build_results(matches, "من غشنا فليس منا")] == books
