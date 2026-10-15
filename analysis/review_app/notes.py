"""Free-text notes from the first reading, kept in analysis/state/annotations.json.

Nothing is lost: rewording a note moves its earlier wording into ``history``,
and removing a note only marks it removed, so the path from a first note to a
failure mode stays inspectable. Notes already in the file, such as ones the
reference interface wrote, are kept as they are.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

from analysis.helpers import _state

NO_FAILURE = "no failure observed"

_FILE = "annotations.json"

# The server answers requests on several threads; every read-change-write of
# the file happens under this lock.
_LOCK = threading.Lock()

type NoteKind = Literal["note", "no_failure"]

# One entry of the file: a Note, or an entry another tool wrote.
type SavedNote = Mapping[str, object]


class NoteVersion(TypedDict):
    note: str
    ts: str


class Note(TypedDict):
    id: str
    trace_id: str
    kind: NoteKind
    quote: str | None
    step: int | None
    note: str
    ts: str
    history: list[NoteVersion]
    removed_ts: str | None


class UnknownNote(KeyError):
    """No saved note has the requested identifier."""


def list_notes() -> list[SavedNote]:
    """Return every saved note, removed ones included, oldest first."""
    return _saved_notes()


def add_note(
    trace_id: str, note: str, *, quote: str | None = None, step: int | None = None
) -> Note:
    """Save a note on a trace, quoting the selected text when there is some."""
    return _append(_new_note(trace_id, "note", note, quote, step))


def edit_note(note_id: str, note: str) -> SavedNote:
    """Reword a note, keeping its earlier wording in its history."""
    return _change(note_id, lambda entry: _reworded(entry, note))


def remove_note(note_id: str) -> SavedNote:
    """Mark a note removed; it stays in the file."""
    return _change(note_id, _removed)


def mark_no_failure(trace_id: str) -> SavedNote:
    """Record that a trace was read and showed no failure, once per trace."""
    return _no_failure_note(trace_id)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_note(
    trace_id: str, kind: NoteKind, note: str, quote: str | None, step: int | None
) -> Note:
    return {
        "id": uuid.uuid4().hex[:12],
        "trace_id": trace_id,
        "kind": kind,
        "quote": quote,
        "step": step,
        "note": note,
        "ts": _now(),
        "history": [],
        "removed_ts": None,
    }


def _path() -> Path:
    return _state.state_path(_FILE)


def _document() -> dict[str, object]:
    """Return the whole file; the reference interface also accepts a bare list."""
    content = _state.read_json(_path(), default=None)
    if isinstance(content, list):
        return {"annotations": content}
    return content if isinstance(content, dict) else {"annotations": []}


def _saved_notes() -> list[SavedNote]:
    entries = _document().get("annotations")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _save(entries: list[SavedNote]) -> None:
    _state.write_json(_path(), {**_document(), "annotations": entries})


def _append(created: Note) -> Note:
    with _LOCK:
        _save([*_saved_notes(), created])
    return created


def _position(entries: list[SavedNote], note_id: str) -> int:
    for position, entry in enumerate(entries):
        if entry.get("id") == note_id:
            return position
    raise UnknownNote(note_id)


def _change(note_id: str, change: Callable[[SavedNote], SavedNote]) -> SavedNote:
    with _LOCK:
        entries = _saved_notes()
        position = _position(entries, note_id)
        entries[position] = change(entries[position])
        _save(entries)
    return entries[position]


def _reworded(entry: SavedNote, note: str) -> SavedNote:
    earlier: NoteVersion = {"note": str(entry.get("note", "")), "ts": str(entry.get("ts", ""))}
    history = entry.get("history")
    versions = list(history) if isinstance(history, list) else []
    return {**entry, "note": note, "ts": _now(), "history": [*versions, earlier]}


def _removed(entry: SavedNote) -> SavedNote:
    return {**entry, "removed_ts": _now()}


def _is_live_no_failure(entry: SavedNote, trace_id: str) -> bool:
    return (
        entry.get("trace_id") == trace_id
        and entry.get("kind") == "no_failure"
        and not entry.get("removed_ts")
    )


def _no_failure_note(trace_id: str) -> SavedNote:
    with _LOCK:
        entries = _saved_notes()
        existing = next((e for e in entries if _is_live_no_failure(e, trace_id)), None)
        if existing is not None:
            return existing
        created = _new_note(trace_id, "no_failure", NO_FAILURE, None, None)
        _save([*entries, created])
        return created
