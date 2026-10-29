"""Tests for the AI suggestions the reviewer accepts or rejects.

analysis/review_app/suggestions.py reads analysis/state/suggestions.json, where
an agent leaves suggested notes. Accepting one turns it into the reviewer's own
note; rejecting one records the decision. Either way the suggestion stays in
the file with what was decided. Each test points the state folder at a
temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.review_app import suggestions

SUGGESTED = {
    "id": "s1",
    "trace_id": "t2",
    "quote": "Older Clover Field Naturals order: Order #925",
    "note": "the reply names an order no tool returned",
}


@pytest.fixture(autouse=True)
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(tmp_path))
    return tmp_path


def _write(state_dir: Path, entries: list[dict[str, object]]) -> None:
    (state_dir / "suggestions.json").write_text(json.dumps(entries))


def _saved_suggestions(state_dir: Path) -> list[dict[str, object]]:
    return json.loads((state_dir / "suggestions.json").read_text())


def _saved_notes(state_dir: Path) -> list[dict[str, object]]:
    path = state_dir / "annotations.json"
    return json.loads(path.read_text())["annotations"] if path.exists() else []


def test_suggestions_are_pending_until_decided(state_dir: Path) -> None:
    _write(state_dir, [SUGGESTED, {"id": "s2", "trace_id": "t1", "quote": "x", "status": "rejected"}])

    assert [(entry["id"], entry["status"]) for entry in suggestions.list_suggestions()] == [
        ("s1", "pending"),
        ("s2", "rejected"),
    ]


def test_accepting_a_suggestion_turns_it_into_a_note(state_dir: Path) -> None:
    _write(state_dir, [SUGGESTED])

    suggestions.accept_suggestion("s1")

    (note,) = _saved_notes(state_dir)
    (saved,) = _saved_suggestions(state_dir)
    assert (note["trace_id"], note["quote"], note["note"]) == (
        "t2",
        "Older Clover Field Naturals order: Order #925",
        "the reply names an order no tool returned",
    )
    assert (saved["status"], saved["note_id"]) == ("accepted", note["id"])


def test_rejecting_a_suggestion_records_it_without_a_note(state_dir: Path) -> None:
    _write(state_dir, [SUGGESTED])

    suggestions.reject_suggestion("s1")

    assert _saved_notes(state_dir) == []
    assert _saved_suggestions(state_dir)[0]["status"] == "rejected"


def test_a_decided_suggestion_keeps_its_first_decision(state_dir: Path) -> None:
    _write(state_dir, [SUGGESTED])

    suggestions.accept_suggestion("s1")
    suggestions.accept_suggestion("s1")
    suggestions.reject_suggestion("s1")

    assert len(_saved_notes(state_dir)) == 1
    assert _saved_suggestions(state_dir)[0]["status"] == "accepted"


def test_a_suggestion_naming_only_a_failure_mode_becomes_a_note_with_that_name(state_dir: Path) -> None:
    _write(state_dir, [{"id": "s3", "trace_id": "t1", "mode": "unconfirmed_write", "quote": "Done"}])

    suggestions.accept_suggestion("s3")

    assert _saved_notes(state_dir)[0]["note"] == "unconfirmed_write"


def test_an_unknown_suggestion_cannot_be_decided(state_dir: Path) -> None:
    _write(state_dir, [SUGGESTED])

    with pytest.raises(KeyError):
        suggestions.reject_suggestion("missing")
