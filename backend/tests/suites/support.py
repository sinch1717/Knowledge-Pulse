"""Stand-ins for the two external dependencies, and shared test helpers.

The fakes replace the lowest layer only, so everything above runs for real:

- FakeEmbeddingModel replaces the sentence-transformers model inside
  app.embeddings. embed(), normalisation, Chroma, similarity conversion and
  confidence scoring are all the production code.
- FakeLLM replaces the HTTP call inside app.llm (_groq). complete(),
  complete_json() with its fence stripping, and every caller's fallback path
  are the production code.

A hashed bag of words is a poor embedding, but it is deterministic and puts
texts that share vocabulary near each other, which is all the pipeline needs to
show that retrieval, confidence, clustering and trend detection are wired
correctly. Quality with the real model is what the live suite checks.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np

DIMENSIONS = 384  # same as all-MiniLM-L6-v2, so Chroma sees the production shape

STOPWORDS = {
    "a", "an", "the", "i", "my", "me", "to", "of", "and", "or", "in", "on", "for", "is", "it",
    "do", "does", "can", "how", "what", "when", "why", "with", "by", "be", "are", "you", "your",
    "this", "that", "from", "at", "as", "we", "our", "please", "there", "any", "way", "get",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words if w not in STOPWORDS]


class FakeEmbeddingModel:
    """Stands in for SentenceTransformer: same encode() signature, 384 dimensions."""

    def encode(self, texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False,
               convert_to_numpy=True):
        out = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in _tokens(text):
                index = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % DIMENSIONS
                out[row, index] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


class FakeLLM:
    """Replaces app.llm._groq. Answers by recognising which prompt it was sent.

    mode:
      "ok"     sensible output for every prompt the system sends
      "down"   raises LLMError, as a quota or network failure would
      "empty"  raises the error _groq raises on an empty reply (reasoning models)
    """

    def __init__(self):
        self.mode = "ok"
        self.calls: list[dict] = []
        self.judge_score = "0.90"

    def __call__(self, system: str, user: str, temperature: float, max_tokens: int, json_mode: bool = False):
        from app import llm

        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if self.mode == "down":
            raise llm.LLMError("Groq returned 429: rate limit reached (test)")
        if self.mode == "empty":
            raise llm.LLMError("Groq returned empty content (test)")

        if "strict evaluator" in system:
            return self.judge_score
        if "List 8 things" in user:
            return json.dumps({"topics": SEED_TOPICS})
        if "support questions about this one topic" in user:
            topic = re.search(r"Topic: (.+)", user)
            topic = topic.group(1).strip() if topic else "invoices"
            n = int(re.search(r"Write (\d+)", user).group(1))
            return json.dumps({"questions": [f"{topic} question {uuid.uuid4().hex[:4]}" for _ in range(n)]})
        if "Write two natural questions" in user:
            passage = user.split("Passage:", 1)[-1]
            words = [w for w in _tokens(passage) if len(w) > 4][:6]
            return json.dumps({"questions": [" ".join(words[:3]), " ".join(words[3:6]) or words[0]]})
        if "headline" in user:
            # Fenced on purpose: complete_json must strip it.
            body = {
                "headline": "Explain this topic on the help page",
                "body": "Customers keep asking about this and the current pages do not answer it.",
                "expected_effect": "Fewer repeat questions on this topic.",
                "faq_answer": "Open the page and follow the steps.",
            }
            return "```json\n" + json.dumps(body) + "\n```"
        if "Give a short title" in user:
            terms = re.search(r"Distinctive terms:\s*(.+)", user)
            words = terms.group(1).split(", ")[:3] if terms else ["topic"]
            return " ".join(w.capitalize() for w in words)
        if "top of a monthly report" in user:
            return "Questions about a newly rising topic grew sharply this month. Two long-running topics persist."
        return "Here is what the documentation says, based on the passages provided."


# ---- traffic -----------------------------------------------------------------

# Three periods fixed in the past, so results do not depend on today's date.
PERIODS = ["2026-06", "2026-07", "2026-08"]

COVERED = [
    "can i edit an invoice after sending it",
    "edit sent invoice after sending",
    "how to edit an invoice after sending it by email",
    "editing an invoice after sending",
    "can i change an invoice after sending",
    "edit invoice after sending client",
    "invoice edit after sending corrected",
    "edit the sent invoice",
]
TEAM = [
    "how do i invite a team member",
    "invite team member email",
    "team member invite role",
    "invite a new team member",
    "change team member role",
    "team member roles permissions",
    "invite email for team member",
]
EMERGING = [
    "upi autopay mandate revoked by bank",
    "upi autopay mandate failed again",
    "upi mandate autopay cancelled",
    "autopay upi mandate revoked urgent",
    "upi autopay mandate error",
    "bank revoked upi autopay mandate",
    "upi autopay mandate not working",
    "upi mandate revoked autopay broken",
    "autopay mandate upi revoked cannot pay",
]

# Volume per period: covered and team steady (recurring), the UPI topic 1 -> 2 -> 9.
DEFAULT_PLAN = [
    {"pool": COVERED, "counts": [7, 8, 8]},
    {"pool": TEAM, "counts": [6, 6, 7]},
    {"pool": EMERGING, "counts": [1, 2, 9]},
]

SEED_TOPICS = [
    {"topic": "editing invoices", "covered": True, "severity": "annoying"},
    {"topic": "inviting team members", "covered": True, "severity": "curious"},
    {"topic": "refunds", "covered": True, "severity": "annoying"},
    {"topic": "exporting csv", "covered": True, "severity": "curious"},
    {"topic": "upi autopay mandates", "covered": False, "severity": "blocking"},
    {"topic": "gst e-invoicing", "covered": False, "severity": "blocking"},
    {"topic": "multi currency", "covered": False, "severity": "annoying"},
    {"topic": "mobile app", "covered": False, "severity": "curious"},
]


def replay(db, workspace_id: str, plan=None, periods=PERIODS) -> int:
    """Put a plan of questions through the real chat engine, spread over periods."""
    from app.rag import engine

    plan = plan or DEFAULT_PLAN
    total = 0
    for p_index, period in enumerate(periods):
        base = datetime.strptime(period + "-03", "%Y-%m-%d").replace(tzinfo=timezone.utc)
        for group in plan:
            for n in range(group["counts"][p_index]):
                question = group["pool"][n % len(group["pool"])]
                if n >= len(group["pool"]):
                    question += " please"
                engine.answer(
                    db,
                    question,
                    session_id=f"test_{uuid.uuid4().hex[:10]}",
                    synthetic=True,
                    created_at=base + timedelta(days=n % 20, hours=n % 9),
                    workspace_id=workspace_id,
                )
                total += 1
    return total


def new_org(prefix: str = "org_t") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
