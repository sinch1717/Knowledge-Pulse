"""Acceptance tests: one or more per functional requirement in section 6.3 of the report.

Each test states its acceptance criterion in the docstring and is tagged with the
requirement id, which is how test-reports/traceability.md is built. Known gaps
are marked xfail(strict=True): they report as PARTIAL now, and the moment the
feature is built they start passing, which fails the run until the marker is
removed, so the matrix can never quietly go stale.
"""

from __future__ import annotations

import pytest
from support import PERIODS

from app.analytics import recommend, trends
from app.config import settings
from app.models import Chunk, Message, Recommendation, TopicCluster

req = pytest.mark.req


# ---- ingestion ---------------------------------------------------------------------

@req("FR1")
def test_fr1_website_and_documents_are_registered_as_sources(tenant, site, tmp_path):
    """A website URL and uploaded PDF/DOCX/TXT files each appear in the source registry."""
    tenant.add_website(f"{site}/docs/")
    (tmp_path / "faq.txt").write_text("Opening hours. Support is open nine to five on weekdays.")
    with (tmp_path / "faq.txt").open("rb") as fh:
        tenant.post("/api/sources/upload", files={"file": ("faq.txt", fh)})
    kinds = {s["kind"] for s in tenant.get("/api/sources").json()}
    assert kinds == {"website", "text"}


@req("FR1")
def test_fr1_invalid_sources_are_refused(tenant):
    """A website without a full URL, or an unsupported file, is refused with a reason."""
    bad_url = tenant.post("/api/sources", json={"kind": "website", "location": "docs.example.com"})
    assert bad_url.status_code == 400 and "http" in bad_url.json()["detail"]
    assert tenant.post("/api/sources/upload", files={"file": ("x.pptx", b"x")}).status_code == 400


@req("FR2")
def test_fr2_crawl_covers_internal_links_and_drops_boilerplate(indexed, db):
    """All linked docs pages are crawled; navigation, header and footer text is not indexed."""
    assert indexed.site_source["pageCount"] >= 7
    text = " ".join(c.text for c in db.query(Chunk).filter(Chunk.source_id == indexed.site_source["id"]))
    for page_fact in ("invite a team member", "Partial refunds", "CSV file", "Press N"):
        assert page_fact in text
    for boilerplate in ("Copyright Kestrel", "Newsletter signup", "Pricing", "Docs home"):
        assert boilerplate not in text


@req("FR3")
def test_fr3_chunks_follow_headings_with_overlap_and_keep_their_path(indexed, db):
    """Chunks split at headings, carry their heading path, and long sections overlap."""
    chunks = db.query(Chunk).filter(Chunk.source_id == indexed.site_source["id"]).all()
    assert all(c.heading_path for c in chunks)
    long_section = [c.text.split() for c in chunks if c.heading_path == "Account settings › Invoice formatting settings"]
    assert len(long_section) >= 2
    overlap = settings.chunk_overlap_words
    assert long_section[0][-overlap:] == long_section[1][:overlap]


@req("FR4")
def test_fr4_every_chunk_is_embedded_with_its_source_metadata(indexed, db):
    """Each chunk row has a vector in the store, tagged with its source and heading."""
    from app import vector_store

    chunks = db.query(Chunk).filter(Chunk.source_id == indexed.site_source["id"]).all()
    stored = vector_store._get_collection().get(ids=[c.id for c in chunks], include=["metadatas", "embeddings"])
    assert len(stored["ids"]) == len(chunks)
    for meta, vector in zip(stored["metadatas"], stored["embeddings"]):
        assert meta["source_id"] == indexed.site_source["id"] and meta["heading_path"]
        assert len(vector) == 384


@req("FR5")
def test_fr5_reindex_refreshes_content_and_hash(indexed, site, tmp_path):
    """Reindexing re-reads the source and records a fresh content hash and timestamp."""
    before = indexed.site_source
    after = indexed.post(f"/api/sources/{before['id']}/reindex").json()
    after = indexed.source(after["id"])
    assert after["status"] == "ready"
    assert after["contentHash"] == before["contentHash"]  # same content, same hash
    assert after["lastIndexedAt"] >= before["lastIndexedAt"]


@req("FR5")
@pytest.mark.xfail(strict=True, reason="Known gap: no automatic change detection or scheduled re-index; "
                                       "reindex is manual (Sources page or POST /reindex)")
def test_fr5_changed_content_is_reindexed_automatically(indexed):
    """Without anyone pressing Reindex, a changed site is picked up on a schedule."""
    from app import main

    assert hasattr(main, "scheduler")


# ---- chat --------------------------------------------------------------------------

@req("FR6", "FR7")
def test_fr6_fr7_answers_are_grounded_and_cite_their_passages(indexed, fake_llm):
    """The answer is generated from retrieved passages, and each passage is returned with its location."""
    reply = indexed.ask("how do i refund a payment")
    assert reply["text"]
    top = reply["citations"][0]
    assert top["headingPath"] == "Payments › Refunds"
    assert top["sourceLabel"] and top["chunkId"] and "refund" in top["excerpt"].lower()
    assert "Partial refunds are supported" in fake_llm.calls[-1]["user"]


@req("FR8")
def test_fr8_confidence_comes_from_retrieval_similarity_not_the_model(indexed, fake_llm, db):
    """Confidence equals the blended top-k similarity, and is the same whatever the model says."""
    from app.rag.engine import compute_confidence

    reply = indexed.ask("send an invoice by email")
    expected = compute_confidence([c["similarity"] for c in reply["citations"]])
    assert reply["confidence"] == pytest.approx(expected, abs=1e-3)

    fake_llm.mode = "down"  # a completely different answer text...
    again = indexed.ask("send an invoice by email")
    assert again["confidence"] == reply["confidence"]  # ...and the same confidence


@req("FR9")
def test_fr9_turns_are_persisted_with_everything_needed_to_mine_them(indexed, db):
    """Every turn has session, role, text, confidence, retrieved chunk ids and a period."""
    indexed.ask("invite a team member", session_id="sess_fr9")
    rows = (
        db.query(Message)
        .join(Message.conversation)
        .filter(Message.organization_id == indexed.org)
        .all()
    )
    assert {r.role for r in rows} == {"customer", "assistant"}
    for r in rows:
        assert r.conversation.session_id == "sess_fr9"
        assert r.text and r.confidence is not None and r.retrieved_chunk_ids and r.period


# ---- analytics -----------------------------------------------------------------------

@req("FR10")
def test_fr10_batch_runs_over_a_chosen_reporting_period(indexed, db):
    """The batch can be run for one named period, touching only that period."""
    from support import replay

    replay(db, indexed.default_workspace)
    assert indexed.post(f"/api/analytics/run?period={PERIODS[1]}").status_code == 202
    assert indexed.get("/api/periods").json() == [PERIODS[1]]


@req("FR10")
@pytest.mark.xfail(strict=True, reason="Known gap: no in-app scheduler; schedule scripts/run_analytics.py with cron "
                                       "(the report allows APScheduler or system cron)")
def test_fr10_batch_is_scheduled_by_the_application():
    """The application itself triggers the batch on a cadence."""
    from app import main

    assert hasattr(main, "scheduler")


@req("FR11")
def test_fr11_queries_cluster_into_topics(with_traffic):
    """Repeated themes in the archive become separate topics."""
    insights = with_traffic.get("/api/insights").json()
    assert len(insights) >= 2
    samples = [" ".join(i["sampleQueries"]) for i in insights]
    assert any("upi" in s for s in samples) and any("invoice" in s for s in samples)


@req("FR11")
@pytest.mark.xfail(strict=True, reason="Defect found in testing: UMAP (min_dist=0) places every point next to its "
                                       "nearest neighbours, so HDBSCAN absorbs isolated one-off queries into the "
                                       "nearest topic instead of labelling them noise")
def test_fr11_isolated_queries_are_left_as_noise():
    """Three tight groups plus three isolated points: the isolated points belong to no topic."""
    import numpy as np

    from app.analytics import clustering

    rng = np.random.default_rng(0)
    centres = rng.normal(size=(3, 384))
    groups = [centres[g] + 0.15 * rng.normal(size=(20, 384)) for g in range(3)]
    isolated = rng.normal(size=(3, 384))
    vectors = np.vstack(groups + [isolated]).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    texts = [f"group {i // 20} question {i}" for i in range(60)] + ["odd one", "odd two", "odd three"]

    clusters = clustering.cluster_queries(texts, vectors, [0.5] * len(texts))
    assert len(clusters) == 3
    assigned = {texts[i] for c in clusters for i in c.indices}
    assert not assigned & {"odd one", "odd two", "odd three"}


@req("FR12")
def test_fr12_topics_have_keywords_and_a_generated_name(with_traffic):
    """Each topic carries representative keywords and a short human-readable name."""
    for insight in with_traffic.get("/api/insights").json():
        assert 1 <= len(insight["keywords"]) <= 6
        assert insight["name"] and len(insight["name"]) <= 120
        assert any(k.lower() in insight["name"].lower() for k in insight["keywords"])


@req("FR13")
def test_fr13_topics_are_classified_with_direction_and_rate_of_change(with_traffic):
    """Each topic is recurring, emerging or stable, with last period's volume and growth rate."""
    insights = with_traffic.get("/api/insights").json()
    assert {i["trend"] for i in insights} <= {"recurring", "emerging", "stable"}
    assert {"recurring", "emerging"} <= {i["trend"] for i in insights}
    for i in insights:
        assert i["growth"] == pytest.approx(trends.compute_growth(i["queryCount"], i["previousQueryCount"]), abs=1e-3)


@req("FR14")
def test_fr14_priority_combines_the_four_factors_into_one_ranking(with_traffic, db):
    """Stored priority equals the weighted formula of volume, growth, confidence deficit and severity."""
    insights = with_traffic.get("/api/insights").json()
    top_volume = max(i["queryCount"] for i in insights)
    for i in insights:
        expected = trends.priority_score(i["queryCount"] / top_volume, i["growth"], i["meanConfidence"], i["severity"])
        assert i["priority"] == pytest.approx(expected, abs=1e-3)
    assert [i["rank"] for i in sorted(insights, key=lambda x: -x["priority"])] == list(range(1, len(insights) + 1))


@req("FR15")
def test_fr15_report_turns_insights_into_categorised_recommendations(with_traffic):
    """The latest report has a summary and recommendations in the four action categories."""
    report = with_traffic.get("/api/reports/latest").json()
    assert report["summary"] and report["recommendations"]
    for rec in report["recommendations"]:
        assert rec["category"] in {"product", "documentation", "faq", "customer_issue"}
        if rec["category"] == "faq":
            assert rec["faqAnswer"]


@req("FR15")
def test_fr15_all_four_categories_are_reachable():
    """The category rules can produce each of the four categories."""
    def cluster(conf, sev, trend, count):
        return TopicCluster(mean_confidence=conf, severity=sev, trend=trend, query_count=count)

    median = 10
    assert recommend.choose_category(cluster(0.2, 0.8, "emerging", 9), median) == "product"
    assert recommend.choose_category(cluster(0.2, 0.3, "recurring", 12), median) == "documentation"
    assert recommend.choose_category(cluster(0.8, 0.3, "recurring", 20), median) == "faq"
    assert recommend.choose_category(cluster(0.8, 0.7, "stable", 3), median) == "customer_issue"


@req("FR16")
def test_fr16_every_insight_and_recommendation_expands_to_its_evidence(with_traffic, db):
    """Insights list their member questions and passages; recommendations list real customer questions."""
    for insight in with_traffic.get("/api/insights").json():
        detail = with_traffic.get(f"/api/insights/{insight['id']}").json()
        assert len(detail["memberQueries"]) == min(insight["queryCount"], 25)
        assert detail["weakestChunks"]
    report_id = db.query(Recommendation).filter(Recommendation.organization_id == with_traffic.org).first().report_id
    for rec in db.query(Recommendation).filter(Recommendation.report_id == report_id):
        assert rec.supporting_queries


@req("FR17")
def test_fr17_admin_endpoints_cover_sources_topics_trends_and_reports(with_traffic):
    """Everything the admin screens need is served: sources, periods, insights with history, reports."""
    t = with_traffic
    assert t.get("/api/sources").json()
    assert t.get("/api/overview").json()["volumeByPeriod"]
    first = t.get("/api/insights").json()[0]
    assert t.get(f"/api/insights/{first['id']}").json()["history"]
    assert t.get("/api/reports").json() and t.get("/api/reports/latest").status_code == 200


@req("FR18")
def test_fr18_evaluation_reports_the_three_metrics_on_a_held_out_set(indexed, db, fake_llm):
    """A held-out question set is scored for faithfulness, answer relevance and context relevance."""
    from app import evaluation

    questions = ["how do i refund a payment", "invite a team member", "export invoices to csv"]
    run = evaluation.run_evaluation(db, questions, indexed.default_workspace)
    served = indexed.get("/api/evaluation/latest").json()
    assert served["questionCount"] == 3
    for metric in ("faithfulness", "answerRelevance", "contextRelevance"):
        assert served[metric] == pytest.approx(0.9)
    assert run.organization_id == indexed.org


@req("FR18")
def test_fr18_low_scoring_questions_are_listed_as_failures(indexed, db, fake_llm):
    """Questions scoring under 0.5 on any metric are reported, worst first."""
    from app import evaluation

    fake_llm.judge_score = "0.2"
    evaluation.run_evaluation(db, ["how do i refund a payment"], indexed.default_workspace)
    failures = indexed.get("/api/evaluation/latest").json()["failures"]
    assert {f["metric"] for f in failures} == {"faithfulness", "answer_relevance", "context_relevance"}


# ---- multi-tenancy ------------------------------------------------------------------

@req("MT1", "AUTH4")
def test_mt1_the_organisation_comes_from_the_session_not_the_browser(client, tenant):
    """Without a session nothing answers; with one, the organisation is the user's, whatever the browser sends."""
    for path in ("/api/sources", "/api/insights", "/api/workspaces", "/api/overview"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Organization-Id": tenant.org}).status_code == 401
    assert tenant.get("/api/auth/me").json()["organizationId"] == tenant.org
    hop = client.get("/api/sources", headers={**tenant.headers(), "X-Organization-Id": "org_default"})
    assert hop.status_code == 403


@req("MT2")
def test_mt2_organisations_are_fully_separated(with_traffic, make_tenant):
    """A second organisation sees nothing of the first, and cannot address its ids."""
    other = make_tenant()
    assert other.get("/api/sources").json() == []
    assert other.get("/api/insights").json() == []
    assert other.ask("edit an invoice after sending")["citations"] == []
    insight = with_traffic.get("/api/insights").json()[0]["id"]
    assert other.get(f"/api/insights/{insight}").status_code == 404
