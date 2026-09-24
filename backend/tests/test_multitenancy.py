"""Tenant isolation tests: organisations, and workspaces inside them.

    python -m unittest tests/test_multitenancy.py

Covers:
 1. /api/health and /api/research stay public.
 2. Every tenant route rejects a missing, blank or malformed X-Organization-Id with 400.
 3. A new organisation gets its own default workspace; workspace lists are per organisation.
 4. Another organisation's workspace id is a 404 (no workspace hopping), for reads,
    PATCH and DELETE; an organisation cannot delete its own default workspace.
 5. Sources are listed per organisation; cross-organisation reindex, stop and delete are 404.
 6. Vector search filters on workspace and organisation inside Chroma.
 7. Chat retrieves and cites only the caller's chunks, and stamps its rows.
 8. Insights and overview are scoped; cross-organisation insight detail is 404.
 9. Reports and evaluation runs are scoped.
10. The analytics batch reads only its workspace and stamps every row it writes.
11. The migration upgrades a pre-tenancy database in place, and moves rows of other
    organisations out of "ws_default" on a database from the organisation-only branch.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import numpy as np

_test_dir = tempfile.mkdtemp(prefix="kp_test_multitenancy_")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"
os.environ["CHROMA_PATH"] = f"{_test_dir}/chroma"
os.environ["HDBSCAN_MIN_CLUSTER_SIZE"] = "2"
os.environ["UMAP_NEIGHBOURS"] = "2"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
import app.config as config_module  # noqa: E402

config_module.settings = get_settings()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import embeddings, llm, vector_store  # noqa: E402
from app.analytics import batch  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.migrate import upgrade  # noqa: E402
from app.models import (  # noqa: E402
    DEFAULT_WORKSPACE_ID,
    ClusterMember,
    Conversation,
    EvaluationRun,
    Message,
    Recommendation,
    Report,
    Source,
    TopicCluster,
    Workspace,
)
from app.tenant import default_workspace_id, ensure_default_workspace  # noqa: E402

ORG_A = "org_test_alpha"
ORG_B = "org_test_beta"
A = {"X-Organization-Id": ORG_A}
B = {"X-Organization-Id": ORG_B}


def fake_embed(texts: list[str], batch_size: int = 32) -> np.ndarray:
    dim = 32
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for row, t in enumerate(texts):
        for word in t.lower().split():
            out[row, sum(ord(c) for c in word) % dim] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


def fake_complete(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900) -> str:
    return "Test answer based on retrieved documents."


def fake_complete_json(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900):
    return {"headline": "Test", "body": "Test body", "expected_effect": "Test effect", "faq_answer": "FAQ"}


class MultiTenancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        embeddings.embed = fake_embed
        embeddings.embed_one = lambda t: fake_embed([t])[0]
        llm.complete = fake_complete
        llm.complete_json = fake_complete_json

        upgrade()
        db = SessionLocal()
        cls.ws_a = ensure_default_workspace(db, ORG_A).id
        cls.ws_b = ensure_default_workspace(db, ORG_B).id
        db.close()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_test_dir, ignore_errors=True)

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _source(self, sid: str, org: str, ws: str, label: str) -> Source:
        src = Source(id=sid, organization_id=org, workspace_id=ws, kind="text",
                     label=label, location=f"/tmp/{sid}.txt", status="ready")
        self.db.add(src)
        self.db.commit()
        return src

    # ---- 1-2. header -----------------------------------------------------

    def test_01_public_routes(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertIn(self.client.get("/api/research/latest").status_code, (200, 404))

    def test_02_header_required(self):
        routes = [
            ("GET", "/api/workspaces"), ("POST", "/api/workspaces"),
            ("GET", "/api/sources"), ("POST", "/api/sources"),
            ("POST", "/api/sources/x/stop"), ("GET", "/api/overview"),
            ("GET", "/api/periods"), ("GET", "/api/insights"),
            ("GET", "/api/reports"), ("GET", "/api/reports/latest"),
            ("POST", "/api/chat"), ("POST", "/api/analytics/run"),
            ("GET", "/api/evaluation/latest"),
        ]
        for method, route in routes:
            resp = self.client.request(method, route, json={} if method == "POST" else None)
            self.assertEqual(resp.status_code, 400, f"{method} {route}")
            self.assertIn("X-Organization-Id header is required", resp.json()["detail"])

        resp = self.client.get("/api/sources", headers={"X-Organization-Id": "   "})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.get("/api/sources", headers={"X-Organization-Id": "bad org!@#"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid X-Organization-Id", resp.json()["detail"])

    # ---- 3-4. workspaces ------------------------------------------------

    def test_03_default_workspace_per_organisation(self):
        fresh = {"X-Organization-Id": "org_test_fresh"}
        listed = self.client.get("/api/workspaces", headers=fresh).json()
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0]["isDefault"])
        self.assertEqual(listed[0]["id"], default_workspace_id("org_test_fresh"))

        created = self.client.post("/api/workspaces", headers=A, json={"name": "Alpha second"}).json()
        ids_a = {w["id"] for w in self.client.get("/api/workspaces", headers=A).json()}
        ids_b = {w["id"] for w in self.client.get("/api/workspaces", headers=B).json()}
        self.assertIn(created["id"], ids_a)
        self.assertNotIn(created["id"], ids_b)
        self.assertNotIn(DEFAULT_WORKSPACE_ID, ids_a | ids_b)
        self.assertEqual(self.db.get(Workspace, created["id"]).organization_id, ORG_A)

    def test_04_no_workspace_hopping(self):
        hop = {**B, "X-Workspace-Id": self.ws_a}
        self.assertEqual(self.client.get("/api/sources", headers=hop).status_code, 404)
        self.assertEqual(self.client.get("/api/overview", headers=hop).status_code, 404)
        self.assertEqual(
            self.client.patch(f"/api/workspaces/{self.ws_a}", headers=B, json={"name": "x"}).status_code, 404
        )
        self.assertEqual(self.client.delete(f"/api/workspaces/{self.ws_a}", headers=B).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/workspaces/{self.ws_a}", headers=A).status_code, 400)
        self.assertIsNotNone(self.db.get(Workspace, self.ws_a))

    # ---- 5. sources -----------------------------------------------------

    def test_05_sources(self):
        self._source("src_alpha_01", ORG_A, self.ws_a, "Alpha Docs")
        self._source("src_beta_01", ORG_B, self.ws_b, "Beta Docs")

        labels_a = [s["label"] for s in self.client.get("/api/sources", headers=A).json()]
        labels_b = [s["label"] for s in self.client.get("/api/sources", headers=B).json()]
        self.assertIn("Alpha Docs", labels_a)
        self.assertNotIn("Beta Docs", labels_a)
        self.assertIn("Beta Docs", labels_b)
        self.assertNotIn("Alpha Docs", labels_b)

        for method, path in [("POST", "/reindex"), ("POST", "/stop"), ("DELETE", "")]:
            resp = self.client.request(method, f"/api/sources/src_alpha_01{path}", headers=B)
            self.assertEqual(resp.status_code, 404, f"{method} {path}")
        self.assertIsNotNone(self.db.get(Source, "src_alpha_01"))

        created = self.client.post(
            "/api/sources", headers=A, json={"kind": "website", "location": "http://127.0.0.1:9/none"}
        )
        self.assertEqual(created.status_code, 201)
        row = self.db.get(Source, created.json()["id"])
        self.assertEqual((row.organization_id, row.workspace_id), (ORG_A, self.ws_a))

    # ---- 6. vector store ------------------------------------------------

    def test_06_vector_store(self):
        vec = fake_embed(["billing payment invoice"])[0]
        for cid, org, ws in [("chk_vec_a", ORG_A, self.ws_a), ("chk_vec_b", ORG_B, self.ws_b)]:
            vector_store.upsert(
                [cid], [vec],
                [{"source_id": f"src_vec_{org}", "workspace_id": ws, "organization_id": org}],
                [f"{org} billing"],
            )
        hits_a = vector_store.search(vec, 10, workspace_id=self.ws_a, organization_id=ORG_A)
        self.assertEqual([h["chunk_id"] for h in hits_a], ["chk_vec_a"])
        # Right workspace, wrong organisation: nothing.
        self.assertEqual(vector_store.search(vec, 10, workspace_id=self.ws_a, organization_id=ORG_B), [])

        vector_store.delete_source(f"src_vec_{ORG_A}")
        self.assertEqual(vector_store.search(vec, 10, workspace_id=self.ws_a, organization_id=ORG_A), [])
        self.assertEqual(len(vector_store.search(vec, 10, workspace_id=self.ws_b, organization_id=ORG_B)), 1)

    # ---- 7. chat ----------------------------------------------------------

    def test_07_chat(self):
        vec = fake_embed(["alpha private secret info"])[0]
        vector_store.upsert(
            ["chk_chat_a"], [vec],
            [{"source_id": "src_alpha_01", "source_label": "Alpha Docs", "heading_path": "Secret",
              "workspace_id": self.ws_a, "organization_id": ORG_A}],
            ["Alpha confidential policy details"],
        )
        body = {"question": "alpha private secret info", "session_id": "sess_shared"}
        cited_b = [c["chunkId"] for c in self.client.post("/api/chat", headers=B, json=body).json()["citations"]]
        cited_a = [c["chunkId"] for c in self.client.post("/api/chat", headers=A, json=body).json()["citations"]]
        self.assertNotIn("chk_chat_a", cited_b)
        self.assertIn("chk_chat_a", cited_a)

        # Same session id in two organisations: two conversations, each stamped.
        convs = self.db.query(Conversation).filter(Conversation.session_id == "sess_shared").all()
        self.assertEqual({(c.organization_id, c.workspace_id) for c in convs},
                         {(ORG_A, self.ws_a), (ORG_B, self.ws_b)})
        for c in convs:
            for m in self.db.query(Message).filter(Message.conversation_id == c.id):
                self.assertEqual(m.organization_id, c.organization_id)

    # ---- 8-9. insights, reports, evaluation --------------------------------

    def test_08_insights(self):
        common = dict(period="2026-08", rank=1, keywords=["k"], query_count=10, previous_query_count=5,
                      growth=1.0, mean_confidence=0.8, severity=0.5, priority=0.8, trend="recurring")
        self.db.add_all([
            TopicCluster(id="ins_alpha_01", organization_id=ORG_A, workspace_id=self.ws_a, name="Alpha Topic", **common),
            TopicCluster(id="ins_beta_01", organization_id=ORG_B, workspace_id=self.ws_b, name="Beta Topic", **common),
        ])
        self.db.commit()
        names = [i["name"] for i in self.client.get("/api/insights", headers=A).json()]
        self.assertEqual(names, ["Alpha Topic"])
        self.assertEqual(self.client.get("/api/insights/ins_beta_01", headers=A).status_code, 404)
        self.assertEqual(self.client.get("/api/insights/ins_alpha_01", headers=A).status_code, 200)
        self.assertEqual(self.client.get("/api/overview", headers=A).json()["topicCount"], 1)
        self.assertEqual(self.client.get("/api/periods", headers=B).json(), ["2026-08"])

    def test_09_reports_and_evaluation(self):
        self.db.add_all([
            Report(id="rep_alpha_01", organization_id=ORG_A, workspace_id=self.ws_a, period="2026-08",
                   summary="Alpha"),
            Report(id="rep_beta_01", organization_id=ORG_B, workspace_id=self.ws_b, period="2026-09",
                   summary="Beta"),
            EvaluationRun(id="eval_alpha_01", organization_id=ORG_A, workspace_id=self.ws_a, faithfulness=0.88),
            EvaluationRun(id="eval_beta_01", organization_id=ORG_B, workspace_id=self.ws_b, faithfulness=0.75),
        ])
        self.db.commit()
        self.assertEqual(self.client.get("/api/reports/latest", headers=A).json()["id"], "rep_alpha_01")
        self.assertEqual(self.client.get("/api/reports/latest", headers=B).json()["id"], "rep_beta_01")
        self.assertEqual([r["id"] for r in self.client.get("/api/reports", headers=A).json()], ["rep_alpha_01"])
        self.assertEqual(self.client.get("/api/evaluation/latest", headers=A).json()["id"], "eval_alpha_01")

    # ---- 10. analytics ----------------------------------------------------

    def test_10_analytics_batch(self):
        period = "2026-10"
        for org, ws, tag in [(ORG_A, self.ws_a, "a"), (ORG_B, self.ws_b, "b")]:
            self.db.add(Conversation(id=f"conv_{tag}_batch", organization_id=org, workspace_id=ws,
                                     session_id=f"s_{tag}_batch"))
            self.db.flush()
            self.db.add_all([
                Message(id=f"msg_{tag}_{i}", organization_id=org, workspace_id=ws,
                        conversation_id=f"conv_{tag}_batch", role="customer",
                        text=f"{tag} invoice question {i}", confidence=0.8, period=period)
                for i in range(6)
            ])
        self.db.commit()

        from app.analytics import clustering

        original = clustering.cluster_queries
        clustering.cluster_queries = lambda texts, vectors, confidences: [
            clustering.Cluster(label=0, indices=list(range(len(texts))), centroid=np.zeros(32, dtype=np.float32),
                               keywords=["invoice"], name="Invoices", mean_confidence=0.8, severity=0.5)
        ]
        try:
            report = batch.run_batch(self.db, period, self.ws_a)
        finally:
            clustering.cluster_queries = original

        self.assertEqual((report.organization_id, report.workspace_id, report.query_count), (ORG_A, self.ws_a, 6))
        clusters = self.db.query(TopicCluster).filter(TopicCluster.period == period).all()
        self.assertEqual({c.organization_id for c in clusters}, {ORG_A})
        members = self.db.query(ClusterMember).filter(ClusterMember.cluster_id.in_([c.id for c in clusters])).all()
        self.assertEqual(len(members), 6)
        self.assertTrue(all(m.organization_id == ORG_A and m.message_id.startswith("msg_a_") for m in members))
        recs = self.db.query(Recommendation).filter(Recommendation.report_id == report.id).all()
        self.assertTrue(recs and all(r.organization_id == ORG_A for r in recs))
        self.assertIsNone(self.db.query(Report).filter(Report.period == period, Report.organization_id == ORG_B).first())


class MigrationTests(unittest.TestCase):
    """Runs upgrade() against hand-built legacy schemas in a separate database."""

    def _upgrade(self, url: str) -> None:
        import app.db as db_module
        import app.migrate as migrate_module
        import app.tenant  # noqa: F401
        from sqlalchemy.orm import sessionmaker

        legacy = create_engine(url)
        saved = (db_module.engine, db_module.SessionLocal, migrate_module.engine, migrate_module.SessionLocal)
        Session = sessionmaker(bind=legacy, autoflush=False, expire_on_commit=False)
        db_module.engine, db_module.SessionLocal = legacy, Session
        migrate_module.engine, migrate_module.SessionLocal = legacy, Session
        try:
            upgrade()
            upgrade()  # idempotent
        finally:
            db_module.engine, db_module.SessionLocal, migrate_module.engine, migrate_module.SessionLocal = saved
        return legacy

    def test_11a_pre_tenancy_database(self):
        url = f"sqlite:///{_test_dir}/legacy_workspaces.db"
        e = create_engine(url)
        with e.begin() as c:
            c.execute(text("CREATE TABLE workspaces (id VARCHAR(40) PRIMARY KEY, name VARCHAR(120), "
                           "description TEXT, chunk_target_words INT, chunk_overlap_words INT, "
                           "crawl_max_pages INT, created_at DATETIME)"))
            c.execute(text("INSERT INTO workspaces (id, name, description) VALUES ('ws_default','D',''),"
                           "('ws_research','R','')"))
            c.execute(text("CREATE TABLE sources (id VARCHAR(40) PRIMARY KEY, workspace_id VARCHAR(40) NOT NULL, "
                           "kind VARCHAR(16), label VARCHAR(200), location TEXT, status VARCHAR(16), "
                           "page_count INT, chunk_count INT, last_indexed_at DATETIME, content_hash VARCHAR(64), "
                           "error TEXT, created_at DATETIME)"))
            c.execute(text("INSERT INTO sources (id, workspace_id, kind, label, location, status, chunk_count) "
                           "VALUES ('src_1','ws_research','website','x','http://x','ready',3)"))
        legacy = self._upgrade(url)
        with legacy.connect() as c:
            self.assertEqual(c.execute(text("SELECT organization_id FROM sources")).scalar(), "org_default")
            orgs = {r[0] for r in c.execute(text("SELECT organization_id FROM workspaces"))}
            self.assertEqual(orgs, {"org_default"})
            index_names = {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))}
            self.assertIn("ix_sources_org_created_at", index_names)

    def test_11b_organisation_only_database(self):
        """The organisation-only branch: organization_id everywhere, no workspaces."""
        url = f"sqlite:///{_test_dir}/legacy_orgs.db"
        e = create_engine(url)
        with e.begin() as c:
            c.execute(text("CREATE TABLE sources (id VARCHAR(40) PRIMARY KEY, organization_id VARCHAR(64) NOT NULL, "
                           "kind VARCHAR(16), label VARCHAR(200), location TEXT, status VARCHAR(16), "
                           "page_count INT, chunk_count INT, last_indexed_at DATETIME, content_hash VARCHAR(64), "
                           "error TEXT, created_at DATETIME)"))
            c.execute(text("INSERT INTO sources (id, organization_id, kind, label, location, status, chunk_count) "
                           "VALUES ('src_d','org_default','text','d','p','ready',1),"
                           "('src_x','org_x','text','x','p','ready',1)"))
        legacy = self._upgrade(url)
        with legacy.connect() as c:
            rows = dict(c.execute(text("SELECT id, workspace_id FROM sources")).all())
            self.assertEqual(rows["src_d"], DEFAULT_WORKSPACE_ID)
            self.assertEqual(rows["src_x"], default_workspace_id("org_x"))
            owner = c.execute(text("SELECT organization_id FROM workspaces WHERE id = :w"),
                              {"w": default_workspace_id("org_x")}).scalar()
            self.assertEqual(owner, "org_x")


if __name__ == "__main__":
    unittest.main()
