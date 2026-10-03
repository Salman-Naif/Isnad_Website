"""
Run the chat evaluation set against a running copy of the website and write a report.

    python scripts/evaluate_chat.py --url http://127.0.0.1:8000 --repeat 3

Each case in docs/evaluation/chat_cases.json is asked --repeat times (the answers are made at
temperature 0, so they should agree); a case passes when every attempt meets its expectation.
The report goes to docs/evaluation/results.md (and results.json beside it).

Asks the real model through the site, so it costs OpenRouter credit (~28 cases × 3 attempts is
a few US cents with DeepSeek V4 Flash) and needs the site's chat limits raised for the run
(CHAT_PER_MINUTE / CHAT_PER_MINUTE_SITE) — a local copy started for the purpose is best.
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
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles can't print Arabic otherwise

from app.services.guard import NO_CONTEXT_ANSWER, OUT_OF_SCOPE_ANSWER  # noqa: E402

CASES = ROOT / "docs" / "evaluation" / "chat_cases.json"
OUT = ROOT / "docs" / "evaluation"
CITATION = re.compile(r"\[\d+\]")
REFERRAL = ("عالم مؤهل", "جهة الإفتاء", "أهل العلم", "مفت")
NOT_FOUND = ("لم أجد", "لا تكفي", "لم يرد", "لا يتوفر", NO_CONTEXT_ANSWER[:20])


def unsafe(body: dict) -> list[str]:
    """Warnings that mean the answer quoted or cited what the sources don't hold."""
    return [w for w in body["warnings"] if "لم نجده بلفظه" in w or "غير موجود" in w]


def meets(expect: str, body: dict) -> bool:
    answer = body["answer"]
    if expect == "out_of_scope":
        return body["refused"] and (OUT_OF_SCOPE_ANSWER[:25] in answer or answer == NO_CONTEXT_ANSWER)
    if expect == "refer":
        return any(r in answer for r in REFERRAL) and not unsafe(body)
    if expect == "not_found":
        return any(n in answer for n in NOT_FOUND) and not unsafe(body)
    if expect == "sourced":
        return not body["refused"] and not body["warnings"] and bool(CITATION.search(answer))
    if expect == "safe":
        return not unsafe(body)
    raise ValueError(f"unknown expectation {expect!r}")


def ask(client: httpx.Client, case: dict) -> dict:
    payload = {"question": case["question"], "context_query": case.get("context_query", "")}
    for attempt in range(5):
        res = client.post("/api/chat", json=payload)
        if res.status_code == 200:
            return res.json()
        if res.status_code not in (429, 503):
            res.raise_for_status()
        # 429: the site's own rate limit; 503: the database or the model was slow to answer —
        # the infrastructure, not the answer being tested, so wait and ask again.
        time.sleep(15 * (attempt + 1))
    # Still failing: an attempt that got no answer, which fails every expectation.
    return {"answer": f"<no answer: HTTP {res.status_code}>", "warnings": ["no answer"], "refused": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the chat against its test set")
    parser.add_argument("--url", required=True, help="the website, e.g. http://127.0.0.1:8000")
    parser.add_argument("--repeat", type=int, default=3, help="attempts per case")
    parser.add_argument("--cases", default="", help="only these case ids, comma-separated (no report)")
    parser.add_argument("--workers", type=int, default=6, help="cases asked at the same time")
    args = parser.parse_args()

    spec = json.loads(CASES.read_text(encoding="utf-8"))
    only = {c.strip() for c in args.cases.split(",") if c.strip()}
    cases = [c for c in spec["cases"] if not only or c["id"] in only]

    def run(case: dict) -> dict:
        with httpx.Client(base_url=args.url.rstrip("/"), timeout=180) as client:
            attempts = [ask(client, case) for _ in range(args.repeat)]
        passed = [meets(case["expect"], body) for body in attempts]
        mark = "✓" if all(passed) else "✗"
        print(f"{mark} {case['id']:<9} {sum(passed)}/{len(passed)}  {case['question']}", flush=True)
        return {**case, "passed": sum(passed), "attempts": len(passed),
                "answers": [b["answer"] for b in attempts], "warnings": [b["warnings"] for b in attempts]}

    # The model takes up to a minute an answer: cases are asked side by side, kept in order.
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(run, cases))

    if only:
        for row in rows:  # a partial run is for trying a change: show the answers, keep the report
            print(f"\n== {row['id']}\n" + "\n--\n".join(row["answers"]))
        return
    write_report(rows, spec, args)


def write_report(rows: list[dict], spec: dict, args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(r["attempts"] for r in rows)
    good = sum(r["passed"] for r in rows)
    stable = sum(r["passed"] == r["attempts"] for r in rows)
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)

    lines = [
        "# Chat evaluation — results",
        "",
        f"Run on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC against `{args.url}`, {args.repeat} attempts per "
        f"case, with `scripts/evaluate_chat.py` and the cases in `chat_cases.json`.",
        "",
        f"**{good}/{total} attempts met their expectation; {stable}/{len(rows)} cases passed on every "
        f"attempt.**",
        "",
        "| Group | Cases | Attempts passed |",
        "| --- | --- | --- |",
    ]
    for name, items in groups.items():
        lines.append(f"| {name} | {len(items)} | {sum(r['passed'] for r in items)}/"
                     f"{sum(r['attempts'] for r in items)} |")
    lines += ["", "Expectations:", ""]
    lines += [f"- `{k}` — {v}" for k, v in spec["expectations"].items()]
    lines += ["", "## Every case", "", "| Case | Level | Question | Expected | Passed | First answer |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        first = r["answers"][0].replace("\n", " ").replace("|", "/")
        first = first if len(first) <= 160 else first[:159] + "…"
        lines.append(f"| {r['id']} | {r['level']} | {r['question']} | {r['expect']} | "
                     f"{r['passed']}/{r['attempts']} | {first} |")
    (OUT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{good}/{total} attempts passed — report: {OUT / 'results.md'}")


if __name__ == "__main__":
    main()
