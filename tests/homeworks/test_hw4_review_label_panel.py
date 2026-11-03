"""Tests for the Label tab's decisions panel (analysis/review_app/ui/js/label-panel.js).

Each final mode starts from a pre-filled decision: present when the mode lists
the turn among its traces, absent when the turn is one of its close negatives
or was marked "no failure observed", and otherwise absent but not checked yet.
A saved label wins over the pre-fill, and a click wins over both. The turn's
notes sit folded under each mode. Each test runs the page's own module in Node.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

LABEL_PANEL = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/label-panel.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { labelPanel } = await import(process.argv[1]);
const given = JSON.parse(process.argv[2]);
state.modes = given.modes;
state.notes = given.notes;
state.labels = given.labels;
state.labelDrafts = given.drafts;
state.labelOpen = new Set(given.open);
state.labelTurn = given.turn;
console.log(labelPanel(given.conversation));
"""

MODES = [
    {"name": "no_reply", "definition": "The turn ends without any reply.", "example_trace_ids": ["t1"],
     "close_negative_trace_ids": [], "note_ids": ["n1"]},
    {"name": "date_errors", "definition": "The reply uses the wrong date.", "example_trace_ids": [],
     "close_negative_trace_ids": ["t1"], "note_ids": []},
    {"name": "too_much_detail", "definition": "The reply says more than needed.", "example_trace_ids": [],
     "close_negative_trace_ids": [], "note_ids": []},
]

NOTES = [
    {"id": "n1", "trace_id": "t1", "kind": "note", "quote": "Let me check", "step": 2, "note": "No reply after this."},
    {"id": "n2", "trace_id": "t2", "kind": "no_failure", "quote": None, "step": None, "note": "no failure observed"},
]

ONE_TURN = {"session_id": "s1", "turns": [{"trace_id": "t1"}]}
TWO_TURNS = {"session_id": "s2", "turns": [{"trace_id": "t1"}, {"trace_id": "t2"}]}


def _panel(
    conversation: dict[str, object] = ONE_TURN,
    labels: list[dict[str, object]] | None = None,
    drafts: dict[str, dict[str, int]] | None = None,
    open_modes: tuple[str, ...] = (),
    turn: dict[str, int] | None = None,
) -> str:
    given = {
        "modes": MODES, "notes": NOTES, "labels": labels or [], "drafts": drafts or {},
        "open": list(open_modes), "turn": turn or {}, "conversation": conversation,
    }
    result = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT, LABEL_PANEL.as_uri(), json.dumps(given)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _block(panel: str, mode: str) -> str:
    """The HTML of one mode's block in the panel."""
    match = re.search(rf'<div class="decision[^"]*" data-mode="{mode}">.*?<!-- /decision -->', panel, re.S)
    assert match, f"no block for {mode}"
    return match[0]


def _pressed(block: str) -> str:
    match = re.search(r'aria-pressed="true"[^>]*>(Present|Absent)<', block)
    return match[1] if match else ""


def test_a_mode_listing_the_turn_starts_present() -> None:
    block = _block(_panel(), "no_reply")

    assert _pressed(block) == "Present"
    assert "From your notes" in block


def test_a_close_negative_starts_absent() -> None:
    block = _block(_panel(), "date_errors")

    assert _pressed(block) == "Absent"
    assert "Close negative" in block


def test_a_turn_with_no_failure_starts_absent_for_every_mode() -> None:
    panel = _panel(TWO_TURNS, turn={"s2": 1})

    assert _pressed(_block(panel, "too_much_detail")) == "Absent"
    assert "No failure observed" in _block(panel, "too_much_detail")


def test_a_mode_without_evidence_starts_absent_but_not_checked() -> None:
    block = _block(_panel(), "too_much_detail")

    assert _pressed(block) == "Absent"
    assert "Not checked yet" in block
    assert "is-unchecked" in block


def test_a_saved_label_wins_over_the_prefill() -> None:
    saved = [{"trace_id": "t1", "mode": "no_reply", "label": 0, "ts": "2026-11-02T00:00:00+00:00"}]

    block = _block(_panel(labels=saved), "no_reply")

    assert _pressed(block) == "Absent"
    assert "Saved" in block


def test_a_click_wins_and_counts_as_checked() -> None:
    block = _block(_panel(drafts={"t1": {"too_much_detail": 1}}), "too_much_detail")

    assert _pressed(block) == "Present"
    assert "is-unchecked" not in block
    assert "Not checked yet" not in block


def test_saving_waits_until_every_mode_is_checked() -> None:
    assert re.search(r"<button[^>]*disabled[^>]*>Save decisions", _panel())
    assert "2 of 3 checked" in _panel()

    ready = _panel(drafts={"t1": {"too_much_detail": 0}})
    assert "3 of 3 checked" in ready
    assert not re.search(r"<button[^>]*disabled[^>]*>Save decisions", ready)


def test_the_turn_notes_sit_folded_under_each_mode_without_a_count() -> None:
    block = _block(_panel(), "date_errors")

    assert 'data-action="toggle-label-notes" data-mode="date_errors" aria-expanded="false"' in block
    assert ">Notes<" in re.sub(r"\s+", "", block)
    assert "No reply after this." not in block


def test_an_unfolded_mode_shows_the_note_cards_of_read() -> None:
    block = _block(_panel(open_modes=("date_errors",)), "date_errors")

    assert 'data-note-card="n1"' in block
    assert "No reply after this." in block
    assert "“Let me check”" in block


def test_a_turn_without_notes_has_no_notes_button() -> None:
    panel = _panel(TWO_TURNS, turn={"s2": 1})

    assert "toggle-label-notes" not in panel


def test_a_two_turn_conversation_switches_turns() -> None:
    panel = _panel(TWO_TURNS, turn={"s2": 1})

    assert 'data-action="label-turn" data-turn="0" aria-pressed="false"' in panel
    assert 'data-action="label-turn" data-turn="1" aria-pressed="true"' in panel
    assert 'data-trace="t2"' in panel


def test_a_turn_not_reviewed_yet_offers_no_decisions() -> None:
    panel = _panel({"session_id": "s3", "turns": [{"trace_id": "t9"}]})

    assert "data-action=\"label-pick\"" not in panel
    assert "Save decisions" not in panel
    assert "Review this turn in Read first" in panel


def test_the_definition_shows_in_full_on_hover() -> None:
    block = _block(_panel(), "no_reply")

    assert 'data-full="The turn ends without any reply."' in block
    assert "title=" not in block
