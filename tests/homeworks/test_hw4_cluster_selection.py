"""Tests for the cluster strategy of select_traces.

The strategy groups the traces into k clusters by their shape and returns the
most typical trace of each: the one closest to its cluster's centre.
"""

from __future__ import annotations

from analysis.helpers import selection


def _trace(trace_id: str, tool_calls: int) -> dict[str, object]:
    return {"id": trace_id, "features": {"tool_call_count": tool_calls}}


# Two clear groups: few tool calls and many tool calls.
TRACES = [
    _trace("few-0", 0),
    _trace("few-1", 1),
    _trace("few-2", 2),
    _trace("many-0", 20),
    _trace("many-1", 21),
    _trace("many-2", 22),
]


def _picked(picks: list[dict[str, str]]) -> set[str]:
    return {pick["trace_id"] for pick in picks}


def test_each_cluster_gives_its_most_typical_trace() -> None:
    picks = selection.select(TRACES, k=2, strategy="cluster", exclude_ids=set())

    assert _picked(picks) == {"few-1", "many-1"}


def test_each_pick_names_its_cluster_and_size() -> None:
    picks = selection.select(TRACES, k=2, strategy="cluster", exclude_ids=set())

    assert sorted(pick["reason"] for pick in picks) == [
        "representative of cluster 1 of 2 (3 traces)",
        "representative of cluster 2 of 2 (3 traces)",
    ]


def test_excluded_traces_are_neither_clustered_nor_picked() -> None:
    picks = selection.select(TRACES, k=2, strategy="cluster", exclude_ids={"few-1", "many-1"})

    assert _picked(picks) & {"few-1", "many-1"} == set()
    assert len(picks) == 2


def test_the_same_traces_give_the_same_picks() -> None:
    first = selection.select(TRACES, k=2, strategy="cluster", exclude_ids=set())
    second = selection.select(TRACES, k=2, strategy="cluster", exclude_ids=set())

    assert first == second
