"""Turns exported spans into a causal graph of steps.

The graph is built only from what the spans record: step keys, the steps each
one depended on, tool arguments and results. Nothing here knows which fault
was injected, and nothing imports the agent that produced the spans.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    key: str
    index: int
    kind: str  # "decision" or "tool"
    depends_on: tuple[str, ...]
    tool: str | None = None
    args: dict = field(default_factory=dict)
    result: dict | None = None
    action: dict | None = None
    verdict: str | None = None
    prompt_version: str | None = None

    @property
    def order(self) -> tuple[int, int]:
        """Execution order: a decision always precedes the tool call it triggers."""
        return (self.index, 0 if self.kind == "decision" else 1)


def _load(attributes, name, default=None):
    raw = attributes.get(name)
    return json.loads(raw) if raw is not None else default


class TraceGraph:
    """The steps of one agent run and the data dependencies between them."""

    def __init__(self, spans):
        self.question = ""
        self.steps: dict[str, Step] = {}
        for span in spans:
            attributes = dict(span.attributes or {})
            if span.name == "support_agent.run":
                self.question = attributes.get("agent.question", "")
            key = attributes.get("agent.step.key")
            if key is None:
                continue
            self.steps[key] = Step(
                key=key,
                index=int(attributes["agent.step.index"]),
                kind=attributes["agent.step.kind"],
                depends_on=tuple(_load(attributes, "agent.depends_on", [])),
                tool=attributes.get("tool.name"),
                args=_load(attributes, "tool.args", {}),
                result=_load(attributes, "tool.result"),
                action=_load(attributes, "agent.decision.action"),
                verdict=attributes.get("agent.verdict"),
                prompt_version=attributes.get("prompt.version"),
            )

    def final_step(self) -> Step | None:
        finals = [step for step in self.steps.values() if step.verdict is not None]
        return max(finals, key=lambda step: step.index) if finals else None

    def ancestors(self, key: str) -> set[str]:
        """Every step the given step transitively depended on."""
        seen: set[str] = set()
        queue = deque([key])
        while queue:
            for parent in self.steps[queue.popleft()].depends_on:
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return seen

    def upstream_tools(self, key: str) -> list[Step]:
        return [self.steps[k] for k in self.steps[key].depends_on if self.steps[k].kind == "tool"]

    def ordered_keys(self) -> list[str]:
        return sorted(self.steps, key=lambda k: self.steps[k].order)
