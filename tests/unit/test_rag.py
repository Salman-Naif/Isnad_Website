"""Unit tests: the chat model client — context block, and when the model is not called."""

from app.services.rag import NO_CONTEXT_ANSWER, RAGError, RAGService, format_context
from tests.conftest import HADITH


def test_context_block_carries_ruling_sanad_and_source():
    block = format_context([HADITH])
    assert "[1] العزو: رواه البخاري في صحيحه عن عمر بن الخطاب\nالنص: إنما الأعمال بالنيات" in block
    assert "الحكم: صحيح" in block
    assert "السند: النبي ﷺ (المصدر) > عمر بن الخطاب (صحابي)" in block
    assert "المصدر: صحيح البخاري" in block


def test_no_passages_means_no_model_call():
    # Without sources the model is never asked, so it can't answer from its own knowledge.
    assert RAGService().answer("سؤال", contexts=[]) == NO_CONTEXT_ANSWER


def test_missing_key_is_reported():
    import pytest

    with pytest.raises(RAGError, match="غير مهيأة"):
        RAGService().answer("سؤال", contexts=[HADITH])


def test_context_block_carries_the_chains_read_from_the_wording():
    from app.models.schemas import SanadNode

    tree = SanadNode(name="النبي ﷺ", children=[SanadNode(name="عمر", children=[
        SanadNode(name="علقمة", children=[SanadNode(name="البخاري")]),
        SanadNode(name="علقمة بن وقاص", children=[SanadNode(name="ابن ماجه")]),
    ])])
    block = format_context([HADITH.model_copy(update={"sanad": [], "sanad_tree": tree, "sanad_extracted": True})])
    assert "السند (مستخرج آليًا من نص الرواية): النبي ﷺ > عمر > علقمة > البخاري" in block
    assert "السند (مستخرج آليًا من نص الرواية): النبي ﷺ > عمر > علقمة بن وقاص > ابن ماجه" in block


def test_a_tree_with_many_routes_is_cut_to_a_few():
    from app.models.schemas import SanadNode
    from app.services.rag import MAX_CHAINS, chains

    tree = SanadNode(name="النبي ﷺ", children=[SanadNode(name=f"راو {i}") for i in range(10)])
    assert len(chains(tree)) == MAX_CHAINS


def test_the_model_is_asked_to_cite_passages_by_number():
    from app.services.rag import SYSTEM_PROMPT

    assert "[1]" in SYSTEM_PROMPT


def test_stream_without_passages_answers_without_the_model():
    assert list(RAGService().stream("سؤال", contexts=[])) == [NO_CONTEXT_ANSWER]


def test_a_hadith_is_attributed_to_its_book_and_companion():
    """The model names the book and the narrator («رواه مسلم في صحيحه عن أبي هريرة»), never
    «according to the sources»: the attribution is given to it ready, from the chain itself."""
    from app.models.schemas import SanadNode
    from app.services.rag import attribution

    tree = SanadNode(name="النبي ﷺ", children=[SanadNode(name="أبي هريرة", children=[SanadNode(name="مسلم")])])
    hadith = HADITH.model_copy(update={"source": "صحيح مسلم", "sanad": [], "sanad_tree": tree})
    assert attribution(hadith) == "رواه مسلم في صحيحه عن أبي هريرة"
    # A companion's own saying: the book only, no «عن»
    saying = SanadNode(name="ابن عمر", children=[SanadNode(name="نافع")])
    hadith = HADITH.model_copy(update={"source": "موطأ الإمام مالك", "sanad": [], "sanad_tree": saying})
    assert attribution(hadith) == "رواه مالك في الموطأ"
    # A book outside the nine
    other = HADITH.model_copy(update={"source": "كتاب.pdf", "sanad": [], "sanad_tree": None})
    assert attribution(other) == "ورد في كتاب.pdf"
