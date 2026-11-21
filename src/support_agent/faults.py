"""Controlled fault injection.

Faults are applied at the boundary between the agent and its environment: on
the action the planner chose, and on tool outputs. Tools and planner stay clean,
and the diagnosis layer never sees which fault was active. Each fault has a
known root-cause step, which is the ground truth the benchmark scores against.
"""

from __future__ import annotations

from .planner import BASELINE_PROMPT_VERSION, Action

FAULTS = (
    "none",
    "stale_document",
    "silent_tool_error",
    "extraction_corruption",
    "context_truncation",
    "prompt_drift",
)

# The step where each fault originates, not the step where it becomes visible.
ROOT_CAUSE_KEY = {
    "stale_document": "1.tool",
    "silent_tool_error": "0.tool",
    "extraction_corruption": "0.decision",
    "context_truncation": "1.tool",
    "prompt_drift": "2.decision",
}

DRIFTED_PROMPT_VERSION = "v2-drift"
TRUNCATE_TO_CHARS = 18
STALE_WINDOW_DAYS = 7
STALE_UPDATED_AT = "2019-03-01"


def prompt_version_for(fault: str, deployed: str = BASELINE_PROMPT_VERSION) -> str:
    if fault == "prompt_drift":
        return DRIFTED_PROMPT_VERSION
    return deployed


def apply_decision_fault(fault: str, action: Action) -> Action:
    if fault == "extraction_corruption" and action.kind == "tool" and action.name == "lookup_order":
        corrupted = _swap_last_digits(action.args["order_id"])
        return Action.tool("lookup_order", order_id=corrupted)
    return action


def apply_tool_fault(fault: str, tool: str, result: dict) -> dict:
    if fault == "silent_tool_error" and tool == "lookup_order" and result.get("status") == "ok":
        # Reports success, but the payload is an error. Nothing upstream flags it.
        return {"status": "ok", "data": {"error": "upstream_timeout"}}
    if fault == "stale_document" and tool == "search_policy":
        return _with_documents([_stale(doc) for doc in result["documents"]])
    if fault == "context_truncation" and tool == "search_policy":
        truncated = [{**doc, "text": doc["text"][:TRUNCATE_TO_CHARS]} for doc in result["documents"]]
        return _with_documents(truncated)
    return result


def _swap_last_digits(order_id: str) -> str:
    return order_id[:-2] + order_id[-1] + order_id[-2]


def _stale(doc: dict) -> dict:
    return {
        **doc,
        "text": f"Return window: {STALE_WINDOW_DAYS} days from delivery.",
        "updated_at": STALE_UPDATED_AT,
    }


def _with_documents(documents: list[dict]) -> dict:
    return {
        "status": "ok",
        "documents": documents,
        "context": " ".join(doc["text"] for doc in documents),
    }
