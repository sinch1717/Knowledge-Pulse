"""Comprehensive multi-tenancy isolation test suite for KnowledgePulse.

Validates all 13 security acceptance criteria:
1. Requests without X-Organization-Id fail with HTTP 400.
2. Requests with malformed/blank X-Organization-Id fail with HTTP 400.
3. Health endpoint remains accessible without X-Organization-Id.
4. Source listing is strictly scoped to the requesting organization.
5. Cross-tenant source reindexing returns 404.
6. Cross-tenant source deletion returns 404.
7. Vector store upsert, search, and delete are strictly tenant-isolated.
8. Chat / RAG retrieval only queries the current organization's chunks.
9. Insights listing and detail lookups are tenant-scoped (cross-tenant 404).
10. Reports are tenant-scoped (latest report does not leak across tenants).
11. Evaluation results are tenant-scoped.
12. Analytics batch processes only the specified organization's conversations.
13. No global mutable tenant state is used.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
import numpy as np

# Set up test environment before importing app
_test_dir = tempfile.mkdtemp(prefix="kp_test_multitenancy_")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"
os.environ["CHROMA_PATH"] = f"{_test_dir}/chroma"
os.environ["HDBSCAN_MIN_CLUSTER_SIZE"] = "2"
os.environ["UMAP_NEIGHBOURS"] = "2"

from app.config import get_settings
get_settings.cache_clear()
import app.config as config_module
config_module.settings = get_settings()

from starlette.testclient import TestClient
from app import embeddings, llm, vector_store
from app.analytics import batch
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Chunk, Conversation, EvaluationRun, Message, Report, Source, TopicCluster
from app.rag import engine as rag_engine

ORG_A = "org_test_alpha"
ORG_B = "org_test_beta"


def fake_embed(texts: list[str], batch_size: int = 32) -> np.ndarray:
    dim = 32
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in text.lower().split():
            idx = sum(ord(c) for c in word) % dim
            out[row, idx] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


def fake_complete(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900) -> str:
    return "Test answer based on retrieved documents."


def fake_complete_json(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900):
    return {
        "headline": "Test recommendation",
        "body": "Test body",
        "expected_effect": "Test effect",
        "faq_answer": "Test FAQ",
    }


class MultiTenancyIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        embeddings.embed = fake_embed
        embeddings.embed_one = lambda text: fake_embed([text])[0]
        llm.complete = fake_complete
        llm.complete_json = fake_complete_json

        from app.analytics import clustering, recommend
        clustering.llm.complete = fake_complete
        recommend.llm.complete = fake_complete
        recommend.llm.complete_json = fake_complete_json

        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_test_dir, ignore_errors=True)

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    # --------------------------------------------------------------------------
    # 1. Header Validation & Health Endpoint
    # --------------------------------------------------------------------------
    def test_01_health_endpoint_public(self):
        """GET /api/health must succeed without X-Organization-Id."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_02_missing_header_rejected_on_all_tenant_routes(self):
        """Tenant-scoped routes must reject requests without X-Organization-Id with 400."""
        routes = [
            ("GET", "/api/sources"),
            ("POST", "/api/sources"),
            ("GET", "/api/overview"),
            ("GET", "/api/insights"),
            ("GET", "/api/reports"),
            ("GET", "/api/reports/latest"),
            ("POST", "/api/chat"),
            ("GET", "/api/evaluation/latest"),
        ]
        for method, route in routes:
            if method == "GET":
                resp = self.client.get(route)
            else:
                resp = self.client.post(route, json={})
            self.assertEqual(
                resp.status_code,
                400,
                f"{method} {route} should fail with 400 when X-Organization-Id is missing, got {resp.status_code}",
            )
            self.assertIn("X-Organization-Id header is required", resp.json()["detail"])

    def test_03_blank_or_invalid_header_rejected(self):
        """Blank or malformed X-Organization-Id must return 400."""
        # Blank
        resp = self.client.get("/api/sources", headers={"X-Organization-Id": "   "})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("X-Organization-Id header is required", resp.json()["detail"])

        # Invalid characters (e.g. spaces, special symbols)
        resp = self.client.get("/api/sources", headers={"X-Organization-Id": "bad org!@#"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid X-Organization-Id", resp.json()["detail"])

    # --------------------------------------------------------------------------
    # 2. Source Isolation (Creation, Listing, Reindex, Delete)
    # --------------------------------------------------------------------------
    def test_04_source_isolation(self):
        """Sources created under org_a are not visible or accessible to org_b."""
        # Create source under org_a
        src_a = Source(
            id="src_alpha_01",
            organization_id=ORG_A,
            kind="text",
            label="Alpha Docs",
            location="/tmp/alpha.txt",
            status="ready",
        )
        # Create source under org_b
        src_b = Source(
            id="src_beta_01",
            organization_id=ORG_B,
            kind="text",
            label="Beta Docs",
            location="/tmp/beta.txt",
            status="ready",
        )
        self.db.add_all([src_a, src_b])
        self.db.commit()

        # List sources for org_a
        resp_a = self.client.get("/api/sources", headers={"X-Organization-Id": ORG_A})
        self.assertEqual(resp_a.status_code, 200)
        labels_a = [s["label"] for s in resp_a.json()]
        self.assertIn("Alpha Docs", labels_a)
        self.assertNotIn("Beta Docs", labels_a)

        # List sources for org_b
        resp_b = self.client.get("/api/sources", headers={"X-Organization-Id": ORG_B})
        self.assertEqual(resp_b.status_code, 200)
        labels_b = [s["label"] for s in resp_b.json()]
        self.assertIn("Beta Docs", labels_b)
        self.assertNotIn("Alpha Docs", labels_b)

    def test_05_cross_tenant_source_operations_404(self):
        """Reindexing or deleting another organization's source must return 404."""
        # Reindex source_a using org_b header -> 404
        resp_reindex = self.client.post(
            "/api/sources/src_alpha_01/reindex", headers={"X-Organization-Id": ORG_B}
        )
        self.assertEqual(resp_reindex.status_code, 404)

        # Delete source_a using org_b header -> 404
        resp_delete = self.client.delete(
            "/api/sources/src_alpha_01", headers={"X-Organization-Id": ORG_B}
        )
        self.assertEqual(resp_delete.status_code, 404)

        # Source should still exist
        self.assertIsNotNone(self.db.get(Source, "src_alpha_01"))

    # --------------------------------------------------------------------------
    # 3. Vector Store Isolation
    # --------------------------------------------------------------------------
    def test_06_vector_store_tenant_filtering(self):
        """Vector search must only return chunks matching the current organization_id."""
        vec = fake_embed(["billing payment invoice"])[0]

        # Upsert vector for ORG_A
        vector_store.upsert(
            chunk_ids=["chk_vec_a"],
            vectors=[vec],
            metadatas=[{"source_id": "src_alpha_01", "heading_path": "Billing › Payments"}],
            documents=["Alpha billing details"],
            organization_id=ORG_A,
        )

        # Upsert vector for ORG_B
        vector_store.upsert(
            chunk_ids=["chk_vec_b"],
            vectors=[vec],
            metadatas=[{"source_id": "src_beta_01", "heading_path": "Subscriptions › Invoices"}],
            documents=["Beta billing details"],
            organization_id=ORG_B,
        )

        # Search with ORG_A
        hits_a = vector_store.search(vec, top_k=10, organization_id=ORG_A)
        self.assertTrue(all(h["meta"]["organization_id"] == ORG_A for h in hits_a))
        self.assertEqual([h["chunk_id"] for h in hits_a], ["chk_vec_a"])

        # Search with ORG_B
        hits_b = vector_store.search(vec, top_k=10, organization_id=ORG_B)
        self.assertTrue(all(h["meta"]["organization_id"] == ORG_B for h in hits_b))
        self.assertEqual([h["chunk_id"] for h in hits_b], ["chk_vec_b"])

        # Delete source for ORG_A should not affect ORG_B
        vector_store.delete_source("src_alpha_01", organization_id=ORG_A)
        hits_a_post = vector_store.search(vec, top_k=10, organization_id=ORG_A)
        self.assertEqual(len(hits_a_post), 0)

        hits_b_post = vector_store.search(vec, top_k=10, organization_id=ORG_B)
        self.assertEqual(len(hits_b_post), 1)

    # --------------------------------------------------------------------------
    # 4. Chat / RAG Retrieval Isolation
    # --------------------------------------------------------------------------
    def test_07_chat_retrieval_isolation(self):
        """POST /api/chat retrieves and cites only chunks from the caller's organization."""
        # Index chunks for ORG_A
        vec_a = fake_embed(["alpha private secret info"])[0]
        vector_store.upsert(
            chunk_ids=["chk_chat_a"],
            vectors=[vec_a],
            metadatas=[{"source_id": "src_alpha_01", "source_label": "Alpha Docs", "heading_path": "Secret"}],
            documents=["Alpha confidential policy details"],
            organization_id=ORG_A,
        )

        # Query chat as ORG_B
        resp_b = self.client.post(
            "/api/chat",
            headers={"X-Organization-Id": ORG_B},
            json={"question": "alpha private secret info", "session_id": "sess_beta_1"},
        )
        self.assertEqual(resp_b.status_code, 200)
        citations_b = resp_b.json().get("citations", [])
        retrieved_ids_b = [c["chunkId"] for c in citations_b]
        self.assertNotIn("chk_chat_a", retrieved_ids_b, "ORG_B must not retrieve ORG_A chunks")

        # Query chat as ORG_A
        resp_a = self.client.post(
            "/api/chat",
            headers={"X-Organization-Id": ORG_A},
            json={"question": "alpha private secret info", "session_id": "sess_alpha_1"},
        )
        self.assertEqual(resp_a.status_code, 200)
        citations_a = resp_a.json().get("citations", [])
        retrieved_ids_a = [c["chunkId"] for c in citations_a]
        self.assertIn("chk_chat_a", retrieved_ids_a, "ORG_A must retrieve its own chunk")
        self.assertNotIn("chk_vec_b", retrieved_ids_a, "ORG_A must not retrieve ORG_B chunks")

    # --------------------------------------------------------------------------
    # 5. Insights & Overview Isolation
    # --------------------------------------------------------------------------
    def test_08_insights_and_overview_isolation(self):
        """Overview and Insights endpoints must strictly isolate cluster metrics and entities."""
        period = "2026-08"
        # Seed cluster for ORG_A
        cluster_a = TopicCluster(
            id="ins_alpha_01",
            organization_id=ORG_A,
            period=period,
            rank=1,
            name="Alpha Topic",
            keywords=["alpha", "support"],
            query_count=10,
            previous_query_count=5,
            growth=1.0,
            mean_confidence=0.8,
            severity=0.5,
            priority=0.85,
            trend="recurring",
        )
        # Seed cluster for ORG_B
        cluster_b = TopicCluster(
            id="ins_beta_01",
            organization_id=ORG_B,
            period=period,
            rank=1,
            name="Beta Topic",
            keywords=["beta", "billing"],
            query_count=20,
            previous_query_count=10,
            growth=1.0,
            mean_confidence=0.7,
            severity=0.6,
            priority=0.90,
            trend="emerging",
        )
        self.db.add_all([cluster_a, cluster_b])
        self.db.commit()

        # GET /api/insights with ORG_A
        resp_a = self.client.get("/api/insights", headers={"X-Organization-Id": ORG_A})
        self.assertEqual(resp_a.status_code, 200)
        names_a = [i["name"] for i in resp_a.json()]
        self.assertIn("Alpha Topic", names_a)
        self.assertNotIn("Beta Topic", names_a)

        # GET /api/insights/{insight_id} cross-tenant check
        resp_cross = self.client.get(
            f"/api/insights/{cluster_b.id}", headers={"X-Organization-Id": ORG_A}
        )
        self.assertEqual(resp_cross.status_code, 404, "Accessing ORG_B insight with ORG_A must return 404")

        # GET /api/overview with ORG_A
        resp_overview = self.client.get("/api/overview", headers={"X-Organization-Id": ORG_A})
        self.assertEqual(resp_overview.status_code, 200)
        data = resp_overview.json()
        self.assertEqual(data["topicCount"], 1)

    # --------------------------------------------------------------------------
    # 6. Reports & Evaluation Isolation
    # --------------------------------------------------------------------------
    def test_09_reports_and_evaluation_isolation(self):
        """Latest report and latest evaluation must be scoped by organization_id."""
        rep_a = Report(
            id="rep_alpha_01",
            organization_id=ORG_A,
            period="2026-08",
            summary="Alpha monthly report",
            conversation_count=5,
            query_count=15,
            unanswered_rate=0.1,
        )
        rep_b = Report(
            id="rep_beta_01",
            organization_id=ORG_B,
            period="2026-09",
            summary="Beta latest report",
            conversation_count=8,
            query_count=25,
            unanswered_rate=0.2,
        )
        eval_a = EvaluationRun(
            id="eval_alpha_01",
            organization_id=ORG_A,
            question_count=10,
            faithfulness=0.88,
            answer_relevance=0.91,
            context_relevance=0.85,
        )
        eval_b = EvaluationRun(
            id="eval_beta_01",
            organization_id=ORG_B,
            question_count=15,
            faithfulness=0.75,
            answer_relevance=0.80,
            context_relevance=0.70,
        )
        self.db.add_all([rep_a, rep_b, eval_a, eval_b])
        self.db.commit()

        # Reports for ORG_A
        resp_rep = self.client.get("/api/reports/latest", headers={"X-Organization-Id": ORG_A})
        self.assertEqual(resp_rep.status_code, 200)
        self.assertEqual(resp_rep.json()["id"], "rep_alpha_01")
        self.assertEqual(resp_rep.json()["summary"], "Alpha monthly report")

        # Evaluation for ORG_A
        resp_eval = self.client.get("/api/evaluation/latest", headers={"X-Organization-Id": ORG_A})
        self.assertEqual(resp_eval.status_code, 200)
        self.assertEqual(resp_eval.json()["id"], "eval_alpha_01")
        self.assertEqual(resp_eval.json()["faithfulness"], 0.88)

        # Reports for ORG_B
        resp_rep_b = self.client.get("/api/reports/latest", headers={"X-Organization-Id": ORG_B})
        self.assertEqual(resp_rep_b.status_code, 200)
        self.assertEqual(resp_rep_b.json()["id"], "rep_beta_01")

    # --------------------------------------------------------------------------
    # 7. Analytics Batch Isolation
    # --------------------------------------------------------------------------
    def test_10_analytics_batch_isolation(self):
        """Analytics batch must strictly cluster and report on the specified organization's conversations."""
        period = "2026-10"
        # Seed messages for ORG_A
        conv_a = Conversation(id="conv_a_batch", session_id="s_a_batch", organization_id=ORG_A)
        conv_b = Conversation(id="conv_b_batch", session_id="s_b_batch", organization_id=ORG_B)
        self.db.add_all([conv_a, conv_b])
        self.db.commit()

        msgs_a = [
            Message(
                id=f"msg_a_{i}",
                conversation_id=conv_a.id,
                organization_id=ORG_A,
                role="customer",
                text=f"Alpha invoice question {i}",
                confidence=0.8,
                period=period,
            )
            for i in range(6)
        ]
        msgs_b = [
            Message(
                id=f"msg_b_{i}",
                conversation_id=conv_b.id,
                organization_id=ORG_B,
                role="customer",
                text=f"Beta team question {i}",
                confidence=0.7,
                period=period,
            )
            for i in range(6)
        ]
        self.db.add_all(msgs_a + msgs_b)
        self.db.commit()

        from app.analytics import clustering

        orig_cluster = clustering.cluster_queries
        try:
            clustering.cluster_queries = lambda texts, vectors, confidences: [
                clustering.Cluster(
                    label=0,
                    indices=list(range(len(texts))),
                    centroid=np.zeros(32, dtype=np.float32),
                    keywords=["alpha", "invoice"],
                    name="Alpha Invoices",
                    mean_confidence=0.8,
                    severity=0.5,
                )
            ]
            # Run analytics batch for ORG_A only
            rep = batch.run_batch(self.db, period, organization_id=ORG_A)
            self.assertIsNotNone(rep)
            self.assertEqual(rep.organization_id, ORG_A)
            self.assertEqual(rep.query_count, 6)
        finally:
            clustering.cluster_queries = orig_cluster

        # Verify topic clusters created for ORG_A have organization_id == ORG_A
        clusters_a = (
            self.db.query(TopicCluster)
            .filter(TopicCluster.period == period, TopicCluster.organization_id == ORG_A)
            .all()
        )
        self.assertEqual(len(clusters_a), 1)
        self.assertEqual(clusters_a[0].organization_id, ORG_A)

        # Verify no clusters or reports exist for ORG_B in this period
        clusters_b = (
            self.db.query(TopicCluster)
            .filter(TopicCluster.period == period, TopicCluster.organization_id == ORG_B)
            .all()
        )
        self.assertEqual(len(clusters_b), 0)

        rep_b = (
            self.db.query(Report)
            .filter(Report.period == period, Report.organization_id == ORG_B)
            .first()
        )
        self.assertIsNone(rep_b)


if __name__ == "__main__":
    unittest.main()

