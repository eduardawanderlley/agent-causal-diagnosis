"""Simulated business data: orders, return policies and a keyword retriever.

Everything here is deterministic. TODAY is pinned so that every run, benchmark
and test sees the same calendar, and expected answers never drift with the clock.
"""

from __future__ import annotations

import re
from datetime import date

TODAY = date(2026, 11, 20)

# PED-1003 is still in transit, so it has no delivery date and must be escalated.
ORDERS: dict[str, dict] = {
    "PED-1001": {"category": "electronics", "amount": 1899.90, "delivered_at": "2026-11-05"},
    "PED-1002": {"category": "apparel", "amount": 189.90, "delivered_at": "2026-10-01"},
    "PED-1003": {"category": "home", "amount": 320.00, "delivered_at": None},
    "PED-1004": {"category": "electronics", "amount": 449.00, "delivered_at": "2026-11-02"},
    "PED-1005": {"category": "apparel", "amount": 79.90, "delivered_at": "2026-11-17"},
    "PED-1006": {"category": "home", "amount": 240.00, "delivered_at": "2026-10-20"},
    "PED-1007": {"category": "electronics", "amount": 999.00, "delivered_at": "2026-10-25"},
}

RETURN_WINDOW_DAYS = {"electronics": 30, "apparel": 45, "home": 30}

POLICY_INDEX = [
    {
        "doc_id": f"policy/{category}",
        "category": category,
        "keywords": [category, "return", "refund", "policy"],
        "updated_at": "2026-08-01",
        "text": (
            f"Return window: {days} days from delivery. "
            "Items must be unused and in original packaging."
        ),
    }
    for category, days in RETURN_WINDOW_DAYS.items()
]


def days_since(iso_date: str, today: date = TODAY) -> int:
    return (today - date.fromisoformat(iso_date)).days


def expected_verdict(order_id: str) -> str:
    """Ground truth, computed directly from the source data and never from the agent."""
    order = ORDERS[order_id]
    if order["delivered_at"] is None:
        return "escalated"
    window = RETURN_WINDOW_DAYS[order["category"]]
    return "eligible" if days_since(order["delivered_at"]) <= window else "not_eligible"


def retrieve(query: str, k: int = 1) -> list[dict]:
    """Keyword-overlap retrieval over the policy index. Returns the k best matches."""
    tokens = set(re.findall(r"[a-z]+", query.lower()))
    scored = [(len(tokens & set(doc["keywords"])), doc) for doc in POLICY_INDEX]
    matches = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in matches[:k]]
