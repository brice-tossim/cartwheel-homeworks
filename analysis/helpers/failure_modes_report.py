"""Write the failure-mode report from patterns.json.

patterns.json is the single source of the failure modes. This writes the
readable table in analysis/report/failure_modes.md from it: each mode's
definition, how many of its traces fall in each review batch, and the total.
Batches sharing a number (batch_1_random, batch_1_clusters) share a column.

    uv run python -m analysis.helpers.failure_modes_report
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from analysis.helpers._state import read_json, state_path
from analysis.review_app.batches import Batch, load_batches

REPORT_PATH = Path(__file__).resolve().parents[1] / "report" / "failure_modes.md"


class Mode(TypedDict):
    name: str
    definition: str
    example_trace_ids: list[str]


def write(output: Path = REPORT_PATH) -> None:
    """Write the failure-mode table to ``output``."""
    modes = _modes()
    batch_of = _batch_numbers(load_batches())
    output.write_text(_report(modes, batch_of))


def _modes() -> list[Mode]:
    patterns: dict[str, list[Mode]] = read_json(state_path("patterns.json"), default={"modes": []})
    return patterns["modes"]


def _batch_numbers(batches: list[Batch]) -> dict[str, int]:
    """Each batched trace's batch number: 1 for batch_1_random, and so on."""
    return {trace_id: _number(batch["name"]) for batch in batches for trace_id in batch["trace_ids"]}


def _number(batch_name: str) -> int:
    match = re.match(r"batch_(\d+)", batch_name)
    if not match:
        raise ValueError(f"batch file {batch_name} does not start with batch_<number>")
    return int(match[1])


def _report(modes: list[Mode], batch_of: dict[str, int]) -> str:
    numbers = sorted(set(batch_of.values()))
    lines = [
        "# Failure modes",
        "",
        "Generated from `analysis/state/patterns.json`; edit that file, then run "
        "`uv run python -m analysis.helpers.failure_modes_report`.",
        "",
        "| Mode | Fails when… | " + "".join(f"Batch {n} | " for n in numbers) + "Total |",
        "|---|---|" + "---:|" * (len(numbers) + 1),
        *(_row(mode, batch_of, numbers) for mode in modes),
    ]
    return "\n".join(lines) + "\n"


def _row(mode: Mode, batch_of: dict[str, int], numbers: list[int]) -> str:
    traces = mode["example_trace_ids"]
    batches = [_batch_of(trace_id, mode, batch_of) for trace_id in traces]
    counts = [batches.count(n) for n in numbers] + [len(traces)]
    return f"| `{mode['name']}` | {mode['definition']} | " + "".join(f"{count} | " for count in counts).rstrip()


def _batch_of(trace_id: str, mode: Mode, batch_of: dict[str, int]) -> int:
    if trace_id not in batch_of:
        raise ValueError(f"trace {trace_id} of {mode['name']} is in no batch file")
    return batch_of[trace_id]


if __name__ == "__main__":
    write()
