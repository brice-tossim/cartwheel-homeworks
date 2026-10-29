"""Tests for the cards in the review page's side panel: notes and AI suggestions.

The cards are drawn by analysis/review_app/ui/js/side-panel.js. Each test runs
the page's own module in Node and reads the HTML the card would show.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SIDE_PANEL = Path(__file__).resolve().parents[2] / "analysis/review_app/ui/js/side-panel.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node to run the page script")

_SUGGESTION_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { suggestionsCard } = await import(process.argv[1]);
state.suggestions = [JSON.parse(process.argv[2])];
console.log(suggestionsCard({ turns: [{ trace_id: "t1" }] }));
"""

_NOTE_SCRIPT = """
const { state } = await import(new URL("state.js", process.argv[1]).href);
const { noteCard } = await import(process.argv[1]);
const note = JSON.parse(process.argv[2]);
state.editingNoteId = process.argv[3] || null;
console.log(noteCard(note));
"""


def _run(script: str, *args: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, SIDE_PANEL.as_uri(), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _suggestion_card(quote: str, note: str) -> str:
    suggestion = {"id": "s1", "trace_id": "t1", "status": "pending", "quote": quote, "note": note}
    return _run(_SUGGESTION_SCRIPT, json.dumps(suggestion))


def _note_card(quote: str, note: str, editing: bool = False) -> str:
    saved = {"id": "n1", "trace_id": "t1", "quote": quote, "note": note, "step": 1}
    return _run(_NOTE_SCRIPT, json.dumps(saved), "n1" if editing else "")


def test_the_suggestion_note_shows_code_and_bold_instead_of_markdown_symbols() -> None:
    card = _suggestion_card("x", "`date_errors` is present here. It is **far** off.")

    assert "<code>date_errors</code>" in card
    assert "<strong>far</strong>" in card
    assert "`" not in card and "**" not in card


def test_the_suggestion_quote_shows_bold_instead_of_markdown_symbols() -> None:
    card = _suggestion_card("Your order is **delivered**.", "a note")

    assert "Your order is <strong>delivered</strong>." in card


def test_the_suggestion_card_still_escapes_html() -> None:
    card = _suggestion_card("<b>quote</b>", "<script>note</script>")

    assert "<script>" not in card and "<b>" not in card
    assert "&lt;script&gt;" in card


def test_a_saved_note_shows_code_and_bold_instead_of_markdown_symbols() -> None:
    card = _note_card("Your order is **delivered**.", "`date_errors` is present here.")

    assert "<code>date_errors</code>" in card
    assert "Your order is <strong>delivered</strong>." in card
    assert "`" not in card and "**" not in card


def test_a_saved_note_still_escapes_html() -> None:
    card = _note_card("<b>quote</b>", "<script>note</script>")

    assert "<script>" not in card and "<b>" not in card
    assert "&lt;script&gt;" in card


def test_editing_a_note_keeps_its_markdown_symbols_in_the_text_box() -> None:
    card = _note_card("q", "`date_errors` is **here**.", editing=True)

    assert "`date_errors` is **here**.</textarea>" in card
