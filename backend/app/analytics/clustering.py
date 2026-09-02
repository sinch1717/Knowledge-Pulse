"""Turning a pile of questions into named topics.

The pipeline is the one established by BERTopic: sentence embeddings, UMAP to
bring the dimensionality down to something density clustering can work with, then
HDBSCAN. Two properties matter here and are the reason for choosing it over
k-means or LDA. The topic count is not fixed in advance, so the data decides how
many things customers are asking about. And unrelated one-off questions are
assigned to noise instead of being forced into whichever cluster is nearest,
which on support text is most of the value.

HDBSCAN comes from scikit-learn rather than the standalone package. Same
algorithm, one fewer C extension to compile.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from app import llm
from app.config import settings

log = logging.getLogger(__name__)

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "in",
    "on", "for", "and", "or", "but", "if", "it", "its", "this", "that", "these",
    "with", "as", "at", "by", "from", "how", "what", "why", "when", "where", "can",
    "do", "does", "did", "i", "my", "me", "we", "you", "your", "not", "no", "so",
    "there", "here", "get", "got", "have", "has", "had", "will", "would", "should",
    "am", "any", "all", "just", "about", "into", "out", "up", "some", "then",
}


@dataclass
class Cluster:
    label: int
    indices: list[int]
    centroid: np.ndarray
    keywords: list[str]
    name: str
    mean_confidence: float
    severity: float


def _tokenise(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9'-]{1,}", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def class_tfidf(docs_by_cluster: dict[int, list[str]], top_n: int = 6) -> dict[int, list[str]]:
    """Class-based TF-IDF: treat each cluster as one document, score its terms
    against the whole corpus. This is what makes labels distinctive rather than
    just frequent — 'invoice' appears everywhere and so scores low."""
    counts = {c: Counter(_tokenise(" ".join(docs))) for c, docs in docs_by_cluster.items()}
    corpus_terms = Counter()
    for counter in counts.values():
        corpus_terms.update(counter.keys())

    n_clusters = max(1, len(counts))
    keywords: dict[int, list[str]] = {}
    for cluster, counter in counts.items():
        total = sum(counter.values()) or 1
        scored = {
            term: (freq / total) * np.log(1 + n_clusters / corpus_terms[term])
            for term, freq in counter.items()
        }
        keywords[cluster] = [t for t, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:top_n]]
    return keywords


def name_cluster(keywords: list[str], samples: list[str]) -> str:
    """Ask the model for a short human title. Falls back to the keywords."""
    fallback = ", ".join(keywords[:3]) if keywords else "Unlabelled topic"
    try:
        prompt = (
            "These are customer support questions that were grouped together.\n\n"
            + "\n".join(f"- {s}" for s in samples[:8])
            + f"\n\nDistinctive terms: {', '.join(keywords)}\n\n"
            "Give a short title, at most eight words, naming what these customers are "
            "trying to do or what is going wrong. No quotes, no full stop."
        )
        title = llm.complete(
            prompt,
            system="You write short, plain, specific labels. Never generic ones like 'Billing issues'.",
            temperature=0.3,
            max_tokens=40,
        )
        title = title.strip().strip('"').rstrip(".")
        return title[:120] if title else fallback
    except llm.LLMError as exc:
        log.warning("Topic naming unavailable: %s", exc)
        return fallback


def infer_severity(name: str, samples: list[str]) -> float:
    """How badly is this blocking the customer? 0 is curiosity, 1 is 'I cannot work'.

    Keyword heuristic first so the system still functions without an LLM, then the
    model refines it. Kept as a heuristic rather than a learned model on purpose:
    it is inspectable, which matters when a reviewer asks why a topic ranked high.
    """
    blob = " ".join([name] + samples[:6]).lower()
    hard = ("cannot", "can't", "failed", "failing", "error", "broken", "stuck", "lost",
            "charged", "refund", "not working", "missing", "wrong", "urgent")
    soft = ("how do i", "where is", "what does", "can i", "is it possible", "difference between")
    score = 0.35
    score += 0.10 * sum(1 for k in hard if k in blob)
    score -= 0.05 * sum(1 for k in soft if k in blob)
    return round(max(0.05, min(1.0, score)), 3)


def cluster_queries(texts: list[str], vectors: np.ndarray, confidences: list[float]) -> list[Cluster]:
    from sklearn.cluster import HDBSCAN

    if len(texts) < settings.hdbscan_min_cluster_size * 2:
        log.warning("Only %d queries; too few to cluster meaningfully", len(texts))
        return []

    # UMAP struggles when n_neighbors approaches the sample count.
    neighbours = min(settings.umap_neighbours, max(2, len(texts) - 1))
    components = min(settings.umap_components, max(2, len(texts) - 2))

    import warnings

    import umap

    # UMAP warns that a fixed random_state disables parallelism. That trade is
    # made deliberately: a reproducible run matters more here than speed.
    warnings.filterwarnings("ignore", message=".*n_jobs value.*overridden.*")

    reducer = umap.UMAP(
        n_neighbors=neighbours,
        n_components=components,
        metric="cosine",
        min_dist=0.0,
        random_state=42,  # reproducibility matters more than the last percent of quality
    )
    reduced = reducer.fit_transform(vectors)

    labels = HDBSCAN(
        min_cluster_size=settings.hdbscan_min_cluster_size,
        min_samples=2,
        metric="euclidean",
    ).fit_predict(reduced)

    groups: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        if label == -1:  # noise: a genuine one-off, not a topic
            continue
        groups.setdefault(int(label), []).append(index)

    if not groups:
        log.warning("HDBSCAN found no clusters; every query was treated as noise")
        return []

    keywords = class_tfidf({c: [texts[i] for i in idx] for c, idx in groups.items()})

    clusters: list[Cluster] = []
    for label, indices in groups.items():
        samples = [texts[i] for i in indices[:10]]
        name = name_cluster(keywords[label], samples)
        clusters.append(
            Cluster(
                label=label,
                indices=indices,
                centroid=vectors[indices].mean(axis=0),
                keywords=keywords[label],
                name=name,
                mean_confidence=round(float(np.mean([confidences[i] for i in indices])), 4),
                severity=infer_severity(name, samples),
            )
        )

    noise = int((labels == -1).sum())
    log.info("Found %d topics from %d queries (%d treated as noise)", len(clusters), len(texts), noise)
    return clusters
