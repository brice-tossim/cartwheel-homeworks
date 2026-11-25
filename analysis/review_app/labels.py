"""The Label tab's decisions: one present (1) or absent (0) label per trace and final mode.

Saving a turn writes each decision to Langfuse as a score named after the mode,
under a fixed score id, so a changed decision replaces the earlier score. It
then appends a line to analysis/state/labels/<mode>.jsonl when the label is new
or changed. The local files are append-only: the last line for a trace wins and
earlier lines stay as the history. Langfuse is written first, so a failed save
leaves the local files untouched and can be retried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict

from analysis.helpers import langfuse_io
from analysis.helpers._state import append_jsonl, read_json, read_jsonl, state_path


class ScoreWriter(Protocol):
    def __call__(self, trace_id: str, mode: str, label: int, *, score_id: str) -> str: ...


class LabelLine(TypedDict):
    trace_id: str
    label: int
    source: str
    ts: str
    label_id: str
    superseded_by: NotRequired[str]


class SavedLabel(TypedDict):
    trace_id: str
    mode: str
    label: int
    ts: str


class BadDecisions(ValueError):
    """The decisions are not one 0 or 1 for every final mode."""


def list_labels() -> list[SavedLabel]:
    """Return the current label of every labeled trace, for each final mode."""
    return [saved for mode in _mode_names() for saved in _current(mode).values()]


def save_decisions(
    trace_id: str,
    decisions: dict[str, object],
    write_score: ScoreWriter = langfuse_io.post_label_score,
) -> list[SavedLabel]:
    """Save one turn's decisions to Langfuse, then to the local label files."""
    checked = _checked(decisions, _mode_names())
    _write_scores(trace_id, checked, write_score)
    _append_changed(trace_id, checked)
    return [_current(mode)[trace_id] for mode in checked]


def _mode_names() -> list[str]:
    patterns: dict[str, list[dict[str, object]]] = read_json(state_path("patterns.json"), default={"modes": []})
    return [str(mode["name"]) for mode in patterns["modes"]]


def _checked(decisions: dict[str, object], modes: list[str]) -> dict[str, int]:
    unknown = sorted(set(decisions) - set(modes))
    missing = [mode for mode in modes if mode not in decisions]
    if unknown or missing:
        raise BadDecisions(f"unknown modes {unknown}, missing modes {missing}")
    return {mode: _as_label(mode, decisions[mode]) for mode in modes}


def _as_label(mode: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise BadDecisions(f"the label for {mode} must be 0 or 1, not {value!r}")
    return value


def _write_scores(trace_id: str, decisions: dict[str, int], write_score: ScoreWriter) -> None:
    for mode, label in decisions.items():
        write_score(trace_id, mode, label, score_id=f"{trace_id}-{mode}")


def _append_changed(trace_id: str, decisions: dict[str, int]) -> None:
    for mode, label in decisions.items():
        lines = _lines(mode)
        current = _current_from(mode, lines).get(trace_id)
        if current is None or current["label"] != label:
            append_jsonl(_path(mode), _line(trace_id, label, lines))


def _line(trace_id: str, label: int, lines: list[LabelLine]) -> LabelLine:
    earlier = sum(1 for line in lines if line["trace_id"] == trace_id)
    return {
        "trace_id": trace_id,
        "label": label,
        "source": "human",
        "ts": datetime.now(UTC).isoformat(),
        "label_id": f"{trace_id}#{earlier}",
    }


def _current(mode: str) -> dict[str, SavedLabel]:
    return _current_from(mode, _lines(mode))


def _current_from(mode: str, lines: list[LabelLine]) -> dict[str, SavedLabel]:
    """The last line written for each trace wins; a line marked superseded never does."""
    live = [line for line in lines if not line.get("superseded_by")]
    return {line["trace_id"]: _saved(mode, line) for line in live}


def _saved(mode: str, line: LabelLine) -> SavedLabel:
    return {"trace_id": line["trace_id"], "mode": mode, "label": line["label"], "ts": line["ts"]}


def _lines(mode: str) -> list[LabelLine]:
    rows: list[LabelLine] = read_jsonl(_path(mode))
    return rows


def _path(mode: str) -> Path:
    return state_path("labels", f"{mode}.jsonl")
