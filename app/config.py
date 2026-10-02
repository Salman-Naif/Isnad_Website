"""
Settings for the Isnad main website, read from environment variables
(.env locally, or Variables on Railway).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Identity ---
    app_name: str = "Isnad"

    # --- Database service (Isnad_v1) ---
    # Its own URL, e.g. https://<database-service>.up.railway.app — no trailing slash.
    database_url: str = ""
    # Same value as SITE_API_KEY on the database service. Stays on this server only.
    site_api_key: str = ""
    database_timeout_seconds: float = 15.0
    # How long the controls set in the dashboard (maintenance, features) are cached here.
    site_config_cache_seconds: int = 30

    # --- Chat model (OpenRouter) ---
    openrouter_api_key: str = ""
    llm_model: str = "deepseek/deepseek-v4-flash-0731"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_seconds: float = 20.0
    llm_max_tokens: int = 700
    # DeepSeek "thinks" before answering by default (~4–10 s). Answering from ready
    # context doesn't need it; with it off, answers take ~1–2 s.
    llm_reasoning: bool = False
    # Passages retrieved from the database for each chat question.
    chat_context_passages: int = 6
    # Passages less similar than this to the question are not given to the model; with none
    # left, the chat answers that the sources hold nothing on it, without calling the model.
    # Measured on the live database (9 books): questions about hadith topics scored 0.59–0.83,
    # questions outside the scope 0.38–0.68 — the prompt refuses the ones that get through.
    chat_min_similarity: float = 0.56

    # --- Verification thresholds (similarity from the database search) ---
    # Measured on 21,000 hadiths (Muslim, Tirmidhi, Ibn Majah) with the database's search
    # (qwen/qwen3-embedding-4b at 1024 dimensions + its literal-quote index):
    #   word-for-word quote 1.0 · two words missing / one changed 0.58–0.85 (p5–p95) ·
    #   first five words only 0.53–0.79 · not in the sources 0.42–0.61.
    # At 0.60, 84% of altered real hadiths are flagged as resembling a known text and 3% of
    # texts that are not in the sources (1 in 30); at 0.50 it was 99% and 60%.
    # Recalibrate if the database's EMBEDDING_MODEL changes.
    threshold_high: float = 0.90  # ≥ high → the same text (verified / found)
    # A reworded version (distortion warning) needs either a strong semantic match, or a
    # moderate one that shares most of its words with the text: an altered quote keeps most
    # words, a saying that only sounds alike shares almost none. Measured on 50,000 hadith
    # vectors: texts not in the sources wrongly warned 3% (57% with a single 0.60 threshold),
    # altered quotes warned 77%, paraphrases in a visitor's own words 88%.
    threshold_strong: float = 0.75
    threshold_mid: float = 0.60
    min_word_overlap: float = 0.6
    # Search by meaning (/api/explore): hadiths about an idea, not one quote. Closer than this
    # to the visitor's idea to be listed. Not yet measured on the real sources — set it from
    # what the real search returns (EXPLORE_MIN_SIMILARITY on Railway).
    explore_min_similarity: float = 0.45

    # --- Public rate limits: per visitor IP, and for the whole site (a ceiling on cost) ---
    search_per_minute: int = 30
    chat_per_minute: int = 10
    search_per_minute_site: int = 300
    chat_per_minute_site: int = 60

    # --- Logging ---
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Single settings instance reused everywhere."""
    return Settings()
