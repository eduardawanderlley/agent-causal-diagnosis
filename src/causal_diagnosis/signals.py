"""Span-level anomaly signals.

Each detector inspects one step and returns the evidence it found. Weights are
deliberately simple and are documented in docs/methodology.md. The detectors
encode domain knowledge about this agent's tools, so they are the part you
would replace or extend for a different system.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from .graph import Step, TraceGraph

_WINDOW = re.compile(r"Return window:\s*(\d+)\s*days")
IDENTIFIER_ARGS = ("order_id",)
STALE_AFTER_DAYS = 365


@dataclass(frozen=True)
class Signal:
    name: str
    weight: int
    fix: str  # name of the counterfactual correction to try for this signal


def detect(step: Step, graph: TraceGraph, reference_date: date) -> list[Signal]:
    if step.kind == "tool":
        return _tool_signals(step, reference_date)
    return _decision_signals(step, graph)


def _tool_signals(step: Step, reference_date: date) -> list[Signal]:
    signals: list[Signal] = []
    result = step.result or {}

    if step.tool == "lookup_order":
        data = result.get("data") or {}
        if result.get("status") == "error":
            signals.append(Signal("explicit_tool_error", 1, "refetch_order"))
        elif "error" in data:
            signals.append(Signal("silent_tool_error", 3, "refetch_order"))

    if step.tool == "search_policy":
        for doc in result.get("documents", []):
            age_days = (reference_date - date.fromisoformat(doc["updated_at"])).days
            if age_days > STALE_AFTER_DAYS:
                signals.append(Signal("stale_document", 3, "refresh_policy_index"))
                break
        if _window_days(result.get("context")) is None:
            signals.append(Signal("missing_policy_terms", 2, "refresh_policy_index"))

    return signals


def _decision_signals(step: Step, graph: TraceGraph) -> list[Signal]:
    signals: list[Signal] = []
    action = step.action or {}
    upstream = graph.upstream_tools(step.key)

    if action.get("kind") == "tool":
        evidence = [graph.question] + [json.dumps(tool.result, sort_keys=True) for tool in upstream]
        for arg in IDENTIFIER_ARGS:
            value = (action.get("args") or {}).get(arg)
            if value is not None and not any(str(value) in text for text in evidence):
                signals.append(Signal("ungrounded_identifier", 3, "ground_identifier_args"))

    if action.get("kind") == "final" and action.get("verdict") in ("eligible", "not_eligible"):
        if _skipped_deadline_step(upstream):
            signals.append(Signal("skipped_required_step", 3, "restore_deadline_step"))

    return signals


def _skipped_deadline_step(upstream: list[Step]) -> bool:
    """A verdict was given although the policy window was known and the deadline was never calculated."""
    policy_steps = [tool for tool in upstream if tool.tool == "search_policy"]
    if not policy_steps:
        return False
    window_known = _window_days(policy_steps[-1].result.get("context")) is not None
    deadline_calculated = any(tool.tool == "calculate_deadline" for tool in upstream)
    return window_known and not deadline_calculated


def _window_days(context: str | None) -> int | None:
    match = _WINDOW.search(context or "")
    return int(match.group(1)) if match else None
