"""Tests for the conversation list filters in the review page.

The filters live in analysis/review_app/ui/js/filters.js. Each test runs the
page's own module in Node and reads which conversations a filter keeps.
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


def _visible(suggested: bool) -> list[str]:
    page = {
        "conversations": CONVERSATIONS,
        "suggestions": SUGGESTIONS,
        "notes": [],
        "batches": [],
        "filters": {"batch": "", "search": "", "role": "", "action": "", "tool": "",
                    "twoTurns": False, "unread": False, "suggested": suggested},
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
