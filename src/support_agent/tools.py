"""Tool implementations.

These are the clean, source-of-truth versions. Faults are applied at the agent
boundary, never inside these functions, so a counterfactual fix can call them
directly to obtain the correct output.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from .fixtures import ORDERS, TODAY, retrieve


def lookup_order(order_id: str) -> dict:
    order = ORDERS.get(order_id)
    if order is None:
        return {"status": "error", "error": "order_not_found", "order_id": order_id}
    return {"status": "ok", "data": {"order_id": order_id, **order}}


def search_policy(query: str) -> dict:
    documents = retrieve(query)
    return {
        "status": "ok",
        "documents": documents,
        "context": " ".join(doc["text"] for doc in documents),
    }


def calculate_deadline(delivered_at: str, window_days: int) -> dict:
    delivered = date.fromisoformat(delivered_at)
    deadline = delivered + timedelta(days=window_days)
    return {
        "status": "ok",
        "deadline": deadline.isoformat(),
        "eligible": TODAY <= deadline,
        "days_since_delivery": (TODAY - delivered).days,
    }


def open_ticket(summary: str) -> dict:
    digest = hashlib.sha1(summary.encode("utf-8")).hexdigest()[:6].upper()
    return {"status": "ok", "ticket_id": f"TCK-{digest}"}


TOOLS = {
    "lookup_order": lookup_order,
    "search_policy": search_policy,
    "calculate_deadline": calculate_deadline,
    "open_ticket": open_ticket,
}
