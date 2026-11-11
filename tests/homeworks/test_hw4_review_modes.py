"""Tests for the failure modes the review page's Failure modes tab shows.

The modes come from patterns.json. Each one carries its definition, how many
of its traces fall in each review batch, its total, and the ids of the notes
that support it. Batches sharing a number (batch_1_random, batch_1_clusters)
count as one batch.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from analysis.review_app import modes


def _write_batch(state: Path, name: str, trace_ids: list[str], selected_at: str) -> None:
    rows = [{"trace_id": trace_id, "selected_at": selected_at} for trace_id in trace_ids]
    (state / "batches" / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def _mode(name: str, traces: list[str], note_ids: list[str]) -> dict[str, object]:
    return {
        "name": name,
        "definition": f"{name} definition.",
        "status": "candidate",
        "example_trace_ids": traces,
        "note_ids": note_ids,
    }


@pytest.fixture
def state(analysis_state: Path) -> Path:
    shutil.rmtree(analysis_state / "batches", ignore_errors=True)
    (analysis_state / "batches").mkdir()
    _write_batch(analysis_state, "batch_1_random", ["t1", "t2"], "2026-10-20T00:00:00+00:00")
    _write_batch(analysis_state, "batch_1_clusters", ["t3"], "2026-10-21T00:00:00+00:00")
    _write_batch(analysis_state, "batch_2_roles", ["t4", "t5"], "2026-10-22T00:00:00+00:00")
    patterns = [
        _mode("no_reply", ["t1", "t3", "t4"], ["n1", "n2", "n3", "n4"]),
        _mode("date_errors", ["t5"], ["n5"]),
        _mode("shows_others_orders", [], []),
    ]
    (analysis_state / "patterns.json").write_text(json.dumps({"modes": patterns}))
    return analysis_state


def test_each_mode_counts_its_traces_per_batch(state: Path) -> None:
    listed = modes.list_modes()

    assert [(m["name"], m["batch_counts"], m["total"]) for m in listed] == [
        ("no_reply", [{"batch": 1, "count": 2}, {"batch": 2, "count": 1}], 3),
        ("date_errors", [{"batch": 1, "count": 0}, {"batch": 2, "count": 1}], 1),
        ("shows_others_orders", [{"batch": 1, "count": 0}, {"batch": 2, "count": 0}], 0),
    ]


def test_each_mode_keeps_its_definition_status_and_notes(state: Path) -> None:
    first = modes.list_modes()[0]

    assert first["definition"] == "no_reply definition."
    assert first["status"] == "candidate"
    assert first["note_ids"] == ["n1", "n2", "n3", "n4"]


def test_each_mode_keeps_the_notes_behind_its_close_negatives(state: Path) -> None:
    patterns = json.loads((state / "patterns.json").read_text())
    patterns["modes"][0]["close_negative_note_ids"] = ["n9"]
    (state / "patterns.json").write_text(json.dumps(patterns))

    listed = modes.list_modes()

    assert listed[0]["close_negative_note_ids"] == ["n9"]
    assert listed[1]["close_negative_note_ids"] == []


def test_each_mode_keeps_its_nearest_mode_and_boundary_or_none(state: Path) -> None:
    patterns = json.loads((state / "patterns.json").read_text())
    patterns["modes"][0]["nearest_mode"] = "date_errors"
    patterns["modes"][0]["boundary"] = "Silence is no_reply; a wrong date is date_errors."
    (state / "patterns.json").write_text(json.dumps(patterns))

    listed = modes.list_modes()

    assert (listed[0]["nearest_mode"], listed[0]["boundary"]) == (
        "date_errors",
        "Silence is no_reply; a wrong date is date_errors.",
    )
    assert (listed[1]["nearest_mode"], listed[1]["boundary"]) == (None, None)


def test_saving_a_boundary_writes_it_and_keeps_the_rest_of_the_mode(state: Path) -> None:
    saved = modes.save_boundary("no_reply", "date_errors", "  Silence is no_reply.  ")

    stored = json.loads((state / "patterns.json").read_text())["modes"][0]
    assert (saved["nearest_mode"], saved["boundary"]) == ("date_errors", "Silence is no_reply.")
    assert (stored["nearest_mode"], stored["boundary"]) == ("date_errors", "Silence is no_reply.")
    assert stored["note_ids"] == ["n1", "n2", "n3", "n4"]


def test_a_boundary_can_have_no_nearest_mode(state: Path) -> None:
    modes.save_boundary("no_reply", "date_errors", "Old text.")

    saved = modes.save_boundary("no_reply", None, "Any text at all means it is not no_reply.")

    stored = json.loads((state / "patterns.json").read_text())["modes"][0]
    assert (saved["nearest_mode"], saved["boundary"]) == (None, "Any text at all means it is not no_reply.")
    assert (stored["nearest_mode"], stored["boundary"]) == (None, "Any text at all means it is not no_reply.")


def test_saving_a_boundary_for_an_unknown_mode_is_refused(state: Path) -> None:
    with pytest.raises(modes.UnknownMode, match="ghost"):
        modes.save_boundary("ghost", "date_errors", "text")


@pytest.mark.parametrize(
    ("nearest", "text", "reason"),
    [
        ("ghost", "text", "ghost"),
        ("no_reply", "text", "itself"),
        ("date_errors", "   ", "empty"),
    ],
)
def test_a_bad_boundary_is_refused_and_nothing_is_written(state: Path, nearest: str, text: str, reason: str) -> None:
    before = (state / "patterns.json").read_text()

    with pytest.raises(modes.BadBoundary, match=reason):
        modes.save_boundary("no_reply", nearest, text)

    assert (state / "patterns.json").read_text() == before


def test_a_trace_in_no_batch_is_refused(state: Path) -> None:
    patterns = json.loads((state / "patterns.json").read_text())
    patterns["modes"][0]["example_trace_ids"].append("unbatched")
    (state / "patterns.json").write_text(json.dumps(patterns))

    with pytest.raises(ValueError, match="unbatched"):
        modes.list_modes()


def test_no_patterns_file_means_no_modes(state: Path) -> None:
    (state / "patterns.json").unlink()

    assert modes.list_modes() == []
