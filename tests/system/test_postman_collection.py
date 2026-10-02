"""System tests: the Postman collection in docs/postman, run by Newman against the live website
(wired to the live database service). Folder C and request A-4 need the real OpenRouter model
and are left out. Needs Node.js (npx); skipped without it."""

import json
import shutil
import subprocess

import pytest

from tests.system.conftest import APP_REPO
from tests.system.test_end_to_end import HADITHS, test_team_uploads_approved_hadiths

COLLECTION = APP_REPO / "docs" / "postman" / "Isnad_App.postman_collection.json"
NPX = shutil.which("npx")


@pytest.mark.skipif(NPX is None, reason="Node.js (npx) is not installed")
def test_postman_collection_passes_against_the_live_site(owner, website_service, tmp_path):
    test_team_uploads_approved_hadiths(owner)  # this module's own database service starts empty

    collection = json.loads(COLLECTION.read_text(encoding="utf-8"))
    collection["item"] = [folder for folder in collection["item"] if not folder["name"].startswith("C")]
    # Request A-4 checks the real model admits a question is outside the sources; the stub
    # model gives one fixed answer, so that check belongs to a run against the real model.
    for folder in collection["item"]:
        folder["item"] = [item for item in folder["item"] if not item["name"].startswith("4 ")]
    local = tmp_path / "collection.json"
    local.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")

    report = tmp_path / "newman.json"
    variables = {"app_url": website_service.url, "query": HADITHS[0]["text"],
                 "question": "ما حكم هذا الحديث؟", "outside_question": "ما حكم حديث لا يوجد في المصادر؟"}
    command = [NPX, "--yes", "newman@6", "run", str(local), "--reporters", "json",
               "--reporter-json-export", str(report)]
    for key, value in variables.items():
        command += ["--env-var", f"{key}={value}"]
    result = subprocess.run(  # noqa: S603 — fixed command, test-only
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    run = json.loads(report.read_text(encoding="utf-8"))["run"]
    failures = [f"{f['source']['name']}: {f['error']['message']}" for f in run["failures"]]
    assert result.returncode == 0 and not failures, failures or result.stdout[-2000:]
    assert run["stats"]["assertions"]["total"] >= 6
