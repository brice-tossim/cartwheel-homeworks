"""Tests for the review batches read by the trace review page.

analysis/review_app/batches.py reads one JSONL file per batch under
analysis/state/batches/, one line per picked trace. Each test points the state
folder at a temporary directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.review_app import batches


@pytest.fixture(autouse=True)
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(tmp_path))
    return tmp_path


def _write_batch(state_dir: Path, name: str, trace_ids: list[str], selected_at: str) -> None:
    folder = state_dir / "batches"
    folder.mkdir(exist_ok=True)
    rows = [
        {"trace_id": trace_id, "reason": "random pick", "selected_at": selected_at}
        for trace_id in trace_ids
    ]
    (folder / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_each_batch_file_gives_its_name_and_trace_ids(state_dir: Path) -> None:
    _write_batch(state_dir, "batch_1_random", ["t1", "t2"], "2026-10-20T03:43:31+00:00")

    assert batches.load_batches() == [{"name": "batch_1_random", "trace_ids": ["t1", "t2"]}]


def test_batches_are_listed_in_the_order_they_were_drawn(state_dir: Path) -> None:
    _write_batch(state_dir, "batch_1_random", ["t1"], "2026-10-20T03:00:00+00:00")
    _write_batch(state_dir, "batch_1_clusters", ["t2"], "2026-10-20T04:00:00+00:00")

    assert [batch["name"] for batch in batches.load_batches()] == [
        "batch_1_random",
        "batch_1_clusters",
    ]


def test_blank_lines_in_a_batch_file_are_skipped(state_dir: Path) -> None:
    folder = state_dir / "batches"
    folder.mkdir()
    (folder / "batch_1_random.jsonl").write_text('{"trace_id": "t1"}\n\n{"trace_id": "t2"}\n')

    assert batches.load_batches() == [{"name": "batch_1_random", "trace_ids": ["t1", "t2"]}]


def test_files_that_are_not_jsonl_are_ignored(state_dir: Path) -> None:
    _write_batch(state_dir, "batch_1_random", ["t1"], "2026-10-20T03:00:00+00:00")
    (state_dir / "batches" / "notes.md").write_text("not a batch")

    assert [batch["name"] for batch in batches.load_batches()] == ["batch_1_random"]


def test_no_batch_folder_means_no_batches() -> None:
    assert batches.load_batches() == []
