"""Regression tests: every bug that was fixed once, and every formula the paper relies on.

Each test names the bug it guards in its docstring. Known-answer tests pin the
exact numbers of the confidence, growth, trend and priority formulas, so a change
to any of them (deliberate or not) shows up here before it shows up in results.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError

from app import llm, vector_store
from app.analytics import trends
from app.analytics.batch import previous_period
from app.config import settings
from app.ingest import chunker
from app.models import Chunk, Source
from app.rag.engine import compute_confidence, current_period

BACKEND = Path(__file__).resolve().parents[3]


# ---- ingestion bugs ------------------------------------------------------------------

def test_nested_block_text_is_indexed_once(indexed, db):
    """Bug: a <p> inside an <li> was indexed twice (fixed in chunker.iter_blocks)."""
    text = " ".join(c.text for c in db.query(Chunk).filter(Chunk.source_id == indexed.site_source["id"]))
    assert text.count("zanzibarshortcut") == 1


def test_same_site_twice_in_one_workspace_is_refused(indexed, site):
    """Bug: adding plausible.io twice doubled every retrieval hit. Now 409 in the same workspace."""
    again = indexed.post("/api/sources", json={"kind": "website", "location": f"{site}/docs/"})
    assert again.status_code == 409
    other_ws = indexed.post("/api/workspaces", json={"name": "Other"}).json()["id"]
    elsewhere = indexed.post("/api/sources", workspace=other_ws, json={"kind": "website", "location": f"{site}/docs/"})
    assert elsewhere.status_code == 201


def test_sources_left_mid_crawl_by_a_restart_are_reset(indexed, db):
    """Bug: a restart during a crawl left the source showing 'indexing' forever."""
    from app.migrate import _reset_interrupted_sources

    fresh = Source(id="src_stuck_new", organization_id=indexed.org, workspace_id=indexed.default_workspace,
                   kind="website", label="x", location="http://x", status="crawling", chunk_count=0)
    db.add(fresh)
    stuck = db.get(Source, indexed.site_source["id"])
    stuck.status = "indexing"
    db.commit()
    _reset_interrupted_sources()
    db.expire_all()
    assert db.get(Source, indexed.site_source["id"]).status == "ready"  # keeps its old chunks
    assert db.get(Source, "src_stuck_new").status == "stopped"
    assert "restart" in db.get(Source, "src_stuck_new").error


def test_chunk_windows_overlap_and_respect_the_target():
    """Chunk windows never exceed the target and consecutive windows share the overlap."""
    words = " ".join(f"w{i}" for i in range(500))
    raw = chunker.chunk_sections([chunker.Section("Long", words)], target=100, overlap=20)
    sizes = [c.word_count for c in raw]
    assert max(sizes) <= 100 and len(raw) >= 5
    for a, b in zip(raw, raw[1:]):
        assert a.text.split()[-20:] == b.text.split()[:20]


# ---- model client bugs -------------------------------------------------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def real_groq(monkeypatch, fakes):
    """The real _groq with HTTP replaced, so its own parsing and error handling run."""
    if fakes is None:
        pytest.skip("not in the live suite")
    monkeypatch.setattr(llm, "_groq", fakes.real_groq)
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    return llm, fakes.real_groq


def test_empty_reply_from_a_reasoning_model_raises(real_groq, monkeypatch):
    """Bug: openai/gpt-oss-20b spent its budget on hidden reasoning and returned empty content."""
    module, real = real_groq
    monkeypatch.setattr(module.httpx, "post", lambda *a, **k: _Resp(200, {"choices": [{"message": {"content": ""}}]}))
    with pytest.raises(module.LLMError, match="empty"):
        real("system", "user", 0.2, 100)


def test_json_mode_is_requested_for_structured_output(real_groq, monkeypatch):
    """complete_json asks Groq for a JSON object, so the model cannot wrap it in prose."""
    module, real = real_groq
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(json)
        return _Resp(200, {"choices": [{"message": {"content": '{"ok": 1}'}}]})

    monkeypatch.setattr(module.httpx, "post", post)
    monkeypatch.setattr(module, "_groq", real)
    assert module.complete_json("u", "s") == {"ok": 1}
    assert sent["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Here you go: {"a": 1} hope that helps', {"a": 1}),
        ('[1, 2]', [1, 2]),
    ],
)
def test_complete_json_tolerates_fences_and_prose(real_groq, monkeypatch, raw, expected):
    """Models wrap JSON in code fences or sentences; complete_json still parses it."""
    module, _ = real_groq
    monkeypatch.setattr(module, "_groq", lambda *a, **k: raw)
    assert module.complete_json("u", "s") == expected


def test_complete_json_raises_when_there_is_no_json(real_groq, monkeypatch):
    """No JSON at all is an LLMError, which every caller already handles."""
    module, _ = real_groq
    monkeypatch.setattr(module, "_groq", lambda *a, **k: "I cannot help with that.")
    with pytest.raises(module.LLMError):
        module.complete_json("u", "s")


def test_example_config_does_not_use_a_reasoning_model():
    """Bug: .env.example set GROQ_MODEL=openai/gpt-oss-20b under a comment saying not to."""
    example = (BACKEND / ".env.example").read_text()
    model = next(line.split("=", 1)[1] for line in example.splitlines() if line.startswith("GROQ_MODEL="))
    assert "gpt-oss" not in model
    assert settings.model_fields["groq_model"].default == "llama-3.3-70b-versatile"


# ---- known-answer formulas ---------------------------------------------------------------------

def test_confidence_formula_known_values():
    """0.6 x best + 0.4 x mean, clipped to [0, 1]; empty retrieval is 0."""
    assert compute_confidence([0.8, 0.4, 0.3]) == pytest.approx(0.6 * 0.8 + 0.4 * 0.5, abs=1e-4)
    assert compute_confidence([]) == 0.0
    assert compute_confidence([1.0, 1.0]) == 1.0


def test_similarity_is_cosine_in_zero_to_one(tenant, db):
    """Chroma returns a distance; the gateway must turn an identical vector into similarity 1."""
    ws = tenant.default_workspace
    vec = np.zeros(384, dtype=np.float32)
    vec[7] = 1.0
    vector_store.upsert(["chk_sim"], [vec], [{"source_id": "s", "workspace_id": ws, "organization_id": tenant.org}], ["x"])
    hit = vector_store.search(vec, 1, ws, tenant.org)[0]
    assert hit["similarity"] == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize("current,previous,expected", [(9, 2, 3.5), (8, 8, 0.0), (3, 6, -0.5), (5, 0, 5.0)])
def test_growth_known_values(current, previous, expected):
    """Growth is the period-over-period rate; a new topic's growth is its whole volume."""
    assert trends.compute_growth(current, previous) == expected


@pytest.mark.parametrize(
    "current,previous,expected",
    [(9, 0, "emerging"), (2, 0, "stable"), (9, 2, "emerging"), (8, 8, "recurring"), (3, 8, "stable"),
     (60, 30, "recurring")],
)
def test_trend_classification_table(current, previous, expected):
    """Emerging needs growth from a small base; steady volume is recurring; decline is stable."""
    min_size = settings.hdbscan_min_cluster_size
    if previous == 0 and current < min_size:
        expected = "stable"
    growth = trends.compute_growth(current, previous)
    assert trends.classify_trend(current, previous, growth) == expected


def test_priority_formula_known_values():
    """Weights 0.30 / 0.30 / 0.25 / 0.15, growth squashed at 3x, result clipped to [0, 1]."""
    assert trends.priority_score(1.0, 3.0, 0.0, 1.0) == 1.0
    assert trends.priority_score(0.5, 1.5, 0.6, 0.4) == pytest.approx(0.15 + 0.15 + 0.10 + 0.06, abs=1e-4)
    assert trends.priority_score(0.0, -2.0, 1.0, 0.0) == 0.0
    assert trends.priority_score(0.2, 30.0, 0.5, 0.0) == trends.priority_score(0.2, 3.0, 0.5, 0.0)


def test_periods_roll_over_the_year():
    """January's previous period is December of the year before."""
    from datetime import datetime, timezone

    assert previous_period("2026-01") == "2025-12"
    assert previous_period("2026-08") == "2026-07"
    assert current_period(datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc)) == "2026-02"


def test_report_carries_at_most_six_recommendations(indexed, db):
    """A report with eighteen actions is a report nobody acts on: it is capped at six."""
    from support import COVERED, EMERGING, TEAM, replay

    many = [{"pool": [f"{q} topic{k}" for q in pool], "counts": [0, 0, 8]}
            for k, pool in enumerate([COVERED, TEAM, EMERGING] * 3)]
    replay(db, indexed.default_workspace, plan=many)
    indexed.post("/api/analytics/run")
    assert len(indexed.get("/api/reports/latest").json()["recommendations"]) <= 6


# ---- tenancy merge ------------------------------------------------------------------------------

def test_rows_cannot_be_written_without_their_owners(db):
    """Merge guard: workspace_id and organization_id have no defaults, so a forgotten owner fails."""
    db.add(Source(id="src_orphan", kind="text", label="x", location="x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_chunks_indexed_before_tenancy_are_tagged_at_startup(tenant):
    """Chroma chunks without workspace or organisation metadata are backfilled on start."""
    from app.main import _backfill_vectors

    vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
    vector_store.upsert(["chk_legacy"], [vec], [{"source_id": "src_legacy"}], ["legacy"])
    _backfill_vectors()
    meta = vector_store._get_collection().get(ids=["chk_legacy"], include=["metadatas"])["metadatas"][0]
    assert meta["workspace_id"] == "ws_default" and meta["organization_id"] == settings.default_organization_id
    vector_store.delete_source("src_legacy")


def test_empty_overview_says_so(tenant):
    """A brand-new workspace's overview reads 'No data yet' rather than erroring."""
    overview = tenant.get("/api/overview").json()
    assert overview["period"] == "No data yet" and overview["queryCount"] == 0


# ---- whole-pipeline guards (separate processes) ----------------------------------------------------

def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    env.pop("DATABASE_URL", None)
    return subprocess.run(cmd, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=900)


def test_smoke_test_still_passes():
    """Bug: the smoke test broke silently when workspaces were added. It must stay green."""
    result = _run([sys.executable, "scripts/smoke_test.py"])
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "All checks passed" in result.stdout + result.stderr


def test_standalone_tenancy_suite_still_passes():
    """The organisation/workspace isolation and migration suite (tests/test_multitenancy.py)."""
    result = _run([sys.executable, "-m", "unittest", "tests/test_multitenancy.py"])
    assert result.returncode == 0, result.stderr[-3000:]
