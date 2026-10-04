"""
Measure the website's verdicts against its verification cases and write a report.

    python scripts/measure_verification.py --url http://127.0.0.1:8000

Each case in docs/evaluation/verification_cases.json is searched once through the site's own
API (/api/search) — the database's search and the site's verdict rules together. A case passes
when the verdict is the one its kind expects and, for a hadith, the first result is that hadith.
The report goes to docs/evaluation/verification.md (and verification.json beside it).

Every search is counted in the database's statistics like a visitor's, and the site allows 30 a
minute from one address (SEARCH_PER_MINUTE): a local copy with the limit raised is best, or
--pause 2 against the live site.
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles can't print Arabic otherwise

CASES = ROOT / "docs" / "evaluation" / "verification_cases.json"
OUT = ROOT / "docs" / "evaluation"
SAME_TEXT = ("verified", "found")
EXPECTED = {
    "exact": SAME_TEXT, "first5": SAME_TEXT,
    "missing2": ("distorted",), "changed1": ("distorted",),
    # a visitor's words can be one of the hadith's own wordings («من لم يشكر الناس لم يشكر الله»)
    "own_words": ("distorted", *SAME_TEXT),
    "not_in_sources": ("no_match",),
}
# The same hadith, for an altered quote: the first result holds 8 of the 10 words it was made
# from — in another book's wording as well, which differs by a word or two.
SAME_HADITH_SHARE = 0.8
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟـ]")
_NOT_WORD = re.compile(r"[^\w\s]")
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def plain(text: str) -> str:
    """For comparing words: no diacritics or punctuation, one form of alef, ya and ta marbuta."""
    text = text.replace("ﷺ", "صلى الله عليه وسلم")
    return " ".join(_NOT_WORD.sub(" ", _DIACRITICS.sub("", text)).translate(_LETTERS).split())


def search(client: httpx.Client, query: str, pause: float) -> dict:
    for attempt in range(5):
        res = client.post("/api/search", json={"query": query, "top_k": 5})
        time.sleep(pause)
        if res.status_code == 200:
            return res.json()
        if res.status_code not in (429, 503):
            res.raise_for_status()
        time.sleep(15 * (attempt + 1))  # the site's rate limit, or the database slow to answer
    return {"verdict": f"no answer: HTTP {res.status_code}", "results": []}


def holds(expected: str, text: str, kind: str) -> bool:
    if kind in ("missing2", "changed1"):
        words, present = plain(expected).split(), set(plain(text).split())
        return sum(w in present for w in words) >= SAME_HADITH_SHARE * len(words)
    return plain(expected) in plain(text)


def judge(case: dict, body: dict) -> dict:
    top = body["results"][0] if body["results"] else None
    right = case["kind"] == "not_in_sources" or bool(
        top and any(holds(e, top["text"], case["kind"]) for e in case["expect"]))
    return {
        **case, "verdict": body["verdict"], "right_hadith_first": right,
        "passed": body["verdict"] in EXPECTED[case["kind"]] and right,
        "similarity": top["similarity"] if top else 0.0,
        "word_overlap": top["word_overlap"] if top else 0.0,
        # without the edition's diacritics: the report quotes the classical text, not the edition
        "first_result": f"{top['source']}: {_DIACRITICS.sub('', top['text'])[:100]}" if top else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the verdicts against the verification cases")
    parser.add_argument("--url", required=True, help="the website, e.g. http://127.0.0.1:8000")
    parser.add_argument("--workers", type=int, default=4, help="searches at the same time")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait after each search")
    parser.add_argument("--note", default="", help="what was measured, for the report (e.g. which data)")
    args = parser.parse_args()

    spec = json.loads(CASES.read_text(encoding="utf-8"))

    def run(case: dict) -> dict:
        with httpx.Client(base_url=args.url.rstrip("/"), timeout=60) as client:
            row = judge(case, search(client, case["query"], args.pause))
        print(f"{'✓' if row['passed'] else '✗'} {row['id']} {row['kind']:<15} {row['verdict']:<10} "
              f"{row['query']}", flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(run, spec["cases"]))
    write_report(rows, spec, args)


def write_report(rows: list[dict], spec: dict, args) -> None:
    (OUT / "verification.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    verdicts = ("verified", "found", "distorted", "no_match")
    lines = [
        "# Verification — results",
        "",
        f"Run on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC against `{args.url}`, with "
        f"`scripts/measure_verification.py` and the cases in `verification_cases.json`."
        + (f" {args.note}" if args.note else ""),
        "",
        spec["about"],
        "",
        f"**{sum(r['passed'] for r in rows)}/{len(rows)} cases reached the expected verdict.**",
        "",
        "| Kind | Expected | Cases | Passed | Right hadith first | " + " | ".join(verdicts) + " |",
        "| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in verdicts) + " |",
    ]
    for kind, expected in spec["kinds"].items():
        group = [r for r in rows if r["kind"] == kind]
        if not group:
            continue
        right = "—" if kind == "not_in_sources" else f"{sum(r['right_hadith_first'] for r in group)}"
        counts = " | ".join(str(sum(r["verdict"] == v for r in group)) for v in verdicts)
        lines.append(f"| {kind} | {expected} | {len(group)} | {sum(r['passed'] for r in group)} | {right} | {counts} |")
    lines += ["", "## Cases that did not pass", "", "| Case | Kind | Query | Verdict | Similarity | First result |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if not r["passed"]:
            first = r["first_result"].replace("|", "/").replace("\n", " ")
            lines.append(f"| {r['id']} | {r['kind']} | {r['query']} | {r['verdict']} | {r['similarity']} | {first} |")
    (OUT / "verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n→ {OUT / 'verification.md'}")


if __name__ == "__main__":
    main()
