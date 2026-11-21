"""Causal localization.

Given the spans of one run that produced a wrong answer, rank the steps that
could be the root cause. The structural heuristic scores every step upstream
of the answer by the anomaly signals it shows. Counterfactual replay then
checks the top candidates and promotes the ones whose correction fixes the
answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .counterfactual import confirm
from .graph import TraceGraph
from .signals import detect


@dataclass
class Candidate:
    key: str
    score: int
    evidence: list[str]
    fix: str
    confirmed: bool | None = None


@dataclass(frozen=True)
class Diagnosis:
    verdict: str | None
    heuristic_ranking: list[str]
    ranking: list[str]
    candidates: list[Candidate]
    replays: int


def heuristic_candidates(graph: TraceGraph, reference_date: date) -> list[Candidate]:
    final = graph.final_step()
    if final is None:
        return []
    scope = graph.ancestors(final.key) | {final.key}
    found = []
    for key in scope:
        signals = detect(graph.steps[key], graph, reference_date)
        if not signals:
            continue
        strongest = max(signals, key=lambda signal: signal.weight)
        found.append(
            Candidate(
                key=key,
                score=sum(signal.weight for signal in signals),
                evidence=[signal.name for signal in signals],
                fix=strongest.fix,
            )
        )
    return sorted(found, key=lambda c: (-c.score, graph.steps[c.key].order))


def _complete(candidates: list[Candidate], graph: TraceGraph) -> list[str]:
    ranked = [c.key for c in candidates]
    return ranked + [key for key in graph.ordered_keys() if key not in ranked]


def diagnose(spans, *, reference_date: date, replay=None, accept=None, top_k: int = 3) -> Diagnosis:
    """Localize the root cause of a failed run from its spans.

    Pass replay and accept to enable counterfactual confirmation. Without them
    the result is the structural heuristic alone.
    """
    graph = TraceGraph(spans)
    final = graph.final_step()
    if final is None:
        return Diagnosis(verdict=None, heuristic_ranking=[], ranking=[], candidates=[], replays=0)

    candidates = heuristic_candidates(graph, reference_date)
    heuristic = _complete(candidates, graph)

    replays = 0
    if replay is not None and accept is not None and candidates:
        candidates, replays = confirm(candidates, replay, accept, top_k=top_k)

    return Diagnosis(
        verdict=final.verdict,
        heuristic_ranking=heuristic,
        ranking=_complete(candidates, graph),
        candidates=candidates,
        replays=replays,
    )


def baseline_rankings(spans) -> dict[str, list[str]]:
    """Two naive baselines to compare against.

    first_visible_error: the earliest step whose tool reported status=error.
    last_before_final:   the steps nearest the answer, read backwards.
    """
    graph = TraceGraph(spans)
    ordered = graph.ordered_keys()
    final = graph.final_step()

    visible = [k for k in ordered if _reports_error(graph.steps[k])]
    first_visible = visible + [k for k in ordered if k not in visible]

    prior = [k for k in reversed(ordered) if final is None or k != final.key]
    if final is not None:
        prior.append(final.key)
    return {"first_visible_error": first_visible, "last_before_final": prior}


def _reports_error(step) -> bool:
    return step.kind == "tool" and (step.result or {}).get("status") == "error"
