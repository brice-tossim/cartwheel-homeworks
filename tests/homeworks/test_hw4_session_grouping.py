"""Grouping tests for the Homework 4 review: one conversation per Langfuse session.

Cartwheel records one trace per customer message, so a two-turn conversation
is two traces sharing a session. The same scenario can also be run several
times, each run in its own session. group_by_session must keep every trace
intact, put the turns of one conversation together, and never glue separate
runs into one. Everything runs offline.
"""

from __future__ import annotations

import copy

from analysis.helpers.normalization import group_by_session, normalize_trace


def _turn(
    trace_id: str,
    said: str,
    started: str,
    *,
    session: str | None,
    scenario: str = "support-0001",
) -> dict[str, object]:
    """One normalized trace holding a single customer message."""
    return normalize_trace(
        {
            "id": trace_id,
            "input": said,
            "timestamp": started,
            "sessionId": session,
            "cartwheel_scenario_id": scenario,
        }
    )


def _trace_ids(groups: list[dict[str, object]]) -> list[list[object]]:
    return [[trace["id"] for trace in group["traces"]] for group in groups]


def test_turns_of_one_conversation_are_grouped_oldest_first() -> None:
    follow_up = _turn("t2", "And order 13?", "2026-10-07T02:10:00.000Z", session="s1")
    opening = _turn("t1", "Where is order 12?", "2026-10-07T02:07:00.000Z", session="s1")

    groups = group_by_session([follow_up, opening])

    assert [group["session_id"] for group in groups] == ["s1"]
    assert _trace_ids(groups) == [["t1", "t2"]]


def test_each_turn_keeps_its_own_steps() -> None:
    opening = _turn("t1", "Where is order 12?", "2026-10-07T02:07:00.000Z", session="s1")
    follow_up = _turn("t2", "And order 13?", "2026-10-07T02:10:00.000Z", session="s1")
    before = copy.deepcopy([opening, follow_up])

    groups = group_by_session([opening, follow_up])

    assert [trace["trace"] for trace in groups[0]["traces"]] == [
        [{"role": "user", "text": "Where is order 12?"}],
        [{"role": "user", "text": "And order 13?"}],
    ]
    assert [opening, follow_up] == before


def test_repeated_runs_of_one_scenario_stay_separate_conversations() -> None:
    first_run = _turn("t1", "Where is order 12?", "2026-10-07T02:07:00.000Z", session="s1")
    second_run = _turn("t2", "Where is order 12?", "2026-10-07T02:30:00.000Z", session="s2")

    groups = group_by_session([first_run, second_run])

    assert [group["session_id"] for group in groups] == ["s1", "s2"]
    assert _trace_ids(groups) == [["t1"], ["t2"]]


def test_trace_without_a_session_is_its_own_conversation() -> None:
    one = _turn("t1", "Where is order 12?", "2026-10-07T02:07:00.000Z", session=None)
    other = _turn("t2", "Cancel order 13.", "2026-10-07T02:08:00.000Z", session=None)

    groups = group_by_session([one, other])

    assert [group["session_id"] for group in groups] == ["t1", "t2"]
    assert _trace_ids(groups) == [["t1"], ["t2"]]


def test_conversations_are_ordered_by_when_they_started() -> None:
    later = _turn("t1", "Cancel order 13.", "2026-10-07T03:00:00.000Z", session="s-later")
    earlier = _turn("t2", "Where is order 12?", "2026-10-07T02:00:00.000Z", session="s-earlier")

    groups = group_by_session([later, earlier])

    assert [group["session_id"] for group in groups] == ["s-earlier", "s-later"]
