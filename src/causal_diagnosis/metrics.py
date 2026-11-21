"""Ranking metrics for root-cause localization."""

from __future__ import annotations


def hit_at_k(rankings: list[list[str]], truths: list[str], k: int) -> float:
    """Share of cases where the true root cause appears in the top k."""
    if not truths:
        return 0.0
    hits = sum(1 for ranking, truth in zip(rankings, truths) if truth in ranking[:k])
    return hits / len(truths)


def mean_reciprocal_rank(rankings: list[list[str]], truths: list[str]) -> float:
    """Average of 1/rank of the true root cause; 0 when it is missing."""
    if not truths:
        return 0.0
    total = 0.0
    for ranking, truth in zip(rankings, truths):
        if truth in ranking:
            total += 1.0 / (ranking.index(truth) + 1)
    return total / len(truths)
