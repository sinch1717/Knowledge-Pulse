"""Metric definitions. Pure functions, no I/O, so they can be unit-tested and
quoted in the paper exactly as implemented.

Relevance. A question is generated from a gold passage of 40-120 words. A
retrieved chunk is *relevant* when either

  - it contains at least half of the gold passage (by word 3-grams), or
  - at least 70% of the chunk lies inside the gold passage.

The second clause keeps the rule fair to small chunk sizes: a 60-word chunk can
never contain half of a 120-word passage, but if it sits almost entirely inside
it, it is answer text. Judging on 3-gram overlap rather than chunk ids is what
makes chunkers comparable at all: each cuts the page differently, so there is no
shared chunk id, but the gold passage is the same text for every one of them.
"""

from __future__ import annotations

import re

import numpy as np

RELEVANCE_THRESHOLD = 0.5  # share of the gold passage inside the chunk
CONTAINMENT_THRESHOLD = 0.7  # share of the chunk inside the gold passage
MIN_CONTAINED_SHINGLES = 10  # so a 12-word fragment cannot qualify on its own
_TOKEN = re.compile(r"\w+")


def shingles(text: str, n: int = 3) -> set[tuple[str, ...]]:
    tokens = _TOKEN.findall(text.lower())
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def coverage(gold: set, chunk: set) -> float:
    """Share of the gold passage that appears in the chunk."""
    return len(gold & chunk) / len(gold) if gold else 0.0


def is_relevant(gold: set, chunk: set) -> bool:
    if coverage(gold, chunk) >= RELEVANCE_THRESHOLD:
        return True
    inside = len(gold & chunk)
    return inside >= MIN_CONTAINED_SHINGLES and inside / len(chunk) >= CONTAINMENT_THRESHOLD if chunk else False


def retrieval_scores(gold: set, gold_url: str, ranked: list[tuple[set, str, int]], k: int) -> dict:
    """ranked: (chunk shingles, chunk url, chunk word count), best first.

    hit@1, hit@k   a relevant chunk is ranked first / in the top k
    rr             reciprocal rank of the first relevant chunk in the top 10
    recall@k       share of the gold passage covered by the union of the top k,
                   which rewards retrieving a passage that a chunker split in two
    page_hit@k     any of the top k comes from the gold page (a looser signal)
    context_words  words handed to the generator from the top k: the cost side
    """
    relevant = [is_relevant(gold, sh) for sh, _, _ in ranked]
    first = next((i for i, r in enumerate(relevant[:10]) if r), None)
    union: set = set()
    for sh, _, _ in ranked[:k]:
        union |= sh
    return {
        "hit1": float(bool(relevant[:1] and relevant[0])),
        "hitk": float(any(relevant[:k])),
        "rr": 1.0 / (first + 1) if first is not None else 0.0,
        "recallk": coverage(gold, union),
        "page_hitk": float(any(url == gold_url for _, url, _ in ranked[:k])),
        "context_words": float(sum(w for _, _, w in ranked[:k])),
    }


def auroc(positive: list[float], negative: list[float]) -> float | None:
    """Probability a random answerable question outscores a random unanswerable one."""
    if not positive or not negative:
        return None
    scores = np.array(positive + negative)
    order = scores.argsort()
    ranks = np.empty(len(scores))
    # Average ranks for ties.
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = ranks[: len(positive)].sum()
    n_pos, n_neg = len(positive), len(negative)
    return float((rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def gap_rates(positive: list[float], negative: list[float], tau: float) -> dict:
    """At threshold tau, a question below tau is flagged as a knowledge gap.

    false_gap   answerable questions wrongly flagged (noise in the gap report)
    missed_gap  unanswerable questions not flagged (gaps the report would miss)
    """
    fg = float(np.mean([p < tau for p in positive])) if positive else None
    mg = float(np.mean([n >= tau for n in negative])) if negative else None
    balanced = None if fg is None or mg is None else 1 - (fg + mg) / 2
    return {"false_gap": fg, "missed_gap": mg, "balanced_accuracy": balanced}


def best_threshold(positive: list[float], negative: list[float]) -> float | None:
    """Threshold maximising balanced accuracy (Youden's J) on this data."""
    if not positive or not negative:
        return None
    candidates = sorted(set(positive + negative))
    best, best_score = candidates[0], -1.0
    for t in candidates:
        score = gap_rates(positive, negative, t)["balanced_accuracy"] or 0
        if score > best_score:
            best, best_score = t, score
    return float(best)


def paired_bootstrap(a: list[float], b: list[float], resamples: int = 2000, seed: int = 13) -> dict:
    """Mean of (a - b) over the same questions, with a 95% percentile interval."""
    diffs = np.array(a) - np.array(b)
    if len(diffs) == 0:
        return {"mean_diff": None, "ci_low": None, "ci_high": None, "significant": False}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diffs), size=(resamples, len(diffs)))
    means = diffs[idx].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return {
        "mean_diff": float(diffs.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "significant": bool(low > 0 or high < 0),
    }


def distribution(values: list[int]) -> dict:
    if not values:
        return {"mean": 0, "median": 0, "p10": 0, "p90": 0}
    arr = np.array(values)
    return {
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
    }
