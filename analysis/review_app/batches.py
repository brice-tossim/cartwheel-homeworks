"""The review batches: which traces each batch of the review sample holds.

Each batch is one JSONL file under analysis/state/batches/, one line per
picked trace, written when the batch is drawn. The page uses them to show one
batch at a time, or the traces in no batch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from analysis.helpers._state import state_path


class Batch(TypedDict):
    name: str
    trace_ids: list[str]


type BatchRow = dict[str, object]


def load_batches() -> list[Batch]:
    """Return every batch, in the order the batches were drawn."""
    files = _batch_files(state_path("batches"))
    drawn = [(file.stem, _rows(file)) for file in files]
    return [_batch(name, rows) for name, rows in sorted(drawn, key=_draw_order)]


def _batch_files(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def _rows(file: Path) -> list[BatchRow]:
    lines = file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _draw_order(drawn: tuple[str, list[BatchRow]]) -> tuple[str, str]:
    """Earliest pick time first; the name breaks ties and orders undated files."""
    name, rows = drawn
    times = [str(row["selected_at"]) for row in rows if row.get("selected_at")]
    return (min(times, default=""), name)


def _batch(name: str, rows: list[BatchRow]) -> Batch:
    return {"name": name, "trace_ids": [str(row["trace_id"]) for row in rows]}
