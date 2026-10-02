# Postman tests — website and model

Tests for the public website: verification, chat with the model (answered only from the
database sources), and the OpenRouter model itself. The database's own tests live in the
**Isnad_Database** repository.

| File                                  | What it is                                           |
| ------------------------------------- | ---------------------------------------------------- |
| `Isnad_App.postman_collection.json`   | All requests, with automatic checks                  |
| `Isnad_App.postman_environment.json`  | Variables (URL, key, questions) — the key is empty   |

## Setup

1. Postman → **Import** → the collection file, then the environment file.
2. Top-right environment selector → **Isnad App**.
3. Fill the **Current value** column (never *Initial value*, which syncs to Postman's cloud):
   - `app_url` — the website URL, no trailing slash
   - `query` — a text from your uploaded sources (or a reworded version of one)
   - `openrouter_key` — only for folder C
4. **Save**.

## Folders

- **A — run in order.** 1 health · 2 verify `query` (verdict, similarity, ruling — printed in the
  Console) · 3 ask the model about that text · 4 ask about a hadith that is *not* in the
  sources — the model must say so instead of answering from its own knowledge.
- **B — must be rejected (422):** an empty query, and a chat history that tries to inject a
  "system" instruction.
- **C — the model directly:** the OpenRouter key works and the configured model exists.

Each visit, verification and question made here also shows up in the database dashboard's
statistics — use a separate environment or remember that when reading the reports.
