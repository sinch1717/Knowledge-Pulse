"""Live checks against the real embedding model and the real LLM provider.

Skipped unless KP_LIVE=1. Uses the API keys and model names in backend/.env, and
temporary storage, so it never touches the real database. Costs a few dozen model
calls. Optional: KP_LIVE_SITE=https://plausible.io/docs to crawl a real site too
(slow: the crawler is polite).

    KP_LIVE=1 python -m pytest -m live
"""

from __future__ import annotations

import os

import pytest

from app import embeddings, llm
from app.config import settings

req = pytest.mark.req


def test_live_embedding_model_loads_and_has_the_expected_shape():
    """The real sentence-transformers model loads and returns normalised 384-d vectors."""
    vectors = embeddings.embed(["how do i refund a payment", "invite a team member"])
    assert vectors.shape == (2, 384)
    assert abs(float((vectors[0] ** 2).sum()) - 1.0) < 1e-3


@req("FR8")
def test_live_confidence_separates_covered_from_uncovered(indexed):
    """With real embeddings, a documented question scores clearly higher than an undocumented one."""
    covered = indexed.ask("how long does a team invite last before it expires")["confidence"]
    uncovered = indexed.ask("does kestrel support upi autopay mandates for recurring billing")["confidence"]
    print(f"\n  covered {covered:.3f}  uncovered {uncovered:.3f}  threshold {settings.low_confidence_threshold}")
    assert covered > uncovered + 0.05


def test_live_model_answers_plain_text():
    """The configured provider returns non-empty text for a normal prompt."""
    text = llm.complete("Say the word ready.", system="Reply with one word.", max_tokens=20)
    assert text.strip()


def test_live_model_returns_json_for_structured_prompts():
    """Regression for the reasoning-model bug: structured prompts return parseable JSON, not nothing."""
    result = llm.complete_json(
        'Return a JSON object with keys "headline" and "body" about exporting invoices to CSV.',
        system="You write short product advice.",
        max_tokens=300,
    )
    assert isinstance(result, dict) and result.get("headline") and result.get("body")


@req("NFR4")
def test_live_faithfulness_meets_the_target(indexed, db):
    """NFR4 for real: faithfulness at least 0.80 on questions the fixture docs answer."""
    from app import evaluation

    questions = [
        "how do i edit an invoice after sending it",
        "how long does a team invite last",
        "can i give a partial refund",
        "how do i export invoices to csv",
        "what happens when a card payment fails",
    ]
    run = evaluation.run_evaluation(db, questions, indexed.default_workspace)
    print(f"\n  faithfulness {run.faithfulness:.2f}  answer {run.answer_relevance:.2f}  context {run.context_relevance:.2f}")
    assert run.question_count == len(questions)
    assert run.faithfulness >= 0.80


@pytest.mark.skipif(not os.environ.get("KP_LIVE_SITE"), reason="set KP_LIVE_SITE to crawl a real documentation site")
def test_live_real_site_crawls_and_answers(tenant):
    """A real documentation site crawls to ready and answers a question from it."""
    source = tenant.add_website(os.environ["KP_LIVE_SITE"])
    assert source["status"] == "ready", source.get("error")
    print(f"\n  {source['pageCount']} pages, {source['chunkCount']} chunks")
    assert tenant.ask("how do i get started")["citations"]
