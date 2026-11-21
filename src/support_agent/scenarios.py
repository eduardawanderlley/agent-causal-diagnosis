"""Scenario suite: every combination of fault, order and phrasing.

With 6 fault settings, 7 orders and 5 phrasings the suite has 210 runs. Each
run carries its expected answer and, for faulted runs, the ground-truth root
cause step. Add orders or phrasings here to grow the suite.
"""

from __future__ import annotations

from dataclasses import dataclass

from .faults import FAULTS, ROOT_CAUSE_KEY
from .fixtures import ORDERS, expected_verdict

TEMPLATES = (
    "I want to return order {order_id}. Am I still within the return window?",
    "Can I still get a refund for order {order_id}?",
    "Order {order_id} arrived damaged. What are my options?",
    "Hi, is {order_id} still eligible for a return?",
    "What is the return deadline for my order {order_id}?",
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    question: str
    fault: str
    expected_verdict: str
    root_cause_key: str | None


def build_scenarios() -> list[Scenario]:
    scenarios = []
    for fault in FAULTS:
        for order_id in ORDERS:
            for number, template in enumerate(TEMPLATES):
                scenarios.append(
                    Scenario(
                        scenario_id=f"{fault}/{order_id}/t{number}",
                        question=template.format(order_id=order_id),
                        fault=fault,
                        expected_verdict=expected_verdict(order_id),
                        root_cause_key=ROOT_CAUSE_KEY.get(fault),
                    )
                )
    return scenarios
