"""Tests for the Label tab's progress (analysis/review_app/ui/js/lookups.js).

A turn is labeled once every failure mode has a saved decision for it. In the
Label tab each conversation card says how many of its turns are labeled, the
list summary counts the read turns left to label, and the top bar counts the
read turns labeled. After a save the page moves to the next read turn left to
label: in the same conversation first, then in the next conversation of the
list, wrapping round to the top. Each test runs the page's own module in Node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LOOKUPS = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/lookups.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { labelState, labelProgress, nextToLabel, turnsToLabel } = await import(process.argv[1]);
Object.assign(state, JSON.parse(process.argv[2]));
console.log(JSON.stringify({
  states: Object.fromEntries(state.conversations.map((c) => [c.session_id, labelState(c)])),
  progress: labelProgress(),
  toLabel: turnsToLabel(state.conversations),
  next: nextToLabel(state.conversations, state.selectedId),
}));
"""


def _conversation(session_id: str, *trace_ids: str) -> dict[str, object]:
    return {"session_id": session_id, "turns": [{"trace_id": t} for t in trace_ids]}


PAGE = {
    "selectedId": None,
    "modes": [{"name": "no_reply"}, {"name": "date_errors"}],
    "conversations": [
        _conversation("done", "t1"),
        _conversation("half", "t2a", "t2b"),
        _conversation("todo", "t3"),
        _conversation("unread", "t4"),
    ],
    "notes": [
        {"id": "n1", "trace_id": "t1", "kind": "no_failure"},
        {"id": "n2", "trace_id": "t2a", "kind": "note"},
        {"id": "n3", "trace_id": "t2b", "kind": "note"},
        {"id": "n4", "trace_id": "t3", "kind": "note"},
    ],
    "labels": [
        {"trace_id": "t1", "mode": "no_reply", "label": 0},
        {"trace_id": "t1", "mode": "date_errors", "label": 0},
        {"trace_id": "t2a", "mode": "no_reply", "label": 1},
        {"trace_id": "t2a", "mode": "date_errors", "label": 0},
        {"trace_id": "t3", "mode": "no_reply", "label": 1},
    ],
}


def _run(**changes: object) -> dict[str, object]:
    page = {**PAGE, **changes}
    result = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT, LOOKUPS.as_uri(), json.dumps(page)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_each_card_says_how_many_turns_are_labeled() -> None:
    states = _run()["states"]

    assert states["done"] == ["labeled", "state-clean"]
    assert states["half"] == ["1 of 2 turns labeled", "state-note"]
    assert states["todo"] == ["not labeled", ""]
    assert states["unread"] == ["not read", ""]


def test_the_open_card_says_labeling_now_with_its_progress() -> None:
    assert _run(selectedId="half")["states"]["half"] == ["labeling now · 1 of 2 turns labeled", "state-reading"]
    assert _run(selectedId="todo")["states"]["todo"] == ["labeling now", "state-reading"]


def test_the_counter_counts_read_turns_labeled() -> None:
    assert _run()["progress"] == {"labeled": 2, "read": 4}


def test_the_list_summary_counts_read_turns_left_to_label() -> None:
    assert _run()["toLabel"] == 2


def test_after_a_save_the_next_read_turn_of_the_same_conversation_opens() -> None:
    labels = [label for label in PAGE["labels"] if label["trace_id"] != "t2a"]

    assert _run(selectedId="half", labels=labels)["next"] == {"session_id": "half", "turn": 0}


def test_a_finished_conversation_moves_on_to_the_next_with_a_turn_to_label() -> None:
    assert _run(selectedId="done")["next"] == {"session_id": "half", "turn": 1}


def test_the_search_wraps_round_to_the_top_of_the_list() -> None:
    conversations = [PAGE["conversations"][i] for i in (1, 0, 3)]

    assert _run(selectedId="unread", conversations=conversations)["next"] == {"session_id": "half", "turn": 1}


def test_nothing_left_to_label_stays_put() -> None:
    labels = [*PAGE["labels"],
              {"trace_id": "t2b", "mode": "no_reply", "label": 0}, {"trace_id": "t2b", "mode": "date_errors", "label": 0},
              {"trace_id": "t3", "mode": "date_errors", "label": 0}]

    assert _run(selectedId="done", labels=labels)["next"] is None
