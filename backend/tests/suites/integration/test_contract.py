"""Frontend-backend contract: every API response has the fields the frontend's types declare.

The frontend's interfaces are read from frontend/src/lib/types.ts by
frontend/scripts/export-api-types.mjs (run-tests does this first). If a backend
schema drops or renames a field the frontend relies on, this fails here rather
than as a blank panel in the browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GENERATED = HERE.parent / ".generated" / "frontend_types.json"
FRONTEND = HERE.parents[3] / "frontend"


@pytest.fixture(scope="module")
def ts_types() -> dict:
    if not GENERATED.exists():
        node = shutil.which("node")
        script = FRONTEND / "scripts" / "export-api-types.mjs"
        if not node or not script.exists() or not (FRONTEND / "node_modules" / "typescript").exists():
            pytest.skip("frontend types not exported: run `npm ci` in frontend/ and use run-tests")
        GENERATED.parent.mkdir(exist_ok=True)
        GENERATED.write_text(subprocess.run([node, str(script)], capture_output=True, text=True, check=True).stdout)
    return json.loads(GENERATED.read_text(encoding="utf-8-sig"))  # PowerShell may add a BOM


def check(value, interface: str, types: dict, where: str) -> list[str]:
    """Missing required fields, recursively through nested interfaces and arrays."""
    problems = []
    for name, spec in types[interface].items():
        if name not in value or value[name] is None:
            if not spec["optional"] and not (name in value and spec.get("nullable")):
                problems.append(f"{where}.{name} missing (required by {interface})")
            continue
        items = value[name] if spec.get("array") else [value[name]]
        for n, item in enumerate(items[:3]):
            path = f"{where}.{name}[{n}]" if spec.get("array") else f"{where}.{name}"
            if spec.get("ref") in types:
                problems += check(item, spec["ref"], types, path)
            elif "props" in spec:
                problems += check(item, "__inline__", {**types, "__inline__": spec["props"]}, path)
    return problems


def assert_matches(value, interface, types, where):
    rows = value if isinstance(value, list) else [value]
    assert rows, f"{where} returned nothing to check"
    problems = [p for n, row in enumerate(rows) for p in check(row, interface, types, f"{where}[{n}]")]
    assert not problems, "\n".join(problems)


def test_contract_for_every_screen(with_traffic, ts_types, db):
    """Each endpoint the frontend calls returns the shape its TypeScript type expects."""
    t = with_traffic
    from app.models import EvaluationRun

    db.add(EvaluationRun(id="eval_contract", organization_id=t.org, workspace_id=t.default_workspace,
                         question_count=1, failures=[{"question": "q", "metric": "faithfulness", "score": 0.2}]))
    db.commit()

    insight = t.get("/api/insights").json()[0]["id"]
    endpoints = [
        ("/api/workspaces", "Workspace"),
        ("/api/sources", "Source"),
        ("/api/overview", "Overview"),
        ("/api/insights", "Insight"),
        (f"/api/insights/{insight}", "InsightDetail"),
        ("/api/reports/latest", "Report"),
        ("/api/reports", "ReportSummary"),
        ("/api/evaluation/latest", "EvaluationRun"),
    ]
    for path, interface in endpoints:
        assert_matches(t.get(path).json(), interface, ts_types, path)
    assert_matches(t.ask("edit an invoice", session_id="sess_contract"), "Message", ts_types, "/api/chat")
    assert_matches(t.get("/api/chat/history?session_id=sess_contract").json(), "Message", ts_types,
                   "/api/chat/history")
    assert_matches(t.get("/api/auth/me").json(), "AuthUser", ts_types, "/api/auth/me")
    login = t.client.post("/api/auth/login", json={"email": t.email, "password": t.password}).json()
    assert_matches(login, "AuthSession", ts_types, "/api/auth/login")
    periods = t.get("/api/periods").json()
    assert isinstance(periods, list) and all(isinstance(p, str) for p in periods)


def test_contract_for_workspace_writes(tenant, ts_types):
    """POST and PATCH /api/workspaces return a full Workspace."""
    created = tenant.post("/api/workspaces", json={"name": "Contract"}).json()
    assert_matches(created, "Workspace", ts_types, "POST /api/workspaces")
    patched = tenant.patch(f"/api/workspaces/{created['id']}", json={"name": "C2"}).json()
    assert_matches(patched, "Workspace", ts_types, "PATCH /api/workspaces")


def test_enumerations_match(with_traffic, ts_types):
    """Trend states and recommendation categories are values the frontend knows."""
    trends = {"recurring", "emerging", "stable"}
    categories = {"product", "documentation", "faq", "customer_issue"}
    assert {i["trend"] for i in with_traffic.get("/api/insights").json()} <= trends
    assert {r["category"] for r in with_traffic.get("/api/reports/latest").json()["recommendations"]} <= categories
