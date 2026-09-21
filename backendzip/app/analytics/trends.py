"""Comparing this period against the last one, and ranking what came out.

Two jobs.

First, matching. A topic in August and a topic in July are the same topic if
their centroids are close enough in embedding space. This is what makes trend
analysis possible at all — the cluster labels HDBSCAN assigns are arbitrary
integers and mean nothing across runs, so identity has to come from the content.

Second, ranking. The priority formula from the report, straight:

    priority = 0.30·volume + 0.30·growth + 0.25·(1 − confidence) + 0.15·severity

Each term is normalised into [0, 1] first, otherwise volume would swamp
everything else the moment one topic got popular.
"""

from __future__ import annotations

import logging

import numpy as np

from app.config import settings
from app.models import TopicCluster

log = logging.getLogger(__name__)


def match_to_previous(
    centroid: np.ndarray, previous: list[TopicCluster]
) -> tuple[TopicCluster | None, float]:
    """Nearest previous-period cluster above the similarity threshold."""
    best: TopicCluster | None = None
    best_score = 0.0
    for candidate in previous:
        if not candidate.centroid:
            continue
        other = np.asarray(candidate.centroid, dtype=np.float32)
        denominator = np.linalg.norm(centroid) * np.linalg.norm(other)
        if denominator == 0:
            continue
        score = float(np.dot(centroid, other) / denominator)
        if score > best_score:
            best, best_score = candidate, score
    if best_score >= settings.topic_match_threshold:
        return best, best_score
    return None, best_score


def classify_trend(query_count: int, previous_count: int, growth: float) -> str:
    """Three states, as specified in F4.

    Emerging is the one that earns its keep. A topic can be trivially small in
    absolute terms and still be the most important thing in the archive, because
    it is growing fast from nothing. Volume ranking alone buries exactly that
    case, which is the finding the emerging-issue literature is built on.
    """
    if previous_count == 0:
        return "emerging" if query_count >= settings.hdbscan_min_cluster_size else "stable"
    if growth >= settings.emerging_growth_threshold and previous_count <= settings.emerging_max_previous:
        return "emerging"
    if query_count >= previous_count * 0.7:
        return "recurring"
    return "stable"


def compute_growth(current: int, previous: int) -> float:
    if previous == 0:
        return float(current)  # new topic: growth is its whole volume
    return round((current - previous) / previous, 4)


def priority_score(
    volume_norm: float, growth: float, mean_confidence: float, severity: float
) -> float:
    # Growth is unbounded upward, so squash it before weighting. A topic that
    # tripled and one that grew tenfold are both "rising fast"; the difference
    # between them should not dominate the whole score.
    growth_norm = min(1.0, max(0.0, growth) / 3.0)
    score = (
        settings.w_volume * volume_norm
        + settings.w_growth * growth_norm
        + settings.w_confidence * (1.0 - mean_confidence)
        + settings.w_severity * severity
    )
    return round(min(1.0, max(0.0, score)), 4)
