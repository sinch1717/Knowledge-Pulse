"""Run the whole pipeline with no API keys and no model download.

The embedder is replaced with a deterministic bag-of-words hash and the language
model with a canned responder. Neither produces good output — that is not the
point. The point is to prove the plumbing works: ingestion writes chunks,
retrieval returns them, confidence is computed, conversations are logged,
clustering finds topics, growth is measured across periods, and a report comes
out with recommendations attached.

Run this before you spend a single API call.

    python scripts/smoke_test.py
"""

from __future__ import annotations

import hashlib
import logging
import random
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
log = logging.getLogger("smoke")

DIMENSIONS = 96


# --------------------------------------------------------------------------
# Stubs
# --------------------------------------------------------------------------

def fake_embed(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Hashed bag of words, L2 normalised. Same words in, same vector out, and
    texts sharing vocabulary land near each other — enough for clustering to have
    something real to find."""
    out = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
    for row, text in enumerate(texts):
        for word in text.lower().split():
            index = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % DIMENSIONS
            out[row, index] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


def fake_complete(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900) -> str:
    if "short title" in user or "Give a short title" in user:
        words = [w for w in user.split() if len(w) > 5][:3]
        return " ".join(words) or "Unnamed topic"
    return "Stubbed answer. The passages given cover part of this question."


def fake_complete_json(user: str, system: str = "", temperature: float = 0.2, max_tokens: int = 900):
    return {
        "headline": "Stubbed recommendation headline",
        "body": "Stubbed body text standing in for model output.",
        "expected_effect": "Stubbed expected effect.",
        "faq_answer": "Stubbed FAQ answer.",
    }


def install_stubs() -> None:
    from app import embeddings, llm

    embeddings.embed = fake_embed
    embeddings.embed_one = lambda text: fake_embed([text])[0]
    llm.complete = fake_complete
    llm.complete_json = fake_complete_json
    # The modules that imported these by name need patching too.
    from app.analytics import clustering, recommend

    clustering.llm.complete = fake_complete
    recommend.llm.complete = fake_complete
    recommend.llm.complete_json = fake_complete_json


# --------------------------------------------------------------------------
# Fixture corpus
# --------------------------------------------------------------------------

PAGES = {
    "Invoicing": [
        ("Creating an invoice", "Open the invoices tab and choose new invoice. Add the client, "
         "the line items and the due date. The invoice is saved as a draft until you send it."),
        ("Editing a sent invoice", "An unpaid invoice can be edited directly and the client sees "
         "the updated version at the same link. A paid invoice cannot be changed; issue a credit "
         "note instead and raise a fresh invoice."),
    ],
    "Payments": [
        ("Recurring invoices", "Recurring invoices are generated on the schedule you set and sent "
         "to the client registered email address. The schedule can be weekly monthly or yearly."),
        ("Payment methods", "Clients can pay by card by net banking or by UPI. Payment status "
         "appears on the invoice within a few minutes of the transaction completing."),
    ],
    "Team": [
        ("Inviting a team member", "Go to settings then team and enter the email address. The "
         "person receives an invitation link that expires after seven days."),
        ("Roles and permissions", "An admin can do anything. An editor can create and send "
         "invoices. A viewer can read invoices but cannot see bank account details."),
    ],
}

# Deliberately absent from the corpus above, so retrieval must fail on it.
EMERGING = [
    "upi autopay mandate failed no error shown anywhere",
    "recurring charge did not happen this month mandate still active",
    "how do i tell if a bank revoked an autopay mandate",
    "autopay mandate keeps failing for every client since last week",
    "is there a webhook when an autopay mandate fails",
    "mandate says active but nothing was charged at all",
    "autopay stopped working for all my clients this month",
    "no notification when an autopay mandate is revoked by bank",
]

COVERED = [
    "can i edit an invoice after i already sent it",
    "how do i change the amount on a sent invoice",
    "client wants a different address on an invoice i sent",
    "is it possible to edit a paid invoice or not",
    "how to issue a credit note instead of editing an invoice",
    "editing a sent invoice changes the link or not",
    "can i still edit an unpaid invoice after sending",
    "what happens if i edit an invoice the client already saw",
]

TEAM = [
    "how do i invite my accountant to the account",
    "can a viewer see my bank account details",
    "what can an editor do that a viewer cannot",
    "team invitation link expired what now",
    "how many people can i add to my team",
    "difference between admin and editor role",
    "invite email never arrived for my team member",
    "can i change someone role after inviting them",
]


def main() -> None:
    workspace = tempfile.mkdtemp(prefix="kp_smoke_")
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{workspace}/smoke.db"
    os.environ["CHROMA_PATH"] = f"{workspace}/chroma"
    os.environ["HDBSCAN_MIN_CLUSTER_SIZE"] = "4"
    os.environ["UMAP_NEIGHBOURS"] = "5"

    from app.config import get_settings

    get_settings.cache_clear()
    import app.config as config_module

    config_module.settings = get_settings()

    install_stubs()

    from app import embeddings, vector_store
    from app.analytics import batch
    from app.db import SessionLocal, create_tables
    from app.ingest import chunker
    from app.models import Chunk, Message, Source
    from app.rag import engine

    create_tables()
    db = SessionLocal()

    # ---- 1. ingest ------------------------------------------------------
    log.info("1/5  Indexing a fixture corpus")
    source = Source(id="src_smoke", kind="text", label="Fixture docs",
                    location="memory", status="indexing")
    db.add(source)
    db.commit()

    sections = [
        chunker.Section(heading_path=f"{top} › {sub}", text=body)
        for top, entries in PAGES.items()
        for sub, body in entries
    ]
    raw = chunker.chunk_sections(sections)
    assert raw, "chunker produced nothing"

    texts = [c.text for c in raw]
    vectors = embeddings.embed(texts)
    ids = [f"chk_{n:04d}" for n in range(len(raw))]
    metas = [{"source_id": source.id, "source_label": source.label,
              "heading_path": c.heading_path, "url": ""} for c in raw]
    vector_store.upsert(ids, vectors, metas, texts)
    for chunk_id, c in zip(ids, raw):
        db.add(Chunk(id=chunk_id, source_id=source.id, heading_path=c.heading_path,
                     text=c.text, word_count=c.word_count))
    source.status = "ready"
    source.chunk_count = len(ids)
    db.commit()
    log.info("     %d chunks indexed, vector store holds %d", len(ids), vector_store.count())

    # ---- 2. retrieval and confidence ------------------------------------
    log.info("2/5  Checking retrieval confidence separates covered from uncovered")
    hits_known, conf_known = engine.retrieve_only("can i edit an invoice after sending it")
    hits_unknown, conf_unknown = engine.retrieve_only("upi autopay mandate revoked by bank")
    log.info("     covered question   confidence %.3f (%d hits)", conf_known, len(hits_known))
    log.info("     uncovered question confidence %.3f (%d hits)", conf_unknown, len(hits_unknown))
    assert conf_known > conf_unknown, "confidence failed to separate covered from uncovered"

    # ---- 3. replay three periods ----------------------------------------
    log.info("3/5  Replaying three periods of traffic")
    random.seed(11)
    now = datetime.now(timezone.utc).replace(day=10)
    periods = [(now - timedelta(days=30 * back)) for back in (2, 1, 0)]

    plan = [
        {"pool": COVERED, "counts": [7, 8, 8]},
        {"pool": TEAM, "counts": [6, 6, 7]},
        {"pool": EMERGING, "counts": [1, 2, 9]},  # the planted emerging concern
    ]

    total = 0
    for index, moment in enumerate(periods):
        for group in plan:
            for n in range(group["counts"][index]):
                question = group["pool"][n % len(group["pool"])]
                if n >= len(group["pool"]):
                    question += " please"  # keep near-duplicates from collapsing entirely
                engine.answer(
                    db, question,
                    session_id=f"smoke_{uuid.uuid4().hex[:8]}",
                    synthetic=True,
                    created_at=moment + timedelta(days=random.randint(0, 18)),
                )
                total += 1
    log.info("     %d questions logged across %s", total,
             ", ".join(p.strftime("%Y-%m") for p in periods))

    logged = db.query(Message).filter(Message.role == "customer").count()
    assert logged == total, f"expected {total} logged questions, found {logged}"

    # ---- 4. analytics ----------------------------------------------------
    log.info("4/5  Running the analytics batch over every period")
    reports = batch.run_for_all_periods(db)
    assert reports, "no reports produced"

    final = reports[-1]
    log.info("     %s: %d questions, %.0f%% poorly answered",
             final.period, final.query_count, final.unanswered_rate * 100)

    from app.models import TopicCluster

    clusters = (db.query(TopicCluster)
                .filter(TopicCluster.period == final.period)
                .order_by(TopicCluster.rank).all())
    log.info("     %d topics found", len(clusters))
    for c in clusters:
        log.info("       %2d. %-38s n=%-3d prev=%-3d growth=%+.2f conf=%.2f pri=%.2f  %s",
                 c.rank, c.name[:38], c.query_count, c.previous_query_count,
                 c.growth, c.mean_confidence, c.priority, c.trend)

    assert len(clusters) >= 2, "clustering collapsed everything into one topic"
    assert any(c.previous_query_count > 0 for c in clusters), \
        "no topic matched across periods — centroid matching is broken"

    # ---- 5. report -------------------------------------------------------
    log.info("5/5  Checking the report")
    assert final.recommendations, "report has no recommendations"
    categories = {r.category for r in final.recommendations}
    log.info("     %d recommendations across categories: %s",
             len(final.recommendations), ", ".join(sorted(categories)))
    for rec in final.recommendations:
        assert rec.supporting_queries, f"{rec.id} has no evidence attached"
    log.info("     every recommendation carries its supporting questions")

    db.close()
    log.info("")
    log.info("All checks passed. The pipeline is wired correctly.")
    log.info("Real embeddings and a real model will change the quality of the output,")
    log.info("not its shape. Workspace: %s", workspace)


if __name__ == "__main__":
    main()
