# Operations — resources, costs and keeping Isnad running

What it takes to run Isnad after the challenge: the services it depends on, what they cost,
the alternative to each critical dependency, and who maintains what.

## What runs where

| Part | Where | Holds |
| --- | --- | --- |
| Website (this repository) | Railway service, Docker | Nothing persistent: pages, verification, chat |
| Database service ([Isnad_Database](https://github.com/Salman-Naif/Isnad_Database)) | Railway service, Docker, with a **Volume** at `/app/chroma_db` (4.4 GB) | Vectors (ChromaDB), texts and literal index, accounts, statistics (SQLite), uploaded originals |
| Models | [OpenRouter](https://openrouter.ai) API | Embeddings (`qwen/qwen3-embedding-4b`), chat (`deepseek/deepseek-v4-flash-0731`), OCR of scanned books (Gemini) |

The two services talk over HTTPS with a shared key (`SITE_API_KEY`). Setup and every variable
are in each repository's README ("Deploying to Railway").

## Running costs

Prices as published on 2026-10-02 ([Railway](https://docs.railway.com/reference/pricing/plans),
OpenRouter's `/api/v1/models`). Usage figures are measured where marked, estimated otherwise.

### Monthly (hosting)

| Item | Price | Isnad's use | Per month |
| --- | --- | --- | --- |
| Railway Hobby plan | $5 / month, includes $5 of usage | — | $5 |
| Memory | $10 / GB / month | database service ~150 MB idle (measured), website ~100 MB (estimate) | ~$2.5 |
| Volume storage | $0.15 / GB / month | 4.4 GB | ~$0.66 |
| CPU | $20 / vCPU / month | near idle between requests (estimate) | < $1 |
| **Total** | | | **about $5 at today's traffic** (usage stays inside the plan's $5) |

### Per use (OpenRouter)

| Operation | Price | Cost |
| --- | --- | --- |
| A chat question (DeepSeek V4 Flash) | $0.0115 / M input tokens, $1.28 / M output tokens | ~3,000 tokens in, ~400 out → **~$0.0006** (≈ 1,700 questions per US dollar) |
| A search (verification) | `qwen3-embedding-4b`: $0.02 / M tokens | **~$0.0000004** |
| Indexing a text book (JSON / CSV) | same | a few cents per book (measured on the four books) |
| Indexing a scanned book (OCR) | Gemini 3 Flash + cross-check | ~$0.01 per page (measured) — only for scanned uploads |

The website's rate limits cap the bill: 10 chat questions per visitor per minute and 60 for the
whole site (`CHAT_PER_MINUTE`, `CHAT_PER_MINUTE_SITE`) — at most ~$0.04 a minute of chat even
under abuse. OpenRouter accounts can also be given a hard credit limit.

### One-time

Indexing the eight books (the Shamela editions, about 60,000 hadiths): about 25 minutes at the
measured rate (Sunan Ibn Majah, 4,332 hadiths, in ~100 s; estimate) and about $0.25 of embeddings
(12.3 M tokens, measured with `scripts/import_hadiths.py --estimate`).

## Critical dependencies and their alternatives

| Dependency | If it fails or must change | How |
| --- | --- | --- |
| OpenRouter (single gateway to the models) | Any OpenAI-compatible API — DeepSeek's own API, another gateway | Website: `LLM_BASE_URL`; database service: `OPENROUTER_BASE_URL` (both with their key) |
| Chat model | Any other model on OpenRouter | `LLM_MODEL`; then re-run the chat evaluation (`scripts/evaluate_chat.py`) before switching |
| Embedding model | Run the same open model (Qwen3-Embedding-4B, Apache-2.0) on the server: same vectors, slower on CPU | Database service's README, "Embeddings" |
| Railway | Any Docker host with a persistent disk (e.g. Render, suggested in the participant guide) | Both services are plain Dockerfiles; the Volume becomes a mounted disk |
| The database service is down | The website answers with a clear message (503) instead of a wrong verdict | `app/services/database.py` |
| Lost Volume | Rebuild: re-upload the eight books (~25 minutes, ~$0.25); originals can be downloaded from the dashboard beforehand | Database service's README, "Disk space" |

## Maintenance and content review

| Task | When | Who |
| --- | --- | --- |
| Approve sources before upload; only approved editions go in | Each new source | The team's Sharia / content reviewer |
| Review searches that found nothing and the chat's warnings (dashboard → statistics) | Weekly | Content reviewer |
| Re-run the chat evaluation (`scripts/evaluate_chat.py`, report in `docs/evaluation/results.md`) | On any change to the prompt, the model or the sources | Technical lead |
| Dependency audit (pip-audit, Bandit, tests — CI on every push) | Every push; review advisories monthly | Technical lead |
| Rotate `SITE_API_KEY` and the OpenRouter key | If ever exposed, and yearly | Technical lead |
| Back up: download the originals from the dashboard | After uploads | Technical lead |

Monitoring: `/health` on both services (Railway health checks), the dashboard's status page
(storage, models, database), and Railway's logs.

## Next steps after the challenge

1. Ask the datasets' authors for permission, or move to sources with published terms that the
   reference pack lists (موسوعة الأحاديث النبوية — HadeethEnc, Dorar's hadith API); add
   scholars' rulings from an edition that has them for every book.
2. A Sharia reviewer validates a sample of answers each month, using the evaluation set.
3. Grow the evaluation set with the questions visitors actually ask (from the statistics).
