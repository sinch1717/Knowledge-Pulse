"""Acceptance tests for the non-functional requirements in section 6.4 of the report.

Timing figures here measure the system's own plumbing with the model and the
embedder stubbed out. They show the pipeline adds no meaningful delay; the
model's own latency is measured by the live suite.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import pytest
from support import COVERED, DEFAULT_PLAN, EMERGING, PERIODS, TEAM, replay

from app.models import Chunk, ClusterMember, Message, Recommendation, Source, TopicCluster

req = pytest.mark.req
BACKEND = Path(__file__).resolve().parents[3]
PROJECT = BACKEND.parent
APP = BACKEND / "app"

JARGON = ("embedding", "vector", "cosine", "hdbscan", "umap", "chunk", "retrieval", "similarity", "llm", "centroid")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return names


# ---- NFR1 performance -------------------------------------------------------------------

@req("NFR1")
def test_nfr1_chat_pipeline_overhead_is_well_under_a_few_seconds(indexed):
    """Retrieval, scoring, logging and HTTP together take under 1 s per question (model excluded)."""
    timings = []
    for q in COVERED + TEAM:
        start = time.perf_counter()
        indexed.ask(q)
        timings.append(time.perf_counter() - start)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    assert p95 < 1.0, f"p95 {p95:.2f}s"


@req("NFR1", "NFR2")
def test_nfr1_nfr2_batch_over_a_large_period_finishes_quickly(indexed, db):
    """A 300-question period is clustered, ranked and reported in well under a minute."""
    big = [{"pool": COVERED, "counts": [0, 0, 110]}, {"pool": TEAM, "counts": [0, 0, 100]},
           {"pool": EMERGING, "counts": [0, 0, 90]}]
    replay(db, indexed.default_workspace, plan=big)
    start = time.perf_counter()
    indexed.post(f"/api/analytics/run?period={PERIODS[-1]}")
    elapsed = time.perf_counter() - start
    assert indexed.get("/api/reports/latest").json()["queryCount"] == 300
    assert elapsed < 60, f"batch took {elapsed:.1f}s"


# ---- NFR2 scalability --------------------------------------------------------------------

@req("NFR2")
def test_nfr2_widening_the_window_needs_no_code_or_schema_change(with_traffic, db):
    """A fourth month of traffic is picked up by re-running the same batch; history stays linked."""
    replay(db, with_traffic.default_workspace, plan=DEFAULT_PLAN, periods=["2026-06", "2026-07", "2026-09"])
    with_traffic.post("/api/analytics/run")
    periods = with_traffic.get("/api/periods").json()
    assert periods[0] == "2026-09" and len(periods) == 4
    assert len(with_traffic.get("/api/reports").json()) == 4


# ---- NFR3 reliability ---------------------------------------------------------------------

@req("NFR3")
def test_nfr3_model_outage_never_stops_logging_or_analytics(indexed, db, fake_llm):
    """With the model down: chat answers from passages, turns are logged, the batch still reports."""
    fake_llm.mode = "down"
    reply = indexed.ask("refund a payment", session_id="sess_nfr3")
    assert reply["citations"] and "unavailable" in reply["text"]
    replay(db, indexed.default_workspace)
    indexed.post("/api/analytics/run")
    assert indexed.get("/api/reports/latest").status_code == 200
    assert db.query(Message).filter(Message.organization_id == indexed.org).count() > 50


@req("NFR3")
def test_nfr3_reasoning_model_empty_replies_are_handled_like_an_outage(indexed, db, fake_llm):
    """An empty model reply (the reasoning-model failure) degrades exactly like an outage."""
    fake_llm.mode = "empty"
    assert "unavailable" in indexed.ask("refund a payment")["text"]
    replay(db, indexed.default_workspace)
    indexed.post("/api/analytics/run")
    assert indexed.get("/api/reports/latest").json()["recommendations"]


# ---- NFR4 accuracy -------------------------------------------------------------------------

@req("NFR4")
def test_nfr4_harness_flags_faithfulness_below_the_target(indexed, fake_llm, tmp_path, monkeypatch, caplog):
    """run_evaluation warns when faithfulness is under 0.80 (real scores: run the live suite)."""
    import json
    import runpy
    import sys

    fake_llm.judge_score = "0.6"
    qs = tmp_path / "set.json"
    qs.write_text(json.dumps([{"question": "refund a payment"}, {"question": "invite a member"}]))
    monkeypatch.setattr(sys, "argv", ["run_evaluation.py", "--organization-id", indexed.org, "--set", str(qs)])
    with caplog.at_level("WARNING"):
        runpy.run_path(str(BACKEND / "scripts" / "run_evaluation.py"), run_name="__main__")
    assert "below the 0.80 target" in caplog.text


# ---- NFR5 explainability --------------------------------------------------------------------

@req("NFR5")
def test_nfr5_everything_in_the_archive_traces_back_to_its_evidence(with_traffic, db):
    """Every retrieved chunk resolves to a source; every topic to its questions; every recommendation to its topic."""
    org = with_traffic.org
    for msg in db.query(Message).filter(Message.organization_id == org, Message.role == "assistant"):
        for chunk_id in msg.retrieved_chunk_ids or []:
            chunk = db.get(Chunk, chunk_id)
            assert chunk is not None and db.get(Source, chunk.source_id).organization_id == org
    for cluster in db.query(TopicCluster).filter(TopicCluster.organization_id == org):
        members = db.query(ClusterMember).filter(ClusterMember.cluster_id == cluster.id).all()
        assert len(members) == cluster.query_count
        assert all(db.get(Message, m.message_id).period == cluster.period for m in members)
    for rec in db.query(Recommendation).filter(Recommendation.organization_id == org):
        cluster = db.get(TopicCluster, rec.cluster_id)
        assert cluster is not None and cluster.name == rec.cluster_name and cluster.query_count == rec.volume


# ---- NFR6 security and privacy --------------------------------------------------------------

@req("NFR6")
def test_nfr6_conversation_records_hold_no_personal_identity_fields():
    """Conversations and messages are keyed by an opaque session id, with no identity columns."""
    from app.models import Conversation

    identity = re.compile(r"email|phone|name|ip_?addr|user_?agent|address", re.I)
    for model in (Conversation, Message):
        columns = [c.name for c in model.__table__.columns]
        assert not [c for c in columns if identity.search(c)], columns


@req("NFR6")
def test_nfr6_credentials_stay_out_of_source_control():
    """.env is git-ignored, only config.py reads the environment, and no key is committed."""
    ignored = (BACKEND / ".gitignore").read_text() + (PROJECT / ".gitignore").read_text()
    assert ".env" in ignored
    for path in APP.rglob("*.py"):
        if path.name == "config.py":
            continue
        text = path.read_text()
        assert not re.search(r"os\.getenv|os\.environ\.get|os\.environ\[", text), f"{path} reads the environment"
    key = re.compile(r"gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}")
    skip = {"node_modules", ".venv", "venv", "dist", ".git", "test-reports", "data"}
    for path in PROJECT.rglob("*"):
        if path.is_file() and not skip & set(path.parts) and path.name != ".env" and path.suffix not in (".db", ".zip", ".png", ".jpg", ".pdf"):
            try:
                assert not key.search(path.read_text(errors="ignore")), f"API key committed in {path}"
            except OSError:
                continue


@req("NFR6")
@pytest.mark.xfail(strict=True, reason="Known gap: no PII redaction step before analytics")
def test_nfr6_personal_details_are_redacted_before_analytics(indexed, db):
    """An email address in a question does not reach the analytics output."""
    plan = [{"pool": ["my email is jane.doe@example.com and my invoice will not send"], "counts": [0, 0, 8]}]
    replay(db, indexed.default_workspace, plan=DEFAULT_PLAN + plan)
    indexed.post("/api/analytics/run")
    report = indexed.get("/api/reports/latest").text
    insights = indexed.get("/api/insights").text
    assert "jane.doe@example.com" not in report + insights


# ---- NFR7 usability -------------------------------------------------------------------------

@req("NFR7")
def test_nfr7_report_is_free_of_technical_terms(with_traffic):
    """Summary and recommendation text avoid model and retrieval vocabulary."""
    report = with_traffic.get("/api/reports/latest").json()
    texts = [report["summary"]] + [
        f"{r['headline']} {r['body']} {r['expectedEffect']}" for r in report["recommendations"]
    ]
    for text in texts:
        assert not [w for w in JARGON if w in text.lower()], text


@req("NFR7")
@pytest.mark.xfail(strict=True, reason="Defect found in testing: when the model is unavailable, the templated "
                                       "fallback text says 'retrieval confidence' (recommend.py defaults and summary)")
def test_nfr7_fallback_report_is_also_free_of_technical_terms(indexed, db, fake_llm):
    """The report written without the model is readable by a non-technical owner too."""
    replay(db, indexed.default_workspace)
    fake_llm.mode = "down"
    indexed.post("/api/analytics/run")
    report = indexed.get("/api/reports/latest").json()
    text = report["summary"] + " ".join(r["body"] for r in report["recommendations"])
    assert not [w for w in JARGON if w in text.lower()], text


# ---- NFR8 maintainability ---------------------------------------------------------------------

@req("NFR8")
def test_nfr8_no_orchestration_framework_and_modules_stay_in_their_lanes():
    """No LangChain-style framework; ingestion, retrieval and analytics do not import each other."""
    requirements = (BACKEND / "requirements.txt").read_text().lower()
    for framework in ("langchain", "llama-index", "llama_index", "haystack", "ragas"):
        assert framework not in requirements
    rules = {"ingest": ("app.rag", "app.analytics", "app.routers"),
             "rag": ("app.ingest", "app.analytics", "app.routers"),
             "analytics": ("app.ingest", "app.rag", "app.routers")}
    for package, forbidden in rules.items():
        for path in (APP / package).glob("*.py"):
            bad = [i for i in _imports(path) if i.startswith(forbidden)]
            assert not bad, f"{path.name} imports {bad}"


# ---- NFR9 portability ----------------------------------------------------------------------

@req("NFR9")
def test_nfr9_container_image_is_defined():
    """A Dockerfile builds the API on a slim Python image and starts uvicorn."""
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert "FROM python:3.11" in dockerfile and "uvicorn" in dockerfile


@req("NFR9")
@pytest.mark.xfail(strict=True, reason="Known gap: no docker-compose.yml; the report specifies Docker Compose")
def test_nfr9_docker_compose_file_exists():
    """The whole system starts with one docker compose command."""
    assert any((PROJECT / n).exists() for n in ("docker-compose.yml", "compose.yaml", "docker-compose.yaml"))


# ---- NFR10 cost ----------------------------------------------------------------------------

@req("NFR10")
def test_nfr10_embedding_and_clustering_run_locally():
    """Only the model client and the crawler make network calls; embeddings are a local model."""
    callers = {p.relative_to(APP).as_posix() for p in APP.rglob("*.py") if "httpx" in _imports(p)}
    assert callers == {"llm.py", "ingest/crawler.py"}
    assert "sentence_transformers" in _imports(APP / "embeddings.py")


@req("NFR10")
def test_nfr10_model_calls_scale_with_topics_not_with_questions(indexed, db, fake_llm):
    """The batch calls the model once per topic, recommendation and summary, never per question."""
    questions = replay(db, indexed.default_workspace)
    fake_llm.calls.clear()
    indexed.post("/api/analytics/run")
    topics = sum(len(indexed.get(f"/api/insights?period={p}").json()) for p in PERIODS)
    recs = sum(len(r["recommendations"]) for r in indexed.get("/api/reports").json())
    assert len(fake_llm.calls) == topics + recs + len(PERIODS)
    assert len(fake_llm.calls) < questions / 2
