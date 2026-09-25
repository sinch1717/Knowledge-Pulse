"""Shared set-up for the integration, acceptance, regression and live suites.

Isolation. Every run gets a fresh temporary SQLite database, Chroma directory
and upload folder. The backend's .env is not read (so a DATABASE_URL pointing at
Neon can never be touched), except by the live suite, which needs the API keys
and still uses temporary storage.

Tenancy as the isolation tool. Each test gets its own organisation id, so tests
never see each other's data even though they share one database. That also
exercises the tenant boundary on every single test.

Reports. Results are written to test-reports/ (override with KP_REPORT_DIR):
<layer>-results.json and, when acceptance tests ran, traceability.md mapping
every FR/NFR in the project report to the tests that cover it.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
from collections import defaultdict
from functools import partial
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SUITES = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SUITES))
os.chdir(BACKEND)  # relative paths in the app (data/research, data/eval_set) resolve as in production
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import logging  # noqa: E402

# Chroma 0.5.5 logs a harmless telemetry TypeError on every call; keep reports readable.
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

LIVE = os.environ.get("KP_LIVE") == "1"
TMP = Path(tempfile.mkdtemp(prefix="kp_tests_"))

# ---- settings: must be replaced before any other app module is imported --------
import app.config as config_module  # noqa: E402

config_module.get_settings.cache_clear()
config_module.settings = config_module.Settings(
    _env_file=".env" if LIVE else None,
    database_url=f"sqlite:///{TMP}/suite.db",
    chroma_path=str(TMP / "chroma"),
    upload_path=str(TMP / "uploads"),
    crawl_delay_seconds=0.0,
    crawl_timeout_seconds=5,
    hdbscan_min_cluster_size=4,
    umap_neighbours=5,
    internal_api_key="test-internal-key",
    demo_user_email="demo@test.local",
    demo_user_password="demo-password-for-tests",
    demo_user_name="Demo",
    **({} if LIVE else {"llm_provider": "groq", "groq_api_key": "test-key-not-used"}),
)
settings = config_module.settings

from support import FakeEmbeddingModel, FakeLLM, new_org  # noqa: E402

import app.auth as auth_module  # noqa: E402

# Password hashing is deliberately slow; tests create a user per test.
auth_module.PBKDF2_ITERATIONS = 1_000
INTERNAL_KEY = settings.internal_api_key

LAYERS = ("integration", "acceptance", "regression", "live")


# ---- markers and layers ----------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "req(*ids): requirement ids from the project report (FR1-FR18, NFR1-NFR10)")
    for layer in LAYERS:
        config.addinivalue_line("markers", f"{layer}: {layer} test (applied from the folder name)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        parts = Path(str(item.fspath)).parts
        for layer in LAYERS:
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
        if "live" in parts and not LIVE:
            item.add_marker(pytest.mark.skip(reason="live suite: set KP_LIVE=1 and API keys in backend/.env"))


# ---- fakes -----------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def fakes():
    """Swap the embedding model and the LLM transport for deterministic fakes."""
    from app import embeddings, llm

    if LIVE:
        yield None
        return
    fake_llm = FakeLLM()
    original_model, original_groq = embeddings._model, llm._groq
    fake_llm.real_groq = original_groq  # for the regression tests of the client itself
    embeddings._model = FakeEmbeddingModel()
    llm._groq = fake_llm
    yield fake_llm
    embeddings._model, llm._groq = original_model, original_groq


@pytest.fixture
def fake_llm(fakes):
    """The fake LLM, reset to healthy after the test whatever the test did to it."""
    if fakes is None:
        pytest.skip("fake LLM not used in the live suite")
    fakes.mode = "ok"
    fakes.calls.clear()
    yield fakes
    fakes.mode = "ok"
    fakes.judge_score = "0.90"


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Scripts and the evaluator pause between API calls for rate limits."""
    import time

    if not LIVE:
        monkeypatch.setattr(time, "sleep", lambda *_: None)


# ---- app and HTTP ---------------------------------------------------------------

@pytest.fixture(scope="session")
def client(fakes):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:  # runs the lifespan: migration, vector backfill
        yield test_client


@pytest.fixture
def db():
    from app.db import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


class Tenant:
    """One organisation with one signed-in user, talking to the API the way the frontend does:
    a bearer token from /api/auth/login, and X-Workspace-Id for the selected workspace."""

    def __init__(self, client, org: str):
        from app.db import SessionLocal

        self.client = client
        self.org = org
        self.workspace: str | None = None  # None: the organisation's default
        self.email = f"{org}@test.local"
        self.password = f"pw-{org}"
        db = SessionLocal()
        try:
            auth_module.create_or_update_user(db, self.email, self.password, f"User of {org}", org)
        finally:
            db.close()
        self.token = self.sign_in()

    def sign_in(self) -> str:
        resp = self.client.post("/api/auth/login", json={"email": self.email, "password": self.password})
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def headers(self, workspace: str | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.token}"}
        ws = workspace or self.workspace
        if ws:
            h["X-Workspace-Id"] = ws
        return h

    def internal_headers(self, workspace: str | None = None) -> dict:
        """As a trusted server-to-server caller: internal key plus organisation header."""
        h = {"X-Internal-Key": INTERNAL_KEY, "X-Organization-Id": self.org}
        if workspace:
            h["X-Workspace-Id"] = workspace
        return h

    def request(self, method: str, path: str, workspace: str | None = None, **kw):
        return self.client.request(method, path, headers=self.headers(workspace), **kw)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    @property
    def default_workspace(self) -> str:
        return next(w["id"] for w in self.get("/api/workspaces").json() if w["isDefault"])

    def add_website(self, url: str, **kw) -> dict:
        """Add a website source. TestClient runs the background crawl before returning."""
        resp = self.post("/api/sources", json={"kind": "website", "location": url, **kw})
        assert resp.status_code == 201, resp.text
        return self.source(resp.json()["id"])

    def source(self, source_id: str) -> dict:
        return next(s for s in self.get("/api/sources").json() if s["id"] == source_id)

    def ask(self, question: str, session_id: str = "sess_test") -> dict:
        resp = self.post("/api/chat", json={"question": question, "session_id": session_id})
        assert resp.status_code == 200, resp.text
        return resp.json()


@pytest.fixture
def tenant(client) -> Tenant:
    return Tenant(client, new_org())


@pytest.fixture
def make_tenant(client):
    return lambda: Tenant(client, new_org())


# ---- fixture documentation site ----------------------------------------------------

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output clean
        pass


@pytest.fixture(scope="session")
def site():
    """The fixture docs site served over real HTTP on a free local port."""
    root = SUITES / "fixtures" / "site"
    handler = partial(_QuietHandler, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def indexed(tenant, site) -> Tenant:
    """A tenant with the fixture docs site crawled and indexed."""
    source = tenant.add_website(f"{site}/docs/")
    assert source["status"] == "ready", source
    tenant.site_source = source
    return tenant


@pytest.fixture
def with_traffic(indexed, db) -> Tenant:
    """Indexed tenant with three periods of planted traffic and the batch run."""
    from support import replay

    indexed.questions_logged = replay(db, indexed.default_workspace)
    resp = indexed.post("/api/analytics/run")
    assert resp.status_code == 202
    return indexed


# ---- results and traceability ---------------------------------------------------------

_results: list[dict] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    final = report.when == "call" or (report.when == "setup" and not report.passed)
    if not final:
        return
    if hasattr(report, "wasxfail"):
        status = "xfailed" if report.skipped else "xpassed"
    else:
        status = report.outcome
    reqs = [r for m in item.iter_markers("req") for r in m.args]
    layer = next((m.name for m in item.iter_markers() if m.name in LAYERS), "other")
    doc = (item.function.__doc__ or "").strip().splitlines()
    _results.append({
        "id": item.nodeid,
        "layer": layer,
        "requirements": reqs,
        "status": status,
        "title": doc[0] if doc else item.name,
        "seconds": round(report.duration, 3),
        "reason": str(getattr(report, "wasxfail", "")).removeprefix("reason: ") or (str(report.longrepr)[:300] if report.failed else ""),
    })


def pytest_sessionfinish(session, exitstatus):
    if not _results:
        return
    out = Path(os.environ.get("KP_REPORT_DIR", BACKEND / "test-reports"))
    out.mkdir(parents=True, exist_ok=True)
    layers = sorted({r["layer"] for r in _results})
    name = layers[0] if len(layers) == 1 else "all"
    (out / f"{name}-results.json").write_text(json.dumps(_results, indent=2))

    if "acceptance" in layers:
        from requirements_catalogue import REQUIREMENTS

        by_req = defaultdict(list)
        for r in _results:
            for req in r["requirements"]:
                by_req[req].append(r)
        lines = ["# Requirement traceability", "",
                 "| Req | Requirement | Tests | Result |", "|---|---|---|---|"]
        for req, text in REQUIREMENTS.items():
            tests = by_req.get(req, [])
            if not tests:
                verdict = "NOT COVERED"
            elif any(t["status"] == "failed" for t in tests):
                verdict = "FAIL"
            elif any(t["status"] == "xfailed" and t["reason"].startswith("Defect") for t in tests):
                verdict = "FAIL (open defect)"
            elif any(t["status"] == "xfailed" for t in tests):
                verdict = "PARTIAL (known gap)"
            else:
                verdict = "PASS"
            names = "<br>".join(t["id"].split("::")[-1] for t in tests) or "-"
            lines.append(f"| {req} | {text} | {names} | {verdict} |")
        (out / "traceability.md").write_text("\n".join(lines) + "\n")
