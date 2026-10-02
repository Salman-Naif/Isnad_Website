# Third-party components, services, models and data

The Isnad team's own code and documentation are under the MIT License (`LICENSE`). Everything
below belongs to its authors and keeps its own license or terms. Nothing listed here is copied
into this repository except where said; Python packages are installed from PyPI at build time.

Versions are the ones pinned in `requirements.txt` / `requirements-dev.txt`; licenses are read
from each package's metadata (checked 2026-10-02).

## Python packages (runtime)

| Package | Version | License | Used for |
| --- | --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.141.1 | MIT | Web framework |
| [Uvicorn](https://uvicorn.dev/) | 0.54.0 | BSD-3-Clause | ASGI server |
| [Jinja2](https://github.com/pallets/jinja/) | 3.1.6 | BSD-3-Clause | HTML templates |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.13.5 | MIT | Data validation |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 2.15.0 | MIT | Settings from environment variables |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.3 | BSD-3-Clause | Local `.env` files |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | Calls to the database service |
| [openai](https://github.com/openai/openai-python) (Python client) | 1.59.7 | Apache-2.0 | Calls to OpenRouter's OpenAI-compatible API |

## Development and testing tools (not in the image)

| Package | License |
| --- | --- |
| pytest 9.1.1, pytest-cov 7.1.0, Ruff 0.16.9 | MIT |
| Bandit 1.9.4, pip-audit 2.10.1 | Apache-2.0 |
| [Newman](https://github.com/postmanlabs/newman) 6 (run through `npx` by the system tests) | Apache-2.0 |

## In the Docker image

| Component | License |
| --- | --- |
| Python 3.11.9 (`python:3.11.9-slim`, Debian) | PSF License; Debian packages under their own licenses |

## Services and AI models (called through APIs, never redistributed)

| Service / model | Terms | Used for |
| --- | --- | --- |
| [OpenRouter](https://openrouter.ai) | [OpenRouter Terms](https://openrouter.ai/terms) and each provider's terms | Gateway to the chat model |
| `deepseek/deepseek-v4-flash-0731` (DeepSeek), set by `LLM_MODEL` | DeepSeek's model license and the serving provider's terms | Chat answers, from the retrieved passages only |
| The Isnad database service ([Isnad_Database](https://github.com/Salman-Naif/Isnad_Database), MIT) | — | Search, rulings, isnad trees; its own models are listed in its `THIRD_PARTY_LICENSES.md` |
| [Railway](https://railway.com) | Railway's terms | Hosting |

Search texts and chat questions are sent to OpenRouter to be processed; the page says so
(footer → «الخصوصية»).

## Data

The website holds no hadith data of its own: it shows what the database service returns. The
sources, their licenses and how they are used are documented in the database repository's
[`docs/DATA_SOURCES.md`](https://github.com/Salman-Naif/Isnad_Database/blob/main/docs/DATA_SOURCES.md).

The chat's evaluation set (`docs/evaluation/chat_cases.json`) adapts the safety test questions of
the challenge's reference pack («المرجعية والحزمة العلمية والبيانات»، أمثلة لأسئلة اختبار التأكد
من سلامة المحتوى).

## Icons and fonts

The page's icons are drawn inline in `app/templates/base.html` after the paths of
[Feather Icons](https://github.com/feathericons/feather) (MIT, © Cole Bemis). No font is
bundled: the page uses the visitor's system fonts.
