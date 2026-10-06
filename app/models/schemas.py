"""Request and response models (Pydantic)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    """Verification verdict; values match the page's data-verdict attribute."""

    VERIFIED = "verified"  # the same text as a structured hadith that carries a scholar's ruling
    FOUND = "found"  # the same text as a passage from an uploaded book, but no ruling attached
    DISTORTED = "distorted"  # resembles a known text with different wording
    # An English text whose meaning is a hadith of the sources: never "the same text", since the
    # visitor's words are not the hadith's
    MEANING = "meaning"
    NO_MATCH = "no_match"


class MatchType(StrEnum):
    """How the visitor's text matches the source."""

    EXACT = "exact"  # word for word
    CLOSE = "close"  # the same text, a letter or a word apart
    REWORDED = "reworded"  # a known text in other words
    MEANING = "meaning"  # the meaning of a known text, in another language
    NONE = "none"


class Narrator(BaseModel):
    name: str
    grade: str | None = None


class SanadNode(BaseModel):
    """A narrator in an isnad tree; each path from the root to a leaf is one chain."""

    name: str
    grade: str | None = None
    children: list["SanadNode"] = Field(default_factory=list)


class QueryWord(BaseModel):
    """A word of the visitor's text; `changed` when it is not in the source (the شبهة)."""

    word: str
    changed: bool = False


# --- From the database service (/api/v1) ---


class SiteConfig(BaseModel):
    """Controls set in the database dashboard."""

    maintenance_mode: bool = False
    maintenance_message: str = "الموقع تحت الصيانة، نعود قريبًا بإذن الله"
    search_enabled: bool = True
    chat_enabled: bool = True
    announcement: str = ""


class Match(BaseModel):
    """One stored passage close to the query, as returned by the database search."""

    id: str
    text: str
    similarity: float
    # Share of the query's words found in the text (None from a database that doesn't send it)
    word_overlap: float | None = None
    kind: str
    hukm: str | None = None
    mohaddith: str | None = None
    sanad: list[Narrator] = Field(default_factory=list)
    # The isnad as a tree; sanad_extracted when the database read it from the narration's wording.
    sanad_tree: SanadNode | None = None
    sanad_extracted: bool = False
    topic: str | None = None
    source: str | None = None
    # The book's compiler and his year of death, for one of the eight books
    compiler: str | None = None


# --- /api/search ---


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)


class SearchResult(BaseModel):
    text: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    word_overlap: float | None = None
    match_type: MatchType = MatchType.NONE
    verdict: Verdict
    verdict_message: str
    kind: str
    hukm: str | None = None
    mohaddith: str | None = None
    sanad: list[Narrator] = Field(default_factory=list)
    sanad_tree: SanadNode | None = None
    sanad_extracted: bool = False
    # The visitor's words, those not in this text marked (the شبهة)
    words: list[QueryWord] = Field(default_factory=list)
    topic: str | None = None
    source: str | None = None
    # The book's compiler and his year of death, for one of the eight books
    compiler: str | None = None
    # The other books the same hadith is in, shown once (app/services/grouping.py)
    also_in: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    verdict: Verdict  # verdict of the best match
    verdict_message: str
    results: list[SearchResult] = Field(default_factory=list)
    # The isnad of the best match, merged with that of the same text in the other books found
    sanad_tree: SanadNode | None = None
    sanad_sources: list[str] = Field(default_factory=list)
    sanad_extracted: bool = False
    # The language the visitor wrote in, and for English the Arabic the sources were searched with
    language: str = "ar"
    searched_as: str | None = None


# --- /api/explore ---


class ExploreRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=10)
    # A title («الصيام»), not a meaning: the hadiths holding its words come first.
    by_title: bool = False


class ExploreResult(BaseModel):
    """A stored text about the visitor's idea, with what the page shows beside it."""

    text: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    kind: str
    hukm: str | None = None
    mohaddith: str | None = None
    topic: str | None = None
    source: str | None = None
    also_in: list[str] = Field(default_factory=list)


class ExploreResponse(BaseModel):
    query: str
    results: list[ExploreResult] = Field(default_factory=list)
    language: str = "ar"
    searched_as: str | None = None


# --- /api/chat ---


class ChatMessage(BaseModel):
    # Only these two roles: a visitor can't inject a "system" instruction through the history.
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    # The text the visitor last searched for, if any — used to retrieve context.
    context_query: str = Field(default="", max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=10)


class ChatPassage(BaseModel):
    """A passage the answer was written from; `number` is the one the answer cites ([1], [2]…)."""

    number: int
    text: str
    hukm: str | None = None
    mohaddith: str | None = None
    source: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    passages: list[ChatPassage] = Field(default_factory=list)
    # Problems the answer check found (an unsourced quotation, a wrong citation…), for the visitor
    warnings: list[str] = Field(default_factory=list)
    # A fixed answer or a referral, resting on no passage: the passages are not shown with it
    refused: bool = False
