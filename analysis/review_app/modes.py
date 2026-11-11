"""The failure modes the review page shows, read from patterns.json.

patterns.json is the single source of the failure modes. Each mode comes back
with its definition, how many of its traces fall in each review batch, its
total, the ids of the notes that support it, and the ids of the notes that
explain its close negatives. Batches sharing a number
(batch_1_random, batch_1_clusters) count as one batch.
"""

from __future__ import annotations

import re
from typing import NotRequired, TypedDict

from analysis.helpers._state import read_json, state_path, write_json
from analysis.review_app.batches import Batch, load_batches


class Pattern(TypedDict):
    name: str
    definition: str
    nearest_mode: NotRequired[str | None]
    boundary: NotRequired[str]
    status: str
    example_trace_ids: list[str]
    close_negative_trace_ids: NotRequired[list[str]]
    note_ids: list[str]
    close_negative_note_ids: NotRequired[list[str]]


class BatchCount(TypedDict):
    batch: int
    count: int


class ModeView(TypedDict):
    name: str
    definition: str
    nearest_mode: str | None
    boundary: str | None
    status: str
    batch_counts: list[BatchCount]
    total: int
    note_ids: list[str]
    example_trace_ids: list[str]
    close_negative_trace_ids: list[str]
    close_negative_note_ids: list[str]


class UnknownMode(LookupError):
    """No mode in patterns.json has this name."""


class BadBoundary(ValueError):
    """The boundary's nearest mode or text can't be saved."""


def list_modes() -> list[ModeView]:
    """Return every failure mode, in the order patterns.json lists them."""
    patterns = _patterns()
    batch_of = _batch_numbers(load_batches())
    return [_view(pattern, batch_of) for pattern in patterns]


def save_boundary(name: str, nearest_mode: str | None, boundary: str) -> ModeView:
    """Write a mode's nearest mode (None when it has no close neighbour) and boundary, and return the mode."""
    patterns = _patterns()
    pattern = _find(patterns, name)
    text = _checked_boundary(patterns, name, nearest_mode, boundary)
    _write(patterns, pattern, nearest_mode, text)
    return _view(pattern, _batch_numbers(load_batches()))


def _patterns() -> list[Pattern]:
    saved: dict[str, list[Pattern]] = read_json(state_path("patterns.json"), default={"modes": []})
    return saved["modes"]


def _find(patterns: list[Pattern], name: str) -> Pattern:
    for pattern in patterns:
        if pattern["name"] == name:
            return pattern
    raise UnknownMode(name)


def _checked_boundary(patterns: list[Pattern], name: str, nearest_mode: str | None, boundary: str) -> str:
    if nearest_mode == name:
        raise BadBoundary(f"{name} can't be its own nearest mode (itself)")
    if nearest_mode is not None and nearest_mode not in {pattern["name"] for pattern in patterns}:
        raise BadBoundary(f"nearest mode {nearest_mode} is not a failure mode")
    if not boundary.strip():
        raise BadBoundary("the boundary text is empty")
    return boundary.strip()


def _write(patterns: list[Pattern], pattern: Pattern, nearest_mode: str | None, boundary: str) -> None:
    pattern["nearest_mode"] = nearest_mode
    pattern["boundary"] = boundary
    path = state_path("patterns.json")
    saved: dict[str, object] = read_json(path)
    write_json(path, {**saved, "modes": patterns})


def _batch_numbers(batches: list[Batch]) -> dict[str, int]:
    """Each batched trace's batch number: 1 for batch_1_random, and so on."""
    return {trace_id: _number(batch["name"]) for batch in batches for trace_id in batch["trace_ids"]}


def _number(batch_name: str) -> int:
    match = re.match(r"batch_(\d+)", batch_name)
    if not match:
        raise ValueError(f"batch file {batch_name} does not start with batch_<number>")
    return int(match[1])


def _view(pattern: Pattern, batch_of: dict[str, int]) -> ModeView:
    traces = pattern["example_trace_ids"]
    batches = [_batch_of(trace_id, pattern, batch_of) for trace_id in traces]
    return {
        "name": pattern["name"],
        "definition": pattern["definition"],
        "nearest_mode": pattern.get("nearest_mode"),
        "boundary": pattern.get("boundary"),
        "status": pattern["status"],
        "batch_counts": [{"batch": n, "count": batches.count(n)} for n in sorted(set(batch_of.values()))],
        "total": len(traces),
        "note_ids": pattern["note_ids"],
        "example_trace_ids": traces,
        "close_negative_trace_ids": pattern.get("close_negative_trace_ids", []),
        "close_negative_note_ids": pattern.get("close_negative_note_ids", []),
    }


def _batch_of(trace_id: str, pattern: Pattern, batch_of: dict[str, int]) -> int:
    if trace_id not in batch_of:
        raise ValueError(f"trace {trace_id} of {pattern['name']} is in no batch file")
    return batch_of[trace_id]
