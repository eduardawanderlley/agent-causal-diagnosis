"""Known-good corrections used by counterfactual replay.

Each fix replaces one step's output with what a correct system would have
produced, using source-of-truth data. Diagnosis refers to fixes by name only,
so the diagnosis package never imports this module.

Every fix has the signature (output, context) -> new_output. For decision
steps the output is an Action, for tool steps it is the tool result.
"""

from __future__ import annotations

from .planner import Action, extract_order_id, latest, parse_window_days
from .tools import lookup_order, search_policy


def refetch_order(output, ctx):
    return lookup_order(ctx.args["order_id"])


def refresh_policy_index(output, ctx):
    return search_policy(ctx.args["query"])


def ground_identifier_args(output, ctx):
    if output.kind != "tool" or "order_id" not in output.args:
        return output
    order_id = extract_order_id(ctx.question)
    if order_id is None:
        return output
    return Action.tool(output.name, **{**output.args, "order_id": order_id})


def restore_deadline_step(output, ctx):
    if output.kind != "final":
        return output
    lookup = latest(ctx.observations, "lookup_order")
    search = latest(ctx.observations, "search_policy")
    if lookup is None or search is None:
        return output
    delivered_at = (lookup.result.get("data") or {}).get("delivered_at")
    window = parse_window_days(search.result.get("context"))
    if not delivered_at or window is None:
        return output
    return Action.tool("calculate_deadline", delivered_at=delivered_at, window_days=window)


FIXES = {
    "refetch_order": refetch_order,
    "refresh_policy_index": refresh_policy_index,
    "ground_identifier_args": ground_identifier_args,
    "restore_deadline_step": restore_deadline_step,
}
