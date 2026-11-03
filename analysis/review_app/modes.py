"""The failure modes the review page shows, read from patterns.json.

patterns.json is the single source of the failure modes. Each mode comes back
with its definition, how many of its traces fall in each review batch, its
total, and the ids of the notes that support it. Batches sharing a number
(batch_1_random, batch_1_clusters) count as one batch.
"""

from __future__ import annotations

import re
from typing import TypedDict

from analysis.helpers._state import read_json, state_path
from analysis.review_app.batches import Batch, load_batches


class Pattern(TypedDict):
    name: str
    definition: str
    status: str
    example_trace_ids: list[str]
    note_ids: list[str]


class BatchCount(TypedDict):
    batch: int
    count: int


class ModeView(TypedDict):
    name: str
    definition: str
    status: str
    batch_counts: list[BatchCount]
    total: int
    note_ids: list[str]


def list_modes() -> list[ModeView]:
    """Return every failure mode, in the order patterns.json lists them."""
    patterns = _patterns()
    batch_of = _batch_numbers(load_batches())
    return [_view(pattern, batch_of) for pattern in patterns]


def _patterns() -> list[Pattern]:
    saved: dict[str, list[Pattern]] = read_json(state_path("patterns.json"), default={"modes": []})
    return saved["modes"]


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
        "status": pattern["status"],
        "batch_counts": [{"batch": n, "count": batches.count(n)} for n in sorted(set(batch_of.values()))],
        "total": len(traces),
        "note_ids": pattern["note_ids"],
    }


def _batch_of(trace_id: str, pattern: Pattern, batch_of: dict[str, int]) -> int:
    if trace_id not in batch_of:
        raise ValueError(f"trace {trace_id} of {pattern['name']} is in no batch file")
    return batch_of[trace_id]
