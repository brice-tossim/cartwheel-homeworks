"""Tests for the by_role strategy of select_traces.

The strategy spreads k conversations evenly across the caller roles and picks
whole conversations, so every turn of a picked conversation is returned.
"""

from __future__ import annotations

from collections import Counter

from analysis.helpers import selection


def _trace(trace_id: str, role: str, session: str) -> dict[str, object]:
    return {"id": trace_id, "meta": {"role": role, "session_id": session}, "features": {}}


TRACES = [
    *[_trace(f"shopper-{i}", "shopper", f"s-shopper-{i}") for i in range(6)],
    *[_trace(f"merchant-{i}", "merchant", f"s-merchant-{i}") for i in range(3)],
    _trace("merchant-0-turn-2", "merchant", "s-merchant-0"),
]


def _picked(picks: list[dict[str, str]]) -> set[str]:
    return {pick["trace_id"] for pick in picks}


def _roles(picks: list[dict[str, str]]) -> Counter[str]:
    sessions = {pick["trace_id"].removesuffix("-turn-2") for pick in picks}
    return Counter(trace_id.split("-")[0] for trace_id in sessions)


def test_conversations_are_spread_evenly_across_roles() -> None:
    picks = selection.select(TRACES, k=4, strategy="by_role", exclude_ids=set())

    assert _roles(picks) == Counter({"shopper": 2, "merchant": 2})


def test_a_picked_conversation_brings_all_its_turns() -> None:
    picks = selection.select(TRACES, k=6, strategy="by_role", exclude_ids=set())

    assert {"merchant-0", "merchant-0-turn-2"} <= _picked(picks)


def test_a_conversation_with_an_excluded_turn_is_not_picked() -> None:
    picks = selection.select(TRACES, k=6, strategy="by_role", exclude_ids={"merchant-0"})

    assert _picked(picks) & {"merchant-0", "merchant-0-turn-2"} == set()


def test_each_pick_names_its_role() -> None:
    picks = selection.select(TRACES, k=2, strategy="by_role", exclude_ids=set())

    assert sorted(pick["reason"] for pick in picks) == [
        "role merchant, conversation 1 of 1",
        "role shopper, conversation 1 of 1",
    ]


def test_the_same_traces_give_the_same_picks() -> None:
    first = selection.select(TRACES, k=4, strategy="by_role", exclude_ids=set())
    second = selection.select(TRACES, k=4, strategy="by_role", exclude_ids=set())

    assert first == second
