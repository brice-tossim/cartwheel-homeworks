"""Tests for which quotes the review page highlights inside a turn.

The rule lives in analysis/review_app/ui/js/quote-marks.js. Each test runs the
page's own module in Node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

QUOTE_MARKS = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/quote-marks.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SCRIPT = """
const { canMark } = await import(process.argv[1]);
console.log(JSON.stringify(canMark(process.argv[2], JSON.parse(process.argv[3]))));
"""


def _can_mark(kind: str, covered_by: list[str]) -> bool:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", _SCRIPT, QUOTE_MARKS.as_uri(), kind, json.dumps(covered_by)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_a_suggestion_quote_is_marked_inside_a_note_quote() -> None:
    assert _can_mark("ai-mark", ["note-mark"]) is True


def test_a_quote_is_marked_where_nothing_is_marked_yet() -> None:
    assert _can_mark("note-mark", []) is True


def test_a_second_quote_of_the_same_kind_is_not_marked_twice() -> None:
    assert _can_mark("note-mark", ["note-mark"]) is False
    assert _can_mark("ai-mark", ["ai-mark"]) is False
