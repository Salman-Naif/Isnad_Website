"""System tests: the whole of Isnad end to end — the public website, the database service and
the (stubbed) model provider, each a real process talking over real HTTP.

One story, in order: the team uploads approved hadiths → a visitor opens the site, verifies a
hadith and asks about it → the visit, search and question appear in the dashboard statistics
→ the team switches maintenance on and off.
"""

import json
import time

from tests.system.stub_openrouter import CHAT_ANSWER

HADITHS = [
    {"id": "b1", "text": "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "hukm": "صحيح",
     "mohaddith": "البخاري ومسلم", "sanad": [{"name": "عمر بن الخطاب", "grade": "صحابي"}],
     "topic": "النية", "source": "صحيح البخاري"},
    {"id": "b2", "text": "من حسن إسلام المرء تركه ما لا يعنيه", "hukm": "حسن",
     "mohaddith": "الترمذي", "topic": "الأخلاق", "source": "جامع الترمذي"},
]


def wait_for(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.3)
    raise AssertionError("condition not met in time")


def test_team_uploads_approved_hadiths(owner):
    body = json.dumps(HADITHS, ensure_ascii=False).encode()
    res = owner.post("/api/sources", files={"file": ("أحاديث.json", body)})
    assert res.status_code == 202
    row = wait_for(lambda: (r := owner.get(f"/api/sources/{res.json()['id']}").json())["status"] != "processing" and r)
    assert row["status"] == "ready" and row["chunks"] == 2


def test_visitor_opens_the_site(visitor):
    res = visitor.get("/")
    assert res.status_code == 200 and "search-form" in res.text
    assert visitor.cookies.get("isnad_vid")
    assert "content-security-policy" in res.headers
    assert visitor.get("/static/js/app.js").status_code == 200


def test_visitor_verifies_a_hadith(visitor):
    res = visitor.post("/api/search", json={"query": "إنما الأعمال بالنيات وإنما لكل امرئ ما نوى"})
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "verified"
    best = body["results"][0]
    assert best["hukm"] == "صحيح" and best["mohaddith"] == "البخاري ومسلم"
    assert best["sanad"] == [{"name": "عمر بن الخطاب", "grade": "صحابي"}]


def test_text_outside_the_sources_is_not_verified(visitor):
    body = visitor.post("/api/search", json={"query": "zzzz qqqq xxxx"}).json()
    assert body["verdict"] == "no_match"


def test_visitor_asks_the_model_about_the_hadith(visitor, openrouter):
    res = visitor.post("/api/chat", json={"question": "ما حكم هذا الحديث؟",
                                          "context_query": "إنما الأعمال بالنيات"})
    assert res.status_code == 200
    assert res.json()["answer"] == CHAT_ANSWER
    assert "صحيح البخاري" in res.json()["sources"]
    # The model received the passage and its ruling as context, as plain text.
    _, request = [r for r in openrouter.requests if r[0].endswith("/chat/completions")][-1]
    prompt = request["messages"][-1]["content"]
    assert "إنما الأعمال بالنيات" in prompt and "الحكم: صحيح" in prompt


def test_visitor_reads_the_answer_as_the_model_writes_it(visitor, openrouter):
    with visitor.stream("POST", "/api/chat/stream", json={"question": "من رواه؟",
                                                        "context_query": "إنما الأعمال بالنيات"}) as res:
        assert res.status_code == 200
        events = [json.loads(line) for line in res.iter_lines() if line.strip()]
    assert events[0]["type"] == "passages"
    assert any("إنما الأعمال بالنيات" in p["text"] for p in events[0]["passages"])
    deltas = [e["text"] for e in events if e["type"] == "delta"]
    assert len(deltas) > 1 and "".join(deltas).strip() == CHAT_ANSWER
    assert events[-1] == {"type": "done"}
    _, request = [r for r in openrouter.requests if r[0].endswith("/chat/completions")][-1]
    assert request["stream"] is True


def test_the_visit_search_and_question_reach_the_dashboard(owner):
    summary = wait_for(lambda: (s := owner.get("/api/reports/summary").json())["chats"] >= 2 and s)
    assert summary["visits"] >= 1 and summary["unique_visitors"] >= 1
    assert summary["searches"] == 2
    # One verified, one no match — shown with Arabic labels in the dashboard.
    assert sorted(r["count"] for r in summary["search_results"]) == [1, 1]
    assert {q["label"] for q in summary["top_questions"]} == {"ما حكم هذا الحديث؟", "من رواه؟"}


def test_maintenance_switch_closes_and_reopens_the_site(owner, visitor):
    settings = owner.get("/api/site-settings").json()
    owner.put("/api/site-settings", json={**settings, "maintenance_mode": True, "maintenance_message": "صيانة قصيرة"})
    closed = visitor.get("/")
    assert closed.status_code == 503 and "صيانة قصيرة" in closed.text
    assert visitor.post("/api/search", json={"query": "نص"}).status_code == 503

    owner.put("/api/site-settings", json={**settings, "maintenance_mode": False})
    assert visitor.get("/").status_code == 200


def test_the_site_key_never_reaches_the_browser(visitor):
    from tests.system.conftest import SITE_KEY

    for path in ("/", "/static/js/app.js", "/static/css/style.css"):
        assert SITE_KEY not in visitor.get(path).text


# Real narrations as a CSV collection holds them: the chain inside the text.
BUKHARI_CSV = (
    "Sahih Bukhari\n"
    "حدثنا الحميدي عبد الله بن الزبير قال حدثنا سفيان قال حدثنا يحيى بن سعيد الأنصاري قال أخبرني محمد بن "
    "إبراهيم التيمي أنه سمع علقمة بن وقاص الليثي يقول سمعت عمر بن الخطاب رضي الله عنه على المنبر قال سمعت "
    "رسول الله صلى الله عليه وسلم يقول إنما الأعمال بالنيات وإنما لكل امرئ ما نوى فمن كانت هجرته إلى دنيا "
    "يصيبها أو إلى امرأة ينكحها فهجرته إلى ما هاجر إليه\n"
)
IBN_MAJAH_CSV = (
    "Sunan Ibn Maja\n"
    "حدثنا أبو بكر بن أبي شيبة حدثنا يزيد بن هارون أنبأنا يحيى بن سعيد عن محمد بن إبراهيم التيمي عن علقمة "
    "بن وقاص الليثي عن عمر بن الخطاب أن رسول الله صلى الله عليه وسلم قال إنما الأعمال بالنيات ولكل امرئ "
    "ما نوى فمن كانت هجرته إلى دنيا يصيبها أو إلى امرأة ينكحها فهجرته إلى ما هاجر إليه\n"
)


def test_the_sanad_tree_merges_the_chains_the_database_reads_from_each_book(owner, visitor):
    for name, body in (("Sahih Bukhari.csv", BUKHARI_CSV), ("Sunan Ibn Maja.csv", IBN_MAJAH_CSV)):
        res = owner.post("/api/sources", files={"file": (name, body.encode())})
        assert res.status_code == 202
        source = f"/api/sources/{res.json()['id']}"
        wait_for(lambda source=source: owner.get(source).json()["status"] == "ready")

    body = visitor.post("/api/search", json={"query": "فمن كانت هجرته إلى دنيا يصيبها أو إلى امرأة ينكحها",
                                             "top_k": 10}).json()
    tree = body["sanad_tree"]
    assert tree["name"] == "النبي ﷺ"
    node, names = tree, []
    while len(node["children"]) == 1:
        node = node["children"][0]
        names.append(node["name"])
    # One chain down to Yahya ibn Sa'id, then a branch per book, each ending with its compiler
    assert names[0].startswith("عمر بن الخطاب") and names[-1].startswith("يحيى بن سعيد")
    assert sorted(c["name"] for c in node["children"]) == sorted(["سفيان", "يزيد بن هارون"])
    assert {path_end(c)["name"] for c in node["children"]} == {"البخاري", "ابن ماجه"}
    assert body["sanad_extracted"] is True
    assert set(body["sanad_sources"]) == {"صحيح البخاري", "سنن ابن ماجه"}


def path_end(node):
    while node["children"]:
        node = node["children"][0]
    return node
