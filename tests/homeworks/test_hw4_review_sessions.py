"""Tests for the conversations the Homework 4 review app loads.

analysis/review_app/sessions.py reads the traces live from Langfuse, falls
back to the local export when Langfuse cannot be reached, keeps only the
support scenarios, and groups the traces into conversations. Everything runs
offline: Langfuse is stood in for by a plain function.
"""

from __future__ import annotations

import json
from pathlib import Path

from analysis.helpers.normalization import TraceRecord, normalize_trace
from analysis.review_app.sessions import load_sessions
from tests.homeworks.hw4_observations import observation


def _trace(
    trace_id: str, scenario: str, session: str, said: str, started: str
) -> TraceRecord:
    return normalize_trace(
        {
            "id": trace_id,
            "input": said,
            "timestamp": started,
            "sessionId": session,
            "cartwheel_scenario_id": scenario,
        }
    )


def _session_trace_ids(loaded: dict[str, object]) -> list[list[object]]:
    sessions = loaded["sessions"]
    assert isinstance(sessions, list)
    return [[trace["id"] for trace in session["traces"]] for session in sessions]


def _export_with_one_trace(path: Path) -> Path:
    """A local export holding one trace, in the shape export_langfuse.py writes."""
    root = observation(
        "root",
        "SPAN",
        "cartwheel.session_message",
        "2026-10-07T02:00:00.000Z",
        trace_id="t9",
        session_id="s9",
        payload_in=[{"role": "user", "parts": [{"type": "text", "content": "Cancel order 13."}]}],
        attributes={"cartwheel.scenario_id": "support-0009"},
        root=True,
    )
    record = {
        "id": "t9",
        "traceId": "t9",
        "cartwheel_scenario_id": "support-0009",
        "timestamp": "2026-10-07T02:00:00.000Z",
        "observations": [root],
    }
    path.write_text(json.dumps({"traces": [record]}))
    return path


def _langfuse_unreachable() -> list[TraceRecord]:
    raise ConnectionError("Langfuse refused the connection")


def test_conversations_come_from_langfuse_when_it_answers(tmp_path: Path) -> None:
    opening = _trace("t1", "support-0001", "s1", "Where is order 12?", "2026-10-07T02:00:00Z")
    follow_up = _trace("t2", "support-0001", "s1", "And order 13?", "2026-10-07T02:05:00Z")

    loaded = load_sessions(
        fetch=lambda: [follow_up, opening], export_path=tmp_path / "unused.json"
    )

    assert loaded["source"] == "langfuse"
    assert loaded["fallback_reason"] is None
    assert _session_trace_ids(loaded) == [["t1", "t2"]]


def test_only_support_scenarios_are_reviewed(tmp_path: Path) -> None:
    traces = [
        _trace("t1", "support-0001", "s1", "Where is order 12?", "2026-10-07T02:00:00Z"),
        _trace("t2", "pilot-020", "s2", "Hello?", "2026-09-28T02:00:00Z"),
        _trace("t3", "probe-024-followup", "s3", "And now?", "2026-10-01T02:00:00Z"),
    ]

    loaded = load_sessions(fetch=lambda: traces, export_path=tmp_path / "unused.json")

    assert _session_trace_ids(loaded) == [["t1"]]


def test_the_export_is_used_when_langfuse_cannot_be_reached(tmp_path: Path) -> None:
    export = _export_with_one_trace(tmp_path / "support_traces.json")

    loaded = load_sessions(fetch=_langfuse_unreachable, export_path=export)

    assert loaded["source"] == "export"
    assert loaded["fallback_reason"] == "ConnectionError: Langfuse refused the connection"
    assert _session_trace_ids(loaded) == [["t9"]]
