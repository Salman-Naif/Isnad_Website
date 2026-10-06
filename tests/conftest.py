"""Shared test setup: the database service and the chat model are replaced by fakes."""

import os
from pathlib import Path

# Must be set before the app (and its cached settings) is imported:
# environment variables take precedence over the developer's .env file.
os.environ["DATABASE_URL"] = "http://database.test"
os.environ["SITE_API_KEY"] = "test-site-key"
os.environ["OPENROUTER_API_KEY"] = ""

# Tests never read the developer's .env: only the values above and the code's defaults apply.
from app.config import Settings

Settings.model_config["env_file"] = None

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_database, get_rag  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core.rate_limit import reset_rate_limits  # noqa: E402
from app.main import app  # noqa: E402
from app.models.schemas import Match, Narrator, SiteConfig  # noqa: E402
from app.services.database import DatabaseError  # noqa: E402

get_settings.cache_clear()

HADITH = Match(
    id="hadith-1",
    text="إنما الأعمال بالنيات وإنما لكل امرئ ما نوى",
    similarity=0.97,
    kind="structured_hadith",
    hukm="صحيح",
    mohaddith="البخاري ومسلم",
    sanad=[Narrator(name="النبي ﷺ", grade="المصدر"), Narrator(name="عمر بن الخطاب", grade="صحابي")],
    topic="النية",
    source="صحيح البخاري",
)
BOOK_PASSAGE = Match(
    id="doc-1", text="نص من كتاب مرفوع", similarity=0.93, kind="document", source="كتاب.pdf",
)


class FakeDatabase:
    """Stands in for the database service: answers from a fixed list and records events."""

    def __init__(self) -> None:
        self.config = SiteConfig()
        self.matches: list[Match] = []
        self.searches: list[tuple[str, int]] = []
        self.by_title: list[bool] = []
        self.events: list[dict] = []
        self.error: DatabaseError | None = None

    def site_config(self) -> SiteConfig:
        return self.config

    def search(self, query: str, top_k: int, by_title: bool = False) -> list[Match]:
        if self.error:
            raise self.error
        self.searches.append((query, top_k))
        self.by_title.append(by_title)
        return self.matches[:top_k]

    def record_event(self, type_, visitor_id, query="", result="", latency_ms=None) -> None:
        self.events.append({"type": type_, "visitor_id": visitor_id, "query": query, "result": result})


class FakeRAG:
    """Records what the chat route sends to the model instead of calling OpenRouter."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.error: Exception | None = None
        self.pieces = ["إجابة ", "تجريبية [1]"]  # what stream() yields
        self.reply = "إجابة تجريبية [1]"  # what answer() returns
        self.renderings: dict[str, str] = {}  # English text → its Arabic rendering (to_arabic)
        self.translations: list[str] = []
        self.translation_error: Exception | None = None

    def answer(self, question, contexts, history=None, subject="") -> str:
        if self.error:
            raise self.error
        self.calls.append({"question": question, "contexts": contexts, "history": history, "subject": subject})
        return self.reply

    def to_arabic(self, text: str) -> str:
        """The Arabic rendering of an English text: a fixed one unless a test sets its own."""
        if self.translation_error:
            raise self.translation_error
        self.translations.append(text)
        return self.renderings.get(text, "إنما الأعمال بالنيات")

    def stream(self, question, contexts, history=None, subject=""):
        if self.error:
            raise self.error
        self.calls.append({"question": question, "contexts": contexts, "history": history, "subject": subject})
        return iter(self.pieces)


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def rag() -> FakeRAG:
    return FakeRAG()


@pytest.fixture
def client(db, rag):
    reset_rate_limits()
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_rag] = lambda: rag
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    reset_rate_limits()


LEVELS = ("unit", "integration", "api", "security", "system")


def pytest_collection_modifyitems(items):
    """Mark every test with its level, taken from its folder (tests/<level>/test_*.py),
    so one level can be run on its own: pytest -m unit."""
    for item in items:
        level = Path(str(item.fspath)).parent.name
        if level in LEVELS:
            item.add_marker(getattr(pytest.mark, level))
