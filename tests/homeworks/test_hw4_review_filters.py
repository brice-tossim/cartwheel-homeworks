"""Tests for the conversation list filters in the review page.

The filters live in analysis/review_app/ui/js/filters.js. Each test runs the
page's own module in Node and reads which conversations a filter keeps.
"Not read yet" and "AI suggestions to check" belong to the Read tab, "Not
labeled yet" to the Label tab; the other filters apply in both.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FILTERS = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/filters.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { visibleConversations } = await import(process.argv[1]);
Object.assign(state, JSON.parse(process.argv[2]));
console.log(JSON.stringify(visibleConversations().map((c) => c.session_id)));
"""


def _conversation(session_id: str, *trace_ids: str) -> dict[str, object]:
    turns = [{"trace_id": t, "customer": "", "reply": "", "steps": []} for t in trace_ids]
    return {"session_id": session_id, "turns": turns, "role": "shopper", "tools": [], "actions": []}


CONVERSATIONS = [_conversation("one", "t1"), _conversation("two", "t2a", "t2b"), _conversation("three", "t3")]
SUGGESTIONS = [
    {"id": "s1", "trace_id": "t2b", "status": "pending"},
    {"id": "s2", "trace_id": "t3", "status": "rejected"},
]


MODES = [{"name": "no_reply"}, {"name": "date_errors"}]
# t1 and t2a are read; t1 has every mode saved, t2a only one.
NOTES = [
    {"id": "n1", "trace_id": "t1", "kind": "no_failure"},
    {"id": "n2", "trace_id": "t2a", "kind": "note"},
]
LABELS = [
    {"trace_id": "t1", "mode": "no_reply", "label": 0},
    {"trace_id": "t1", "mode": "date_errors", "label": 0},
    {"trace_id": "t2a", "mode": "no_reply", "label": 1},
]


def _visible(
    suggested: bool = False, unread: bool = False, unlabeled: bool = False, view: str = "read",
) -> list[str]:
    page = {
        "view": view,
        "conversations": CONVERSATIONS,
        "suggestions": SUGGESTIONS,
        "notes": NOTES,
        "modes": MODES,
        "labels": LABELS,
        "batches": [],
        "filters": {"batch": "", "search": "", "role": "", "action": "", "tool": "", "twoTurns": False,
                    "unread": unread, "suggested": suggested, "unlabeled": unlabeled},
    }
    result = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT, FILTERS.as_uri(), json.dumps(page)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_the_suggestion_filter_keeps_conversations_with_a_pending_suggestion_on_any_turn() -> None:
    assert _visible(suggested=True) == ["two"]


def test_without_the_suggestion_filter_every_conversation_shows() -> None:
    assert _visible(suggested=False) == ["one", "two", "three"]


def test_not_labeled_yet_keeps_conversations_with_a_read_turn_left_to_label() -> None:
    assert _visible(unlabeled=True, view="label") == ["two"]


def test_not_labeled_yet_does_nothing_in_the_read_tab() -> None:
    assert _visible(unlabeled=True, view="read") == ["one", "two", "three"]


def test_read_tab_filters_do_nothing_in_the_label_tab() -> None:
    assert _visible(unread=True, suggested=True, view="label") == ["one", "two", "three"]


def test_not_read_yet_still_works_in_the_read_tab() -> None:
    assert _visible(unread=True, view="read") == ["two", "three"]
