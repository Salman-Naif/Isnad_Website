# Isnad in the challenge

**إسناد (Isnad)** is the entry of **فريق إسناد (Isnad team)** in **تحدي الذكاء الاصطناعي في خدمة
المحتوى الإسلامي** (The AI Challenge in Serving Islamic Content), organised by مؤسسة باذل الأهلية,
2026.

## At a glance

| | |
| --- | --- |
| Live demo | https://isnadapplication-production.up.railway.app |
| Code (public, MIT) | [Isnad_Website](https://github.com/Salman-Naif/Isnad_Website) — the public site and the chat · [Isnad_Database](https://github.com/Salman-Naif/Isnad_Database) — the sources, their search and the admin dashboard |
| Hosting | Railway, two Docker services in one project: the website (public) and the database service (its dashboard only for the team's signed-in users), which keeps vectors, texts, settings and statistics on a persistent Volume. Every push to `main` is tested in CI and redeployed. |
| How it works | A visitor's text → the database service finds it word for word (SQLite FTS5) or by meaning (embeddings in ChromaDB) → the website gives the verdict, the ruling with its scholar, the differing words and the isnad tree → the chat answers from the passages found only, and every quotation is checked against them |
| Technologies | Python 3.11 · FastAPI · Jinja2 · ChromaDB · SQLite (FTS5) · OpenRouter: `qwen/qwen3-embedding-4b` (embeddings), `deepseek/deepseek-v4-flash-0731` (chat), Gemini (OCR of scanned books) · Docker · Railway · GitHub Actions |
| Data | Eight books of hadith from their printed editions in المكتبة الشاملة (63,815 hadiths, rulings as the editions record them), checked against الدرر السنية — the database repo's `docs/DATA_SOURCES.md` |
| Run it | Each README: "Running locally" (environment variables in `.env.example`, all listed under "Environment variables"), "Deploying to Railway", "Development and testing" |
| Dashboard access | Not public. The team's system manager can create an account for a reviewer on request. |

## Team and contact

| Member | Contact |
| --- | --- |
| سلمان نايف المحيسن | almuhaysins@outlook.sa |
| نوت عبدالعزيز الجهني | noota123db@gmail.com |

## Problem, beneficiary and success measure

- **Problem:** hadiths and sayings attributed to the Prophet ﷺ circulate with altered wording,
  without a source, or not being hadiths at all; checking one means knowing where to look and
  reading the chains and rulings of the scholars.
- **Beneficiaries:** those who introduce Islam and share its content, researchers, and the
  general public who meet a quote and want to know whether it is authentic.
- **What Isnad does:** a visitor writes a hadith or quote in any wording. Isnad finds it in the
  approved books — word for word, or by meaning — and says whether it is the same text, a
  reworded version of a known one, or not in the sources. It shows the source, the ruling
  attributed to the scholar who gave it, the words that differ, and the chain of narration as a
  tree across the books. A chat assistant then answers questions about it from those texts only.
- **Success is measured by:** the share of verifications that reach the right verdict (310
  cases over the eight books: `docs/evaluation/verification.md`, and the README's "Verification"),
  and the share of chat answers that stay
  on the sources, refuse what is out of scope, never make up a hadith and refer personal cases
  (`docs/evaluation/results.md`).

## The judging criteria and where to check each

| Criterion | Weight | Evidence |
| --- | --- | --- |
| Technical quality and use of AI | 25% | Semantic search (Qwen3 embeddings, 1024 dims) plus a literal-quote index; RAG chat with an answer check; isnad trees from the editions' narrator links, or read from the narrations' wording. 700+ automated tests at five levels (unit, integration, API, security, system), CI on every push. README "How it fits together"; Isnad_Database README; AI as a development tool and as product features: [`AI.md`](AI.md) |
| Reliability and scientific safety | 15% | Rules of the reference pack's content levels in the prompt, a retrieval gate and a deterministic answer check (`docs/SAFETY.md`); rulings only from the sources; the evaluation set run 3× per case (`docs/evaluation/`) |
| Innovation and added value | 15% | Verdicts that tell a distorted quote from an authentic one (word overlap + similarity), the differing words highlighted, isnad trees merged across books, every chat quotation verified word for word against the sources |
| Beneficiary experience, communication and accessibility | 10% | Arabic, right-to-left, mobile-first; clear verdicts and next steps; keyboard and screen-reader labels; the AI nature and privacy stated on the page |
| Benefit by the track's success criterion | 20% | Measured verdict accuracy (`docs/evaluation/verification.md`: word for word 64/64, not in the sources 29/30); chat evaluation results (`docs/evaluation/results.md`) |
| Realistic operation and continuation | 10% | Costs, alternatives to each critical dependency, maintenance roles (`docs/OPERATIONS.md`) |
| Clear presentation and verifiability | 5% | Every claim above links to code, a test or a measurement; how to re-run them below |

## Verifying it yourself

- **Live demo:** https://isnadapplication-production.up.railway.app
- **Tests:** `pytest` in each repository (README "Development and testing").
- **Chat evaluation:** start the site (README "Running locally"), then
  `python scripts/evaluate_chat.py --url http://127.0.0.1:8000 --repeat 3` — it writes
  `docs/evaluation/results.md`.
- **Verdicts:** `python scripts/measure_verification.py --url <site>` — it writes
  `docs/evaluation/verification.md` (each search counts in the statistics; `--pause 2` against the
  live site, which allows 30 searches a minute).
- **A verdict by hand:** search the same text on [الدرر السنية](https://dorar.net/hadith).

## Starting version and rights

Isnad is the team's own earlier work, continued during the challenge, as the participant guide
allows. The repositories' history up to the tag `challenge-start` (set at the start of the
challenge days, 4 October 2026) is the starting version; what follows it is the work of the
challenge days. All the code is the team's (MIT License, `LICENSE`); third-party components,
models, services and data keep their own licenses (`THIRD_PARTY_LICENSES.md`, and the database
repository's `docs/DATA_SOURCES.md`).
