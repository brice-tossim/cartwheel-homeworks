"""Tests for the free-text notes taken during the Homework 4 first reading.

analysis/review_app/notes.py keeps the notes in analysis/state/annotations.json.
An edited note keeps its earlier wording and a removed note stays in the file,
so the path from a first note to a failure mode can still be inspected. Each
test points the state folder at a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.review_app import notes


@pytest.fixture(autouse=True)
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(tmp_path))
    return tmp_path


def _saved(state_dir: Path) -> list[dict[str, object]]:
    return json.loads((state_dir / "annotations.json").read_text())["annotations"]


def test_a_note_is_saved_against_the_text_it_quotes(state_dir: Path) -> None:
    note = notes.add_note(
        "t1", "the reply claims the refund is done", quote="Your refund is processed", step=4
    )

    saved = _saved(state_dir)

    assert [
        {key: entry[key] for key in ("id", "trace_id", "kind", "quote", "step", "note", "history")}
        for entry in saved
    ] == [
        {
            "id": note["id"],
            "trace_id": "t1",
            "kind": "note",
            "quote": "Your refund is processed",
            "step": 4,
            "note": "the reply claims the refund is done",
            "history": [],
        }
    ]
    assert saved[0]["removed_ts"] is None


def test_editing_a_note_keeps_its_first_wording(state_dir: Path) -> None:
    note = notes.add_note("t1", "refund wrong")

    notes.edit_note(note["id"], "the reply claims the refund is done; the tool only queued it")

    saved = _saved(state_dir)[0]
    assert saved["note"] == "the reply claims the refund is done; the tool only queued it"
    assert [version["note"] for version in saved["history"]] == ["refund wrong"]


def test_a_removed_note_stays_in_the_saved_file(state_dir: Path) -> None:
    note = notes.add_note("t1", "refund wrong")

    notes.remove_note(note["id"])

    saved = _saved(state_dir)
    assert [entry["note"] for entry in saved] == ["refund wrong"]
    assert saved[0]["removed_ts"] is not None


def test_no_failure_observed_is_recorded_once_per_trace(state_dir: Path) -> None:
    notes.mark_no_failure("t1")
    notes.mark_no_failure("t1")

    assert [
        (entry["trace_id"], entry["kind"], entry["note"]) for entry in _saved(state_dir)
    ] == [("t1", "no_failure", "no failure observed")]


def test_an_unknown_note_cannot_be_edited() -> None:
    with pytest.raises(KeyError):
        notes.edit_note("missing", "the reply claims the refund is done")


def test_notes_saved_earlier_are_kept(state_dir: Path) -> None:
    earlier = {"id": "old", "trace_id": "T1", "note": "an earlier note", "ts": "2026-07-08"}
    (state_dir / "annotations.json").write_text(json.dumps({"annotations": [earlier]}))

    notes.add_note("t2", "the agent never checked the order")

    assert [entry["note"] for entry in _saved(state_dir)] == [
        "an earlier note",
        "the agent never checked the order",
    ]
