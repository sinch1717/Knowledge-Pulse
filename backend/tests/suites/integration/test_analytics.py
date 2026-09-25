"""The analytics batch end to end: logged traffic in, ranked insights and a report out."""

from __future__ import annotations

from support import PERIODS

from app.models import ClusterMember, Message, Report, TopicCluster

CATEGORIES = {"product", "documentation", "faq", "customer_issue"}


def _insights(t, period=None):
    q = f"?period={period}" if period else ""
    return t.get(f"/api/insights{q}").json()


def test_batch_analyses_every_period_in_order(with_traffic):
    """All three periods are analysed; the latest is the default view."""
    assert with_traffic.get("/api/periods").json() == list(reversed(PERIODS))
    assert _insights(with_traffic) == _insights(with_traffic, PERIODS[-1])


def test_ranked_list_is_ordered_by_priority(with_traffic):
    """Rank 1 has the highest priority and ranks are contiguous."""
    insights = _insights(with_traffic)
    assert len(insights) >= 2
    assert [i["rank"] for i in insights] == list(range(1, len(insights) + 1))
    priorities = [i["priority"] for i in insights]
    assert priorities == sorted(priorities, reverse=True)


def test_planted_emerging_topic_is_detected(with_traffic):
    """The topic that went 1 -> 2 -> 9 is flagged emerging in the last period."""
    insights = _insights(with_traffic)
    upi = [i for i in insights if any("upi" in q for q in i["sampleQueries"])]
    assert upi, "the UPI topic did not form a cluster"
    assert upi[0]["trend"] == "emerging"
    assert upi[0]["meanConfidence"] < min(i["meanConfidence"] for i in insights if i not in upi)


def test_steady_topics_are_matched_across_periods(with_traffic):
    """Topics present every month are linked to last month's cluster and read as recurring."""
    insights = _insights(with_traffic)
    linked = [i for i in insights if i["previousQueryCount"] > 0]
    assert linked
    assert any(i["trend"] == "recurring" for i in linked)
    detail = with_traffic.get(f"/api/insights/{linked[0]['id']}").json()
    assert len(detail["history"]) >= 2
    assert [p["period"] for p in detail["history"]] == sorted(p["period"] for p in detail["history"])


def test_insight_detail_exposes_member_questions_and_weakest_passages(with_traffic, db):
    """Each insight expands into the questions that make it up and the passages they got."""
    first = _insights(with_traffic)[0]
    detail = with_traffic.get(f"/api/insights/{first['id']}").json()
    member_ids = {m["id"] for m in detail["memberQueries"]}
    stored = {m.message_id for m in db.query(ClusterMember).filter(ClusterMember.cluster_id == first["id"])}
    assert member_ids and member_ids <= stored
    confidences = [m["confidence"] for m in detail["memberQueries"]]
    assert confidences == sorted(confidences)  # worst first
    assert detail["weakestChunks"]


def test_report_has_recommendations_with_evidence(with_traffic, db):
    """The report's recommendations each name a category and carry real customer questions."""
    report = with_traffic.get("/api/reports/latest").json()
    assert report["period"] == PERIODS[-1]
    assert report["summary"]
    assert 1 <= len(report["recommendations"]) <= 6
    for rec in report["recommendations"]:
        assert rec["category"] in CATEGORIES
        assert rec["headline"] and rec["body"] and rec["expectedEffect"]
        members = {
            m.text
            for m in db.query(Message)
            .join(ClusterMember, ClusterMember.message_id == Message.id)
            .filter(ClusterMember.cluster_id == rec["insightId"])
        }
        assert rec["supportingQueries"] and set(rec["supportingQueries"]) <= members


def test_overview_counts_match_the_archive(with_traffic):
    """Overview figures agree with what was logged for the latest period."""
    overview = with_traffic.get("/api/overview").json()
    assert overview["period"] == PERIODS[-1]
    assert overview["queryCount"] == 8 + 7 + 9
    assert overview["topicCount"] == len(_insights(with_traffic))
    assert [p["period"] for p in overview["volumeByPeriod"]] == PERIODS
    assert 0 <= overview["unansweredRate"] <= 1
    assert overview["emergingCount"] >= 1


def test_rerunning_the_batch_replaces_a_period_instead_of_duplicating_it(with_traffic, db):
    """The batch is idempotent per period."""
    ws = with_traffic.default_workspace
    before = db.query(TopicCluster).filter(TopicCluster.workspace_id == ws).count()
    with_traffic.post("/api/analytics/run")
    with_traffic.post(f"/api/analytics/run?period={PERIODS[-1]}")
    db.expire_all()
    assert db.query(TopicCluster).filter(TopicCluster.workspace_id == ws).count() == before
    assert db.query(Report).filter(Report.workspace_id == ws).count() == len(PERIODS)


def test_too_little_traffic_produces_no_report(indexed):
    """A period with only a handful of questions is skipped with a clear 404 on the report."""
    for q in ("refund a payment", "invite a member", "export csv"):
        indexed.ask(q)
    indexed.post("/api/analytics/run")
    resp = indexed.get("/api/reports/latest")
    assert resp.status_code == 404 and "analytics" in resp.json()["detail"].lower()


def test_model_outage_still_produces_a_report(indexed, db, fake_llm):
    """Without the model, topics fall back to keyword names and recommendations to templates."""
    from support import replay

    replay(db, indexed.default_workspace)
    fake_llm.mode = "down"
    indexed.post("/api/analytics/run")
    report = indexed.get("/api/reports/latest").json()
    assert report["recommendations"]
    assert all(r["headline"].startswith("Look into:") for r in report["recommendations"])
    assert "topics were identified" in report["summary"]
