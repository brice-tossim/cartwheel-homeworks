"""Tests for the failure-mode report written from patterns.json.

The report is one Markdown table: each mode's name and definition, then how
many of its traces fall in each review batch, then the total. Batches with the
same number (batch_1_random, batch_1_clusters) share one column.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from analysis.helpers import failure_modes_report


def _write_batch(state: Path, name: str, trace_ids: list[str], selected_at: str) -> None:
    rows = [{"trace_id": trace_id, "selected_at": selected_at} for trace_id in trace_ids]
    (state / "batches" / f"{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def _mode(name: str, definition: str, traces: list[str]) -> dict[str, object]:
    return {"name": name, "definition": definition, "status": "candidate", "example_trace_ids": traces}


@pytest.fixture
def state(analysis_state: Path) -> Path:
    shutil.rmtree(analysis_state / "batches", ignore_errors=True)
    (analysis_state / "batches").mkdir()
    _write_batch(analysis_state, "batch_1_random", ["t1", "t2"], "2026-10-20T00:00:00+00:00")
    _write_batch(analysis_state, "batch_1_clusters", ["t3"], "2026-10-21T00:00:00+00:00")
    _write_batch(analysis_state, "batch_2_roles", ["t4", "t5"], "2026-10-22T00:00:00+00:00")
    modes = [
        _mode("no_reply", "The turn ends without any reply to the customer.", ["t1", "t3", "t4"]),
        _mode("date_errors", "The reply uses the wrong current date (`world_asof`).", ["t5"]),
        _mode("shows_others_orders", "The reply shows another caller's orders.", []),
    ]
    (analysis_state / "patterns.json").write_text(json.dumps({"modes": modes}))
    return analysis_state


def test_the_report_lists_each_mode_with_its_count_per_batch(state: Path, tmp_path: Path) -> None:
    output = tmp_path / "failure_modes.md"

    failure_modes_report.write(output)

    assert output.read_text() == (
        "# Failure modes\n"
        "\n"
        "Generated from `analysis/state/patterns.json`; edit that file, then run "
        "`uv run python -m analysis.helpers.failure_modes_report`.\n"
        "\n"
        "| Mode | Fails when… | Batch 1 | Batch 2 | Total |\n"
        "|---|---|---:|---:|---:|\n"
        "| `no_reply` | The turn ends without any reply to the customer. | 2 | 1 | 3 |\n"
        "| `date_errors` | The reply uses the wrong current date (`world_asof`). | 0 | 1 | 1 |\n"
        "| `shows_others_orders` | The reply shows another caller's orders. | 0 | 0 | 0 |\n"
    )


def test_a_trace_in_no_batch_is_refused(state: Path, tmp_path: Path) -> None:
    patterns = json.loads((state / "patterns.json").read_text())
    patterns["modes"][0]["example_trace_ids"].append("unbatched")
    (state / "patterns.json").write_text(json.dumps(patterns))

    with pytest.raises(ValueError, match="unbatched"):
        failure_modes_report.write(tmp_path / "failure_modes.md")
