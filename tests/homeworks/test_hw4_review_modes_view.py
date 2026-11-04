"""Tests for the Failure modes tab of the review page.

The tab is drawn by analysis/review_app/ui/js/modes-view.js. Each test runs the
page's own module in Node with a few modes and notes, and reads the HTML the
tab would show.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODES_VIEW = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/modes-view.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { modesView } = await import(process.argv[1]);
state.modes = JSON.parse(process.argv[2]);
state.notes = JSON.parse(process.argv[3]);
state.modesSearch = process.argv[4];
state.openModes = new Set(JSON.parse(process.argv[5]));
console.log(modesView());
"""

MODES = [
    {
        "name": "no_reply",
        "definition": "The turn ends **without** any reply.",
        "status": "candidate",
        "batch_counts": [{"batch": 1, "count": 2}, {"batch": 2, "count": 1}],
        "total": 3,
        "note_ids": ["n1", "n2", "n3"],
    },
    {
        "name": "date_errors",
        "definition": "The reply uses the wrong current date.",
        "status": "candidate",
        "batch_counts": [{"batch": 1, "count": 0}, {"batch": 2, "count": 1}],
        "total": 1,
        "note_ids": ["n4"],
    },
]

NOTES = [
    {"id": "n1", "trace_id": "abcdef0123", "kind": "note", "quote": None, "step": None, "note": "No answer at all."},
    {"id": "n2", "trace_id": "bbbbbbbb99", "kind": "note", "quote": "Let me check", "step": 2, "note": "`no_reply` here."},
    {"id": "n3", "trace_id": "cccccccc99", "kind": "note", "quote": None, "step": None, "note": "Gone.",
     "removed_ts": "2026-10-30T00:00:00+00:00"},
    {"id": "n4", "trace_id": "dddddddd99", "kind": "note", "quote": None, "step": None, "note": "<b>Wrong date</b>"},
]


def _view(search: str = "", open_modes: tuple[str, ...] = ("no_reply", "date_errors")) -> str:
    result = subprocess.run(
        [
            "node", "--input-type=module", "-e", _SCRIPT, MODES_VIEW.as_uri(),
            json.dumps(MODES), json.dumps(NOTES), search, json.dumps(list(open_modes)),
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def test_every_mode_shows_its_name_definition_and_counts() -> None:
    view = _view()

    assert "no_reply" in view and "date_errors" in view
    assert "The turn ends <strong>without</strong> any reply." in view
    assert "3 traces" in view and "1 trace<" in view
    assert "Batch 1 <strong>2</strong>" in view and "Batch 2 <strong>1</strong>" in view


def test_supporting_notes_start_folded_with_their_count() -> None:
    view = _view(open_modes=())

    assert "No answer at all." not in view
    assert "Supporting notes · 2" in view
    assert 'data-action="toggle-notes" data-mode="no_reply" aria-expanded="false"' in view


def test_an_unfolded_mode_shows_its_notes() -> None:
    view = _view(open_modes=("no_reply",))

    assert "No answer at all." in view
    assert "<code>no_reply</code> here." in view
    assert "“Let me check”" in view
    assert 'data-mode="no_reply" aria-expanded="true"' in view
    assert "&lt;b&gt;Wrong date" not in view


def test_a_removed_note_is_not_shown_or_counted() -> None:
    view = _view()

    assert "Gone." not in view
    assert "Supporting notes · 2" in view


def test_each_note_leads_to_its_trace_in_the_read_tab() -> None:
    view = _view()

    assert 'data-action="open-note" data-trace="bbbbbbbb99" data-note="n2"' in view
    assert "trace bbbbbbbb · step 2" in view


def test_the_search_keeps_only_modes_whose_name_matches() -> None:
    view = _view("DATE")

    assert "date_errors" in view
    assert "no_reply" not in view


def test_a_search_with_no_match_says_so() -> None:
    view = _view("refund")

    assert "No mode name contains “refund”." in view


def test_notes_and_definitions_still_escape_html() -> None:
    view = _view()

    assert "<b>" not in view
    assert "&lt;b&gt;Wrong date&lt;/b&gt;" in view
