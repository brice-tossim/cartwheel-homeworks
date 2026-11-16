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
state.editingBoundary = process.argv[6] || null;
state.openRequirements = new Set(JSON.parse(process.argv[7]));
state.specRevisions = JSON.parse(process.argv[8]);
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


def _view(
    search: str = "",
    open_modes: tuple[str, ...] = ("no_reply", "date_errors"),
    modes: list[dict[str, object]] = MODES,
    editing: str = "",
    open_requirements: tuple[str, ...] = (),
    spec_revisions: list[dict[str, object]] | None = None,
) -> str:
    result = subprocess.run(
        [
            "node", "--input-type=module", "-e", _SCRIPT, MODES_VIEW.as_uri(),
            json.dumps(modes), json.dumps(NOTES), search, json.dumps(list(open_modes)), editing,
            json.dumps(list(open_requirements)), json.dumps(spec_revisions or []),
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


def test_mode_names_in_a_boundary_are_bold() -> None:
    boundary = "Silence is no_reply; a wrong day is date_errors, not no_reply_extra."
    modes = [{**MODES[0], "nearest_mode": "date_errors", "boundary": boundary}, MODES[1]]

    view = _view(modes=modes)

    assert (
        'Silence is <strong class="mode-ref mono">no_reply</strong>; '
        'a wrong day is <strong class="mode-ref mono">date_errors</strong>, not no_reply_extra.'
    ) in view


def test_a_boundary_with_no_nearest_mode_says_so() -> None:
    modes = [{**MODES[0], "nearest_mode": None, "boundary": "Any text means it is not silence."}, MODES[1]]

    view = _view(modes=modes)

    assert "<strong>Boundary</strong> · no close neighbour</p>" in view
    assert "nearest mode" not in view


def test_the_boundary_form_offers_none_as_nearest_mode() -> None:
    modes = [{**MODES[0], "nearest_mode": None, "boundary": "Any text means it is not silence."}, MODES[1]]

    view = _view(modes=modes, editing="no_reply")

    assert '<option value="none" selected>None (no close neighbour)</option>' in view
    assert "How to tell it apart" in view
    assert "Which question decides whether a trace has this mode, and what looks like it but isn't" in view


def test_the_boundary_form_keeps_the_saved_nearest_mode_selected() -> None:
    modes = [{**MODES[0], "nearest_mode": "date_errors", "boundary": "Silence."}, MODES[1]]

    view = _view(modes=modes, editing="no_reply")

    assert '<option value="none">None (no close neighbour)</option>' in view
    assert '<option value="date_errors" selected>date_errors</option>' in view
    assert "How to tell them apart" in view


REQUIRED = {
    **MODES[0],
    "evaluator_type": "code_check",
    "requirements": [
        {"kind": "spec_revision", "id": "RESP-7", "text": "Every turn ends with a reply."},
        {"kind": "spec_revision", "id": "RESP-6", "text": "Do not reveal <internal> details."},
    ],
    "product_changes": ["Return a fallback reply."],
}


def test_a_mode_shows_its_evaluator_and_requirement_ids_with_the_text_folded() -> None:
    view = _view(modes=[REQUIRED, MODES[1]])

    assert "<strong>Evaluator</strong>" in view and ">Code check<" in view
    assert ">RESP-7<" in view and ">RESP-6<" in view
    assert "proposed spec revisions" in view
    assert 'data-action="toggle-requirement" data-mode="no_reply" aria-expanded="false"' in view
    assert "Show requirement" in view
    assert "Every turn ends with a reply." not in view
    assert "Return a fallback reply." not in view


def test_an_unfolded_requirement_shows_its_text_and_product_changes() -> None:
    view = _view(modes=[REQUIRED, MODES[1]], open_requirements=("no_reply",))

    assert 'data-mode="no_reply" aria-expanded="true"' in view and "Hide requirement" in view
    assert "Every turn ends with a reply." in view
    assert "Do not reveal &lt;internal&gt; details." in view
    assert "Product changes" in view and "Return a fallback reply." in view


def test_a_single_requirement_without_product_changes_says_revision_and_lists_no_changes() -> None:
    mode = {**REQUIRED, "evaluator_type": "llm_judge", "requirements": REQUIRED["requirements"][:1], "product_changes": []}

    view = _view(modes=[mode, MODES[1]], open_requirements=("no_reply",))

    assert ">LLM judge<" in view
    assert "proposed spec revision<" in view
    assert "Product changes" not in view


def test_a_mode_without_evaluator_or_requirement_shows_neither() -> None:
    view = _view()

    assert "Evaluator" not in view and "toggle-requirement" not in view


def test_spec_revisions_not_tied_to_a_mode_show_below_the_modes() -> None:
    revision = {"id": "REF-1", "text": "A refund covers whole units.", "product_changes": ["Take units."]}

    view = _view(spec_revisions=[revision])

    assert view.index("</ul>") < view.index("Spec revisions not tied to a mode")
    assert ">REF-1<" in view and "A refund covers whole units." in view and "Take units." in view


def test_no_spec_revisions_means_no_section() -> None:
    assert "Spec revisions not tied to a mode" not in _view()


def test_a_mode_name_already_marked_in_a_boundary_is_bold_once() -> None:
    boundary = "Silence is **no_reply**, a wrong day is `date_errors`. Both can hold."
    modes = [{**MODES[0], "nearest_mode": "date_errors", "boundary": boundary}, MODES[1]]

    view = _view(modes=modes)

    assert (
        'Silence is <strong class="mode-ref mono">no_reply</strong>, '
        'a wrong day is <strong class="mode-ref mono">date_errors</strong>. Both can hold.'
    ) in view
