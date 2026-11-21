"""Counterfactual confirmation.

A candidate root cause is accepted only if replacing its step with the
suggested correction, and re-running the same input, produces a correct final
answer. The replay function and the acceptance check come from the caller, so
this module does not depend on any particular agent.

In production the acceptance check is usually a deterministic verifier that
recomputes the answer from source-of-truth data, or a human-labelled expectation.
"""

from __future__ import annotations

from collections.abc import Callable


def confirm(candidates, replay: Callable[[str, str], str], accept: Callable[[str], bool], top_k: int = 3):
    """Replay the top candidates and move confirmed ones to the front.

    Returns the reordered candidate list and the number of replays executed.
    Candidates outside the top k keep their heuristic order and stay unconfirmed.
    """
    head, tail = candidates[:top_k], candidates[top_k:]
    replays = 0
    for candidate in head:
        verdict = replay(candidate.key, candidate.fix)
        replays += 1
        candidate.confirmed = bool(accept(verdict))
    reordered = [c for c in head if c.confirmed] + [c for c in head if not c.confirmed] + tail
    return reordered, replays
