"""Chat: retrieval, confidence, generation and logging through the HTTP API."""

from __future__ import annotations

from app.config import settings
from app.models import Chunk, Conversation, Message


def test_covered_question_is_answered_with_citations_from_the_right_section(indexed):
    """A question the docs answer cites the section that answers it."""
    reply = indexed.ask("can i edit an invoice after sending it")
    assert reply["role"] == "assistant" and reply["text"]
    paths = [c["headingPath"] for c in reply["citations"]]
    assert paths[0] == "Invoices › Editing an invoice after sending"
    assert 0 < len(reply["citations"]) <= settings.retrieval_top_k
    sims = [c["similarity"] for c in reply["citations"]]
    assert sims == sorted(sims, reverse=True) and all(0 <= s <= 1 for s in sims)


def test_confidence_is_lower_for_a_question_the_docs_do_not_cover(indexed):
    """Retrieval confidence separates covered from uncovered questions."""
    covered = indexed.ask("how do i invite a team member")["confidence"]
    uncovered = indexed.ask("upi autopay mandate revoked by bank")["confidence"]
    assert covered > uncovered
    assert uncovered < settings.low_confidence_threshold


def test_every_turn_is_logged_with_confidence_and_retrieved_chunks(indexed, db):
    """Both turns persist; confidence and chunk ids match what the API returned."""
    reply = indexed.ask("refund a payment", session_id="sess_log_check")
    conv = db.query(Conversation).filter(
        Conversation.session_id == "sess_log_check", Conversation.organization_id == indexed.org
    ).one()
    turns = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at).all()
    assert [t.role for t in turns] == ["customer", "assistant"]
    customer, assistant = turns
    assert customer.text == "refund a payment"
    assert assistant.id == reply["id"]
    assert customer.confidence == assistant.confidence == reply["confidence"]
    assert assistant.retrieved_chunk_ids == [c["chunkId"] for c in reply["citations"]]
    assert customer.period and customer.workspace_id == indexed.default_workspace
    for chunk_id in assistant.retrieved_chunk_ids:
        assert db.get(Chunk, chunk_id) is not None


def test_same_session_id_continues_one_conversation(indexed, db):
    """Follow-up questions in a session join the same conversation."""
    indexed.ask("create an invoice", session_id="sess_follow")
    indexed.ask("and send it by email", session_id="sess_follow")
    convs = db.query(Conversation).filter(
        Conversation.session_id == "sess_follow", Conversation.organization_id == indexed.org
    ).all()
    assert len(convs) == 1
    assert db.query(Message).filter(Message.conversation_id == convs[0].id).count() == 4


def test_empty_workspace_says_there_is_nothing_indexed(tenant, fake_llm):
    """With no sources the assistant says so and does not call the model."""
    reply = tenant.ask("how do refunds work")
    assert reply["citations"] == [] and reply["confidence"] == 0
    assert "nothing indexed" in reply["text"].lower()
    assert fake_llm.calls == []


def test_model_outage_degrades_to_passages_and_still_logs(indexed, fake_llm, db):
    """If generation fails the answer is the retrieved text, and the turn is kept."""
    fake_llm.mode = "down"
    reply = indexed.ask("edit an invoice after sending", session_id="sess_outage")
    assert "unavailable" in reply["text"]
    assert "edit an invoice after sending" in reply["text"]
    assert reply["citations"]
    conv = db.query(Conversation).filter(
        Conversation.session_id == "sess_outage", Conversation.organization_id == indexed.org
    ).one()
    assert db.query(Message).filter(Message.conversation_id == conv.id).count() == 2


def test_prompt_sent_to_the_model_contains_only_retrieved_passages(indexed, fake_llm):
    """Grounding: the generator sees the passages and the question, with sources named."""
    indexed.ask("payment methods")
    prompt = fake_llm.calls[-1]["user"]
    assert prompt.startswith("Passages:") and "Question: payment methods" in prompt
    assert "Section: Payments › Payment methods" in prompt
    assert "answer only" in fake_llm.calls[-1]["system"].lower()


# ---- conversation history -----------------------------------------------------------

def test_history_returns_every_turn_in_order_with_citations(indexed):
    """A conversation comes back question, answer, question, answer, with the answers' citations."""
    first = indexed.ask("can i edit an invoice after sending it", session_id="sess_hist")
    second = indexed.ask("and send it by email", session_id="sess_hist")
    turns = indexed.get("/api/chat/history?session_id=sess_hist").json()
    assert [t["role"] for t in turns] == ["customer", "assistant", "customer", "assistant"]
    assert turns[0]["text"] == "can i edit an invoice after sending it"
    assert turns[1] == first and turns[3] == second
    assert turns[0]["citations"] == [] and turns[0]["confidence"] is None


def test_history_for_a_new_session_is_empty_not_an_error(indexed):
    assert indexed.get("/api/chat/history?session_id=sess_never_used").json() == []


def test_history_survives_a_reindex(indexed):
    """Citations are stored with the turn, so replacing the chunks does not blank old answers."""
    reply = indexed.ask("how do i refund a payment", session_id="sess_reindex")
    indexed.post(f"/api/sources/{indexed.site_source['id']}/reindex")
    turns = indexed.get("/api/chat/history?session_id=sess_reindex").json()
    assert turns[1]["citations"] == reply["citations"] and turns[1]["citations"]


def test_history_is_per_workspace(indexed):
    """The same session id in another workspace is a different, empty conversation."""
    indexed.ask("refund a payment", session_id="sess_ws")
    other = indexed.post("/api/workspaces", json={"name": "Elsewhere"}).json()["id"]
    assert indexed.get("/api/chat/history?session_id=sess_ws", workspace=other).json() == []


def test_turns_logged_before_citations_were_stored_are_rebuilt(indexed, db):
    """Older rows without a citation snapshot get citations from their chunk ids."""
    from app.models import Message

    reply = indexed.ask("invite a team member", session_id="sess_legacy")
    row = db.get(Message, reply["id"])
    row.citations = None
    db.commit()
    rebuilt = indexed.get("/api/chat/history?session_id=sess_legacy").json()[1]["citations"]
    assert [c["chunkId"] for c in rebuilt] == [c["chunkId"] for c in reply["citations"]]
    assert [c["similarity"] for c in rebuilt] == [c["similarity"] for c in reply["citations"]]
