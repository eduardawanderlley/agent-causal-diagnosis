"""Rule-based planner.

It plays the role of the LLM decision step. Given the question and what the
agent has observed so far, it returns exactly one action: call a tool or give
the final answer. Keeping it rule-based makes every experiment deterministic
and free to run. The interface is the one an LLM-backed planner would implement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .fixtures import days_since

BASELINE_PROMPT_VERSION = "v1"
DRIFT_WINDOW_DAYS = 15  # the fixed window a drifted prompt falls back to

_ORDER_ID = re.compile(r"PED-\d{4}")
_WINDOW = re.compile(r"Return window:\s*(\d+)\s*days")


@dataclass(frozen=True)
class Action:
    kind: str  # "tool" or "final"
    name: str | None = None
    args: dict = field(default_factory=dict)
    verdict: str | None = None

    @classmethod
    def tool(cls, name: str, **args) -> "Action":
        return cls(kind="tool", name=name, args=args)

    @classmethod
    def final(cls, verdict: str) -> "Action":
        return cls(kind="final", verdict=verdict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name, "args": self.args, "verdict": self.verdict}


@dataclass(frozen=True)
class Observation:
    key: str
    tool: str
    args: dict
    result: dict


def extract_order_id(text: str) -> str | None:
    match = _ORDER_ID.search(text)
    return match.group(0) if match else None


def parse_window_days(context: str | None) -> int | None:
    match = _WINDOW.search(context or "")
    return int(match.group(1)) if match else None


def latest(observations, tool: str) -> Observation | None:
    for observation in reversed(observations):
        if observation.tool == tool:
            return observation
    return None


def decide(question: str, observations, prompt_version: str = BASELINE_PROMPT_VERSION) -> Action:
    lookup = latest(observations, "lookup_order")
    if lookup is None:
        order_id = extract_order_id(question)
        if order_id is None:
            return _escalate(observations, "no order id in the message")
        return Action.tool("lookup_order", order_id=order_id)

    data = lookup.result.get("data") if lookup.result.get("status") == "ok" else None
    order = data or {}
    if not order.get("delivered_at"):
        return _escalate(observations, "order has no delivery date")

    search = latest(observations, "search_policy")
    if search is None:
        return Action.tool("search_policy", query=f"{order['category']} return policy")

    window = parse_window_days(search.result.get("context"))
    if window is None:
        return _escalate(observations, "return window not found in policy text")

    deadline = latest(observations, "calculate_deadline")
    if deadline is not None:
        return Action.final("eligible" if deadline.result["eligible"] else "not_eligible")

    if prompt_version == BASELINE_PROMPT_VERSION:
        return Action.tool("calculate_deadline", delivered_at=order["delivered_at"], window_days=window)

    # A drifted prompt skips the deadline calculator and reasons with a fixed window.
    within = days_since(order["delivered_at"]) <= DRIFT_WINDOW_DAYS
    return Action.final("eligible" if within else "not_eligible")


def _escalate(observations, reason: str) -> Action:
    if latest(observations, "open_ticket") is None:
        return Action.tool("open_ticket", summary=f"Escalated to a human agent: {reason}")
    return Action.final("escalated")
