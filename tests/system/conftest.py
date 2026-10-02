"""System-test fixtures: the website and the database service run as real uvicorn processes,
wired together exactly as on Railway, with OpenRouter replaced by a local stub server.

The database service's code is taken from its own repository, checked out next to this one
(../Isnad_Database — or ../Isnad_v1, its earlier name — or the ISNAD_DB_REPO environment
variable) with its virtual environment (.venv). Without it, the system tests are skipped.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.system.stub_openrouter import StubOpenRouter

APP_REPO = Path(__file__).resolve().parents[2]
_SIBLINGS = [APP_REPO.parent / name for name in ("Isnad_Database", "Isnad_v1")]
DB_REPO = Path(os.environ.get("ISNAD_DB_REPO") or next((p for p in _SIBLINGS if p.exists()), _SIBLINGS[0]))
SITE_KEY = "system-test-site-key-0123456789abcdef"
OWNER, OWNER_PASSWORD = "owner", "owner-password-1"
OWNER_NEW_PASSWORD = "owner-password-2"  # the first-start password must be replaced before uploading
DIMENSIONS = 64
STARTUP_TIMEOUT = 60

# Settings of either service that must never leak in from the test process.
SETTINGS = {
    "CHROMA_DIR", "SQLITE_PATH", "UPLOADS_DIR", "SITE_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL",
    "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "ADMIN_USERNAME", "ADMIN_PASSWORD", "DATABASE_URL",
    "LLM_BASE_URL", "LLM_MODEL", "SITE_CONFIG_CACHE_SECONDS", "OCR_ENGINE", "LOG_LEVEL",
}


def db_python() -> Path | None:
    for candidate in (DB_REPO / ".venv" / "Scripts" / "python.exe", DB_REPO / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServiceProcess:
    def __init__(self, name: str, python: Path | str, repo: Path, workdir: Path, env: dict[str, str]) -> None:
        self.name = name
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.log = workdir / f"{name}.log"
        # Started from its own empty folder, so no developer .env is read.
        self.workdir = workdir / name
        self.workdir.mkdir()
        self.command = [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)]
        self.env = {
            **{k: v for k, v in os.environ.items() if k.upper() not in SETTINGS},
            "PYTHONPATH": str(repo), "PYTHONIOENCODING": "utf-8", "LOG_LEVEL": "WARNING", **env,
        }
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        self.process = subprocess.Popen(  # noqa: S603 — fixed command, test-only
            self.command, cwd=self.workdir, env=self.env, stdout=self.log.open("ab"), stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.name} exited:\n{self.log.read_text(encoding='utf-8', errors='replace')}")
            try:
                if httpx.get(f"{self.url}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.2)
        raise RuntimeError(f"{self.name} did not start:\n{self.log.read_text(encoding='utf-8', errors='replace')}")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()


@pytest.fixture(scope="module")
def openrouter():
    with StubOpenRouter(DIMENSIONS) as stub:
        yield stub


@pytest.fixture(scope="module")
def database_service(tmp_path_factory, openrouter):
    python = db_python()
    if python is None:
        pytest.skip(f"database service not found at {DB_REPO} (with .venv) — set ISNAD_DB_REPO")
    work = tmp_path_factory.mktemp("isnad-db")
    service = ServiceProcess("database", python, DB_REPO, work, {
        "CHROMA_DIR": str(work / "chroma"), "SQLITE_PATH": str(work / "isnad.db"),
        "UPLOADS_DIR": str(work / "uploads"), "SITE_API_KEY": SITE_KEY,
        "OPENROUTER_API_KEY": "sk-or-system-test", "OPENROUTER_BASE_URL": openrouter.url,
        "EMBEDDING_MODEL": "stub/embedding", "EMBEDDING_DIMENSIONS": str(DIMENSIONS),
        "ADMIN_USERNAME": OWNER, "ADMIN_PASSWORD": OWNER_PASSWORD,
    })
    service.start()
    yield service
    service.stop()


@pytest.fixture(scope="module")
def website_service(tmp_path_factory, openrouter, database_service):
    work = tmp_path_factory.mktemp("isnad-app")
    service = ServiceProcess("website", sys.executable, APP_REPO, work, {
        "DATABASE_URL": database_service.url, "SITE_API_KEY": SITE_KEY,
        "OPENROUTER_API_KEY": "sk-or-system-test", "LLM_BASE_URL": openrouter.url,
        "SITE_CONFIG_CACHE_SECONDS": "0",  # dashboard switches apply at once in these tests
    })
    service.start()
    yield service
    service.stop()


@pytest.fixture
def owner(database_service):
    """The team member in the database dashboard."""
    with httpx.Client(base_url=database_service.url, timeout=30) as client:
        res = client.post("/api/auth/login", json={"username": OWNER, "password": OWNER_NEW_PASSWORD})
        if res.status_code == 401:
            # First sign-in: the database refuses to act until the first-start password is replaced.
            res = client.post("/api/auth/login", json={"username": OWNER, "password": OWNER_PASSWORD})
            assert res.status_code == 200, res.text
            change = client.post("/api/auth/change-password", json={
                "current_password": OWNER_PASSWORD, "new_password": OWNER_NEW_PASSWORD})
            assert change.status_code == 204, change.text
        assert res.status_code == 200, res.text
        yield client


@pytest.fixture
def visitor(website_service):
    """A visitor's browser on the public website."""
    with httpx.Client(base_url=website_service.url, timeout=30) as client:
        yield client
