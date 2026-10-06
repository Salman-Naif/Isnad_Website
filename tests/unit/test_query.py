"""Unit tests: what a chat question is about, and how its passages are gathered."""

import pytest

from app.api.routes.chat import retrieve
from app.models.schemas import Match
from app.services.query import subject_of


@pytest.mark.parametrize(("question", "subject"), [
    ("من روى حديث النية؟", "النية"),
    ("هل ورد حديث في فضل الصدقة؟", "فضل الصدقة"),
    ("ما حكم حديث الطهور شطر الإيمان", "الطهور شطر الايمان"),
    ("كيف كان النبي ﷺ يصوم؟", "كان يصوم"),
    ("ماذا قال رسول الله صلى الله عليه وسلم عن الغضب", "الغضب"),
    ("من رواه؟ وما حكمه؟", ""),
    ("ما معنى هذا الحديث؟", ""),
    ("اذكر لي الأحاديث التي وردت في بر الوالدين وصلة الرحم والإحسان إلى الجار واليتيم", ""),  # too long
])
def test_the_subject_is_what_is_left_without_the_framing_words(question, subject):
    assert subject_of(question) == subject


def m(id_):
    return Match(id=id_, text=id_, similarity=0.7, kind="structured_hadith")


class Db:
    def __init__(self, found):
        self.found, self.asked = found, []

    def search(self, text, top_k, by_title=False):
        self.asked.append((text, top_k, by_title))
        return [m(i) for i in self.found[text]][:top_k]


def test_the_searched_text_comes_first_then_the_question_in_turn():
    db = Db({"نص": ["a", "b", "c"], "موضوع": ["d", "a", "e"], "سؤال": ["f", "g", "d"]})
    found = retrieve(db, "نص", [("موضوع", True), ("سؤال", False)], 6)
    assert [x.id for x in found] == ["a", "b", "c", "d", "f", "g"]
    assert db.asked == [("نص", 3, False), ("موضوع", 3, True), ("سؤال", 3, False)]
