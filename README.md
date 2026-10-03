# Isnad (إسناد)

> An intelligent conversational system for verifying the authenticity of hadiths and Islamic quotes

**Live demo:** https://isnadapplication-production.up.railway.app

The public website of Isnad. A visitor enters any hadith or quote in any wording; the site
matches it semantically against the approved sources, shows the ruling attributed to the
scholar who issued it with the chain of narration (sanad), warns when the wording is a
distorted version of a known text, and lets the visitor ask the model about it — answered
only from the sources.

The sources, their search and the admin dashboard live in the separate database service,
**Isnad_Database**. This repository is the website only.

**Team:** فريق إسناد (Isnad) — سلمان نايف المحيسن (almuhaysins@outlook.sa) ·
نوت عبدالعزيز الجهني (noota123db@gmail.com)

Isnad is the team's entry in **تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي** (The AI
Challenge in Serving Islamic Content, مؤسسة باذل الأهلية, 2026) — see
[`docs/CHALLENGE.md`](docs/CHALLENGE.md) for the problem, the judging criteria and where each is
evidenced.

## Documentation

| Document | What it covers |
| --- | --- |
| [`docs/CHALLENGE.md`](docs/CHALLENGE.md) | The challenge entry, team and contact, criteria → evidence, how to verify |
| [`docs/AI.md`](docs/AI.md) | الذكاء الاصطناعي في البناء وفي المنتج: أدوات التطوير، والخوارزميات والنماذج داخل إسناد (بالعربية) |
| [`docs/SAFETY.md`](docs/SAFETY.md) | Reliability and scientific safety: scope, content levels, anti-hallucination checks, limits |
| [`docs/evaluation/`](docs/evaluation/) | The chat's evaluation set and its latest results |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Running resources and costs, dependencies and alternatives, maintenance |
| [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) | Every component, service, model and data source, with its license |
| Isnad_Database [`docs/DATA_SOURCES.md`](https://github.com/Salman-Naif/Isnad_Database/blob/main/docs/DATA_SOURCES.md) | The hadith books and datasets: titles, compilers, licenses, how they are used and checked |

## License

The team's code is under the [MIT License](LICENSE). Third-party components, models, services
and data keep their own licenses: [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

---

## How it fits together

```
Visitor ──► Isnad_Website (this repo) ──SITE_API_KEY──► Isnad_Database database service
                    │                                  • search the sources
                    │                                  • site controls (maintenance, features)
                    │                                  • statistics (visits, searches, questions)
                    └──OPENROUTER_API_KEY──► chat model (DeepSeek V4 Flash)
```

- The website calls the database **from its server**; the key never reaches the browser.
- The controls set in the database dashboard apply here within 30 seconds: maintenance mode
  (a maintenance page with its message), the announcement banner, and switching search or chat
  off.
- Every page view, verification and chat question is reported to the database for its
  statistics, after the response is sent, so it never slows the visitor down. Visitors are
  counted with an anonymous random cookie; no IP address or personal data is sent.

## Verification

The database returns the stored passages closest to the text, with a similarity score.
The best match decides the verdict:

| Best match                                                      | Matched item                    | Verdict shown                                                   |
| --------------------------------------------------------------- | ------------------------------- | --------------------------------------------------------------- |
| similarity ≥ `THRESHOLD_HIGH` (0.90), or the words found verbatim | Structured hadith with a ruling | **Verified** — the ruling, scholar and sanad are shown          |
| similarity ≥ `THRESHOLD_HIGH` (0.90), or the words found verbatim | Text from an uploaded book      | **Found** — the text is in the sources, but no ruling attached  |
| similarity ≥ `THRESHOLD_STRONG` (0.75)                          | Any                             | **Distortion warning** — a known text with different wording    |
| similarity ≥ `THRESHOLD_MID` (0.60) **and** ≥ `MIN_WORD_OVERLAP` (60%) of the query's words in the text | Any | **Distortion warning** |
| anything else                                                   | Any                             | **No match** in the approved sources                            |

The database service sends, with every match, its similarity and its **word overlap** — the share
of the query's meaningful words found in the matched text. An altered quote of a real hadith keeps
most of its words; a saying that merely sounds like one shares almost none with the hadith it lands
on (in a search over 50,000 hadith vectors, «صوموا تصحوا» landed on an unrelated hadith at 0.73 with
no word in common). Similarity alone could not tell them apart.

Measured on the four books (Bukhari, Muslim, Tirmidhi, Ibn Majah — from the
[Hadith-Data-Sets](https://github.com/abdelrahmaan/Hadith-Data-Sets) and
[hadith-json](https://github.com/AhmedBaset/hadith-json) datasets; see the database repo's
`docs/DATA_SOURCES.md`), searched by the database service (`qwen/qwen3-embedding-4b`, 1024
dimensions, query instruction, literal-quote index):

| Query                                                        | Verdict reached                         |
| ------------------------------------------------------------ | --------------------------------------- |
| A hadith's words, word for word (3+ words)                   | same text — every time (similarity 1.0) |
| Two words missing, one word changed, or the first five words | distortion warning 77%                  |
| A hadith in the visitor's own words                          | distortion warning 88%                  |
| Not in the sources: modern sentences, proverbs, sayings wrongly attributed to the Prophet ﷺ | no match 97% (with a single 0.60 threshold: 43%) |

If the database's `EMBEDDING_MODEL` changes, recalibrate with real sources and set the
thresholds below.

"Found" exists because a book may itself list weak or fabricated narrations — appearing in a
book is not the same as being authenticated.

### What the result shows

| Part                       | Shown                                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------- |
| Match (التطابق)            | Similarity %, the match type — تطابق حرفي · تطابق شبه تام · صياغة مختلفة — and the share of shared words |
| Ruling (الحكم)             | Always: the ruling and its scholar, or «لا يتوفر حكم موثّق لهذا النص في المصادر المرفوعة»              |
| Doubt (موضع الشبهة)        | The visitor's text with the words that are not in the authenticated text highlighted                   |
| Isnad tree (شجرة الإسناد)  | From the Prophet ﷺ down to each book's compiler                                                         |

The isnad tree comes from the database service (`sanad_tree`). When the same text is found in
several books, their trees are merged: shared narrators are drawn once and each book's chain
branches off where it differs (Bukhari, Abu Dawud and Ibn Majah's chains of «إنما الأعمال
بالنيات» meet at «يحيى بن سعيد الأنصاري»). A chain read automatically from the narration's
wording is labelled as such on the page. Words are compared without diacritics and with one form
of alef, ya and ta marbuta, so spelling alone is never marked as a difference.

Stylesheet and script URLs carry a hash of their content (`?v=…`), so after a deploy browsers
load the new script with the new page.

## Chat

The question is answered by the chat model from the passages the database finds for it and
for the text the visitor last verified (so "what is the ruling of this hadith?" refers to that
text). It stays within its scope and on the sources in three layers — details and measurements
in [`docs/SAFETY.md`](docs/SAFETY.md):

1. **Retrieval gate** — passages less similar to the question than `CHAT_MIN_SIMILARITY` (0.56)
   are not given to the model, nor chains that only point to a hadith elsewhere («… بمثله»);
   with none left, a fixed answer says the sources hold nothing on it, and the model isn't called.
2. **The prompt** — the rules of the challenge's reference pack: answer from the passages only,
   quote them word for word and cite each ([1], [2]…), never make up a hadith or a ruling, no
   personal fatwa (refer to a qualified scholar), refuse anything outside the scope with a fixed
   sentence, say it is an AI tool. Each hadith is named by its book and narrator, ready-made
   from the data («رواه البخاري في صحيحه عن عمر بن الخطاب رضي الله عنه»), never «according to
   the sources»: the answer gives the hadith, its meaning, then its ruling. Temperature 0.
3. **The answer check** — every quotation in the answer is compared word for word with the
   passages, every citation with the passages given, every ruling with the rulings recorded;
   what fails is shown to the visitor under the answer. A refusal comes without passages.

The chat is evaluated on a fixed set of cases (the reference pack's safety questions, made-up
hadiths, out-of-scope and rule-breaking requests), three attempts each:
`python scripts/evaluate_chat.py --url <site>` → [`docs/evaluation/results.md`](docs/evaluation/results.md).

Reasoning is switched off (`LLM_REASONING=false`): answers take a few seconds instead of ~10.

## Security

- `SITE_API_KEY` and `OPENROUTER_API_KEY` stay on the server; the page never sees them.
- Search and chat are rate limited per visitor IP (30 and 10 per minute by default) and for
  the whole site (300 and 60 per minute): the IP comes from `X-Forwarded-For`, to which a client
  can add made-up addresses, so the site-wide limit is what caps the OpenRouter bill.
- The chat history accepts only `user` / `assistant` messages — no injected system prompts.
- Content-Security-Policy allows only the site's own scripts, styles and API; the page can't be
  framed; HSTS keeps browsers on HTTPS; the interactive API docs are off.
- Everything the page shows from the database is inserted as text, never as HTML.
- The Docker image runs the site as an unprivileged user.
- Dependencies are pinned and checked for known vulnerabilities in CI.

## Project structure

```
isnad_website/
├── app/
│   ├── main.py                 # Entry point, security headers, routes
│   ├── config.py               # Settings from environment variables
│   ├── api/
│   │   ├── deps.py             # Shared clients, visitor id, "is the site open" check
│   │   └── routes/             # pages (/) · search · chat · health
│   ├── core/                   # Rate limiting, logging
│   ├── models/schemas.py       # Request and response models
│   ├── services/
│   │   ├── database.py         # Client for the database service API
│   │   ├── verification.py     # Similarity → verdict; one isnad tree for the books found
│   │   ├── isnad.py            # Match type, the words that differ (شبهة), merging trees
│   │   └── rag.py              # Chat model via OpenRouter
│   ├── templates/              # index · maintenance
│   └── static/                 # CSS · JS
├── docs/postman/               # Website and model tests for Postman
├── tests/
│   ├── unit/ · integration/ · api/ · security/ · system/   # one folder per test level
│   └── conftest.py             # fake database service and fake chat model
├── .github/workflows/ci.yml    # lint, scans, tests, Docker build on every push
├── Dockerfile
├── railway.json
├── pyproject.toml              # pytest, coverage, ruff and bandit settings
├── requirements.txt            # what the site needs to run
└── requirements-dev.txt        # + test, lint and security-scan tools
```

## Deploying to Railway

The website is a second service, next to the database service.

1. In the **same Railway project** as the database: **New** → **GitHub Repo** → `Salman-Naif/Isnad_Website`.
2. **Variables**:

   | Variable             | Value                                                            |
   | -------------------- | ---------------------------------------------------------------- |
   | `DATABASE_URL`       | the database service's URL, e.g. `https://<database-service>.up.railway.app` |
   | `SITE_API_KEY`       | the same value as `SITE_API_KEY` on the database service         |
   | `OPENROUTER_API_KEY` | your OpenRouter key                                              |
   | `PORT`               | `8000`                                                           |

3. **Settings** → **Networking** → **Generate Domain** (target port `8000`) — this is the public
   link of Isnad.
4. In the database dashboard → **التحكم بالموقع** → set the website URL, so the status page can
   check it.

No Volume is needed: the website stores nothing.

## Running locally (optional)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env — then fill in the values
uvicorn app.main:app --reload --port 8001
```

## Development and testing

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # the app's requirements + test, lint and scan tools
```

The tests are grouped by level, one folder each, and each level can be run on its own:

| Level         | Folder               | What it checks                                                        |
| ------------- | -------------------- | --------------------------------------------------------------------- |
| Unit          | `tests/unit`         | One function or class alone, no database or network                  |
| Integration   | `tests/integration`  | Components together: the database client over HTTP, the real OpenAI SDK                  |
| API           | `tests/api`          | Every endpoint's status codes, response shape and input validation    |
| Security      | `tests/security`     | Access to every route, injection, uploads, sessions, headers, secrets |
| System        | `tests/system`       | The real server as a process over real HTTP, end to end — the website and the database service (from `../Isnad_Database`, or `ISNAD_DB_REPO`) together |

```bash
pytest                      # everything
pytest -m unit              # one level: unit | integration | api | security | system
pytest --cov                # with coverage (must stay at 90% or more)
ruff check .                # lint
bandit -c pyproject.toml -r app   # code security scan
pip-audit -r requirements-dev.txt   # known vulnerabilities in dependencies
```

The tests never read your `.env` and never call OpenRouter: the model provider is replaced by
fakes, and in the system tests by a local stub server. The system tests also run the Postman
collection in `docs/postman` with Newman when Node.js is installed.

The end-to-end tests need the database service checked out next to this repository with its
own `.venv`; without it they are skipped. In CI, give the workflow read access to `Isnad_Database`
with a token in the `ISNAD_DB_TOKEN` secret if that repository is private.

**CI** (`.github/workflows/ci.yml`) runs all of this on every push to `main` and every pull
request, then builds the Docker image and checks that it starts and answers `/health`.

## Environment variables

| Variable                    | Required | Default                           |
| --------------------------- | -------- | --------------------------------- |
| `DATABASE_URL`              | Yes      | —                                 |
| `SITE_API_KEY`              | Yes      | —                                 |
| `OPENROUTER_API_KEY`        | Yes      | —                                 |
| `LLM_MODEL`                 | No       | `deepseek/deepseek-v4-flash-0731` |
| `LLM_BASE_URL`              | No       | `https://openrouter.ai/api/v1`    |
| `LLM_TIMEOUT_SECONDS`       | No       | `20`                              |
| `LLM_MAX_TOKENS`            | No       | `700`                             |
| `LLM_REASONING`             | No       | `false`                           |
| `CHAT_CONTEXT_PASSAGES`     | No       | `6`                               |
| `CHAT_MIN_SIMILARITY`      | No       | `0.56` (passages below it are not given to the model) |
| `THRESHOLD_HIGH`            | No       | `0.90`                            |
| `THRESHOLD_STRONG`          | No       | `0.75`                            |
| `THRESHOLD_MID`             | No       | `0.60`                            |
| `MIN_WORD_OVERLAP`          | No       | `0.6`                             |
| `SEARCH_PER_MINUTE`         | No       | `30`                              |
| `CHAT_PER_MINUTE`           | No       | `10`                              |
| `SEARCH_PER_MINUTE_SITE`    | No       | `300` (all visitors together)     |
| `CHAT_PER_MINUTE_SITE`      | No       | `60` (all visitors together)      |
| `DATABASE_TIMEOUT_SECONDS`  | No       | `15`                              |
| `SITE_CONFIG_CACHE_SECONDS` | No       | `30`                              |
| `LOG_LEVEL`                 | No       | `INFO`                            |
