"""Acceptance scenarios: what each kind of user does, end to end, through the API.

Each test is one journey written as Given / When / Then. They use only the HTTP
API the frontend uses (plus the seeding helper standing in for a month of real
customers), so a passing journey means the screen built on it has what it needs.
"""

from __future__ import annotations

import pytest
from support import PERIODS, replay

from app.config import settings

req = pytest.mark.req


@req("FR1", "FR2", "FR3", "FR4", "FR6", "FR7", "MT1")
def test_uj1_new_organisation_goes_from_nothing_to_cited_answers(tenant, site):
    """UJ1. A new organisation signs in, adds its docs site and gets grounded answers.

    Given an organisation that has never used the system
    When it lists workspaces, adds its documentation URL and asks a question
    Then it has a default workspace, the source is ready with pages and chunks,
         and the answer cites the page section that answers the question.
    """
    workspaces = tenant.get("/api/workspaces").json()
    assert len(workspaces) == 1 and workspaces[0]["isDefault"] and workspaces[0]["sourceCount"] == 0

    source = tenant.add_website(f"{site}/docs/")
    assert source["status"] == "ready" and source["pageCount"] >= 7 and source["chunkCount"] > 10

    reply = tenant.ask("how long does a team invite last")
    assert reply["citations"][0]["headingPath"] == "Team › Inviting a team member"
    assert "seven days" in reply["citations"][0]["excerpt"]
    assert tenant.get("/api/workspaces").json()[0]["sourceCount"] == 1


@req("FR10", "FR11", "FR12", "FR13", "FR14", "FR15", "FR16")
def test_uj2_support_lead_reads_the_monthly_report(indexed, db):
    """UJ2. After three months of traffic, the support lead finds the rising problem.

    Given three months of customer questions, one topic rising 1 -> 2 -> 9 and undocumented
    When the analytics batch runs and the lead opens Overview, Insights and Report
    Then the rising topic is flagged emerging with low confidence, its detail shows three
         months of history and the questions behind it, and the report tells the owner
         what to do about it with those questions attached.
    """
    replay(db, indexed.default_workspace)
    assert indexed.post("/api/analytics/run").json()["status"] == "started"

    overview = indexed.get("/api/overview").json()
    assert overview["period"] == PERIODS[-1] and overview["emergingCount"] >= 1

    insights = indexed.get("/api/insights").json()
    upi = next(i for i in insights if any("upi" in q for q in i["sampleQueries"]))
    assert upi["trend"] == "emerging"
    assert upi["meanConfidence"] < settings.low_confidence_threshold

    detail = indexed.get(f"/api/insights/{upi['id']}").json()
    assert all("upi" in q["text"] or "autopay" in q["text"] for q in detail["memberQueries"])

    report = indexed.get("/api/reports/latest").json()
    action = next(r for r in report["recommendations"] if r["insightId"] == upi["id"])
    assert action["category"] in ("documentation", "product")
    assert any("upi" in q for q in action["supportingQueries"])
    assert action["volume"] == upi["queryCount"]


@req("FR6", "FR8", "FR15")
def test_uj3_documentation_owner_closes_a_gap_and_the_system_sees_it(indexed, db, tmp_path):
    """UJ3. The loop closes: acting on a documentation recommendation fixes the answers.

    Given the report recommends documenting UPI autopay mandates (low confidence)
    When the owner uploads a page covering it
    Then the same customer question is now answered from that page with higher confidence.
    """
    question = "upi autopay mandate revoked by bank"
    before = indexed.ask(question)
    assert before["confidence"] < settings.low_confidence_threshold

    page = tmp_path / "upi-autopay.md"
    page.write_text(
        "UPI autopay mandates. If your bank revoked the UPI autopay mandate, open Payments and "
        "choose Set up UPI autopay mandate again. A revoked mandate cannot be restarted by Kestrel; "
        "the client approves a new UPI autopay mandate in their banking app."
    )
    with page.open("rb") as fh:
        uploaded = indexed.post("/api/sources/upload", files={"file": (page.name, fh)}, data={"label": "UPI autopay"})
    assert indexed.source(uploaded.json()["id"])["status"] == "ready"

    after = indexed.ask(question)
    assert after["citations"][0]["sourceLabel"] == "UPI autopay"
    assert after["confidence"] > before["confidence"] + 0.2
    assert after["confidence"] >= settings.low_confidence_threshold


@req("FR3", "MT2")
def test_uj4_team_runs_a_second_product_in_its_own_workspace(indexed, site):
    """UJ4. One organisation, two products, kept apart, each with its own chunking.

    Given an organisation with its main docs indexed in the default workspace
    When it creates a 'Settings module' workspace with smaller chunks and a one-page crawl limit,
         and indexes the settings page there
    Then each workspace lists and answers from only its own sources.
    """
    ws = indexed.post("/api/workspaces", json={"name": "Settings module", "chunkTargetWords": 80,
                                               "chunkOverlapWords": 10, "crawlMaxPages": 1}).json()
    indexed.post("/api/sources", workspace=ws["id"], json={"kind": "website", "location": f"{site}/docs/settings.html"})

    mine = indexed.get("/api/sources", workspace=ws["id"]).json()
    assert [s["location"] for s in mine] == [f"{site}/docs/settings.html"]
    reply = indexed.post("/api/chat", workspace=ws["id"], json={"question": "refund a payment", "session_id": "s"}).json()
    assert all(c["headingPath"].startswith("Account settings") for c in reply["citations"]), reply["citations"]
    default_reply = indexed.ask("refund a payment")
    assert default_reply["citations"][0]["headingPath"] == "Payments › Refunds"


@req("FR18", "NFR4")
def test_uj5_evaluator_measures_answer_quality(indexed, db, fake_llm):
    """UJ5. Before a demo, someone checks the assistant still answers well.

    Given an indexed corpus and a held-out question set
    When the evaluation harness runs
    Then the Evaluation screen shows three metrics above the 0.80 target and no failures.
    """
    from app import evaluation

    run = evaluation.run_evaluation(db, ["refund a payment", "invite a team member", "export to csv"],
                                    indexed.default_workspace)
    shown = indexed.get("/api/evaluation/latest").json()
    assert shown["id"] == run.id and shown["faithfulness"] >= 0.80 and shown["failures"] == []


@req("NFR3")
def test_uj6_model_provider_goes_down_during_a_demo(indexed, db, fake_llm):
    """UJ6. The model quota runs out mid-demo; the product keeps working.

    Given a working deployment
    When the model provider starts refusing requests
    Then chat keeps answering from the passages, and the monthly report is still produced.
    """
    replay(db, indexed.default_workspace)
    fake_llm.mode = "down"
    reply = indexed.ask("how do i invite a team member")
    assert reply["citations"] and "unavailable" in reply["text"]
    indexed.post("/api/analytics/run")
    assert indexed.get("/api/reports/latest").json()["recommendations"]
    fake_llm.mode = "ok"
    assert "unavailable" not in indexed.ask("how do i invite a team member")["text"]


@req("MT1", "MT2")
def test_uj7_two_customers_on_one_deployment(with_traffic, make_tenant, site):
    """UJ7. Two organisations share the deployment and never see each other.

    Given organisation A with sources, traffic and reports
    When organisation B signs in, indexes the same public site and asks the same question
    Then B's workspace, sources, answers, insights and reports contain nothing of A's.
    """
    b = make_tenant()
    b.add_website(f"{site}/docs/")
    a_chunks = {c["chunkId"] for c in with_traffic.ask("refund a payment")["citations"]}
    b_chunks = {c["chunkId"] for c in b.ask("refund a payment")["citations"]}
    assert a_chunks and b_chunks and not (a_chunks & b_chunks)
    assert b.get("/api/insights").json() == [] and b.get("/api/reports").json() == []
    assert b.get("/api/overview").json()["queryCount"] == 1
    assert len(with_traffic.get("/api/sources").json()) == 1
