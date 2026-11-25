"""AI suggestions the reviewer accepts or rejects, kept in analysis/state/suggestions.json.

An agent leaves suggested notes in the file. They stay apart from the reviewer's
own notes until a decision: accepting one turns it into the reviewer's note,
rejecting one only records the decision. A suggestion keeps its first decision,
and every suggestion stays in the file with what was decided.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from analysis.helpers import _state
from analysis.review_app import notes

PENDING = "pending"

_FILE = "suggestions.json"

# The server answers on several threads; every read-change-write of the file
# happens under this lock.
_LOCK = threading.Lock()

type SavedSuggestion = Mapping[str, object]


class UnknownSuggestion(KeyError):
    """No saved suggestion has the requested identifier."""


def list_suggestions() -> list[SavedSuggestion]:
    """Return every suggestion with its status: pending, accepted or rejected."""
    return [_with_status(entry) for entry in _saved_suggestions()]


def accept_suggestion(suggestion_id: str) -> SavedSuggestion:
    """Turn a pending suggestion into the reviewer's own note."""
    return _decide(suggestion_id, _accepted)


def reject_suggestion(suggestion_id: str) -> SavedSuggestion:
    """Record that the reviewer rejected a pending suggestion."""
    return _decide(suggestion_id, _rejected)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _path() -> Path:
    return _state.state_path(_FILE)


def _document() -> object:
    """Return the whole file: a bare list, or an object holding ``suggestions``."""
    return _state.read_json(_path(), default=[])


def _saved_suggestions() -> list[SavedSuggestion]:
    document = _document()
    entries = document.get("suggestions") if isinstance(document, dict) else document
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _save(entries: list[SavedSuggestion]) -> None:
    document = _document()
    if isinstance(document, dict):
        _state.write_json(_path(), {**document, "suggestions": entries})
    else:
        _state.write_json(_path(), entries)


def _with_status(entry: SavedSuggestion) -> SavedSuggestion:
    return {**entry, "status": entry.get("status") or PENDING}


def _position(entries: list[SavedSuggestion], suggestion_id: str) -> int:
    for position, entry in enumerate(entries):
        if entry.get("id") == suggestion_id:
            return position
    raise UnknownSuggestion(suggestion_id)


def _decide(
    suggestion_id: str, decision: Callable[[SavedSuggestion], SavedSuggestion]
) -> SavedSuggestion:
    with _LOCK:
        entries = _saved_suggestions()
        position = _position(entries, suggestion_id)
        current = _with_status(entries[position])
        if current["status"] != PENDING:
            return current
        entries[position] = decision(current)
        _save(entries)
        return entries[position]


def _note_text(entry: SavedSuggestion) -> str:
    return str(entry.get("note") or entry.get("mode") or "AI suggestion")


def _quote(entry: SavedSuggestion) -> str | None:
    quote = entry.get("quote")
    return quote if isinstance(quote, str) and quote else None


def _accepted(entry: SavedSuggestion) -> SavedSuggestion:
    note = notes.add_note(str(entry.get("trace_id") or ""), _note_text(entry), quote=_quote(entry))
    return {**entry, "status": "accepted", "note_id": note["id"], "decided_ts": _now()}


def _rejected(entry: SavedSuggestion) -> SavedSuggestion:
    return {**entry, "status": "rejected", "decided_ts": _now()}
