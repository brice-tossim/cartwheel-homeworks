"""Tests for saving the Label tab's decisions (analysis/review_app/labels.py).

A turn's decisions are one present (1) or absent (0) label per final mode.
Saving writes each one to Langfuse as a score named after the mode, with a
fixed score id so a changed decision replaces the earlier score, and appends
a line to analysis/state/labels/<mode>.jsonl when the label is new or changed.
A stand-in score writer keeps everything offline.
"""

from __future__ import annotations

import json
from pathlib import Path
import httpx

import pytest

from analysis.helpers import langfuse_io
from analysis.review_app import labels

TRACE = "0af7651916cd43dd8448eb211c80319c"
OTHER = "1bf8762a27de54ee9559fc322d91420d"


class _Scores:
    """Stands in for langfuse_io.write_label_score and records each call."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, int, str]] = []
        self.fail = fail

    def __call__(self, trace_id: str, mode: str, label: int, *, score_id: str) -> str:
        if self.fail:
            raise ConnectionError("Langfuse refused the connection")
        self.calls.append((trace_id, mode, label, score_id))
        return trace_id


@pytest.fixture
def state(analysis_state: Path) -> Path:
    modes = [{"name": "no_reply", "note_ids": []}, {"name": "date_errors", "note_ids": []}]
    (analysis_state / "patterns.json").write_text(json.dumps({"modes": modes}))
    for name in ("no_reply", "date_errors"):
        (analysis_state / "labels" / f"{name}.jsonl").unlink(missing_ok=True)
    return analysis_state


def _lines(state: Path, mode: str) -> list[dict[str, object]]:
    path = state / "labels" / f"{mode}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_saving_writes_one_score_per_mode(state: Path) -> None:
    scores = _Scores()

    labels.save_decisions(TRACE, {"no_reply": 1, "date_errors": 0}, write_score=scores)

    assert scores.calls == [
        (TRACE, "no_reply", 1, f"{TRACE}-no_reply"),
        (TRACE, "date_errors", 0, f"{TRACE}-date_errors"),
    ]


def test_saving_appends_a_human_label_line_per_mode(state: Path) -> None:
    labels.save_decisions(TRACE, {"no_reply": 1, "date_errors": 0}, write_score=_Scores())

    [line] = _lines(state, "no_reply")
    assert (line["trace_id"], line["label"], line["source"], line["label_id"]) == (TRACE, 1, "human", f"{TRACE}#0")
    assert [row["label"] for row in _lines(state, "date_errors")] == [0]


def test_saved_labels_are_listed_per_trace_and_mode(state: Path) -> None:
    labels.save_decisions(TRACE, {"no_reply": 1, "date_errors": 0}, write_score=_Scores())
    labels.save_decisions(OTHER, {"no_reply": 0, "date_errors": 0}, write_score=_Scores())

    listed = {(row["trace_id"], row["mode"]): row["label"] for row in labels.list_labels()}

    assert listed == {(TRACE, "no_reply"): 1, (TRACE, "date_errors"): 0, (OTHER, "no_reply"): 0, (OTHER, "date_errors"): 0}


def test_a_changed_decision_appends_a_line_and_wins(state: Path) -> None:
    labels.save_decisions(TRACE, {"no_reply": 1, "date_errors": 0}, write_score=_Scores())
    labels.save_decisions(TRACE, {"no_reply": 0, "date_errors": 0}, write_score=_Scores())

    assert [(row["label"], row["label_id"]) for row in _lines(state, "no_reply")] == [(1, f"{TRACE}#0"), (0, f"{TRACE}#1")]
    assert len(_lines(state, "date_errors")) == 1
    listed = {(row["trace_id"], row["mode"]): row["label"] for row in labels.list_labels()}
    assert listed[(TRACE, "no_reply")] == 0


def test_decisions_must_cover_every_final_mode(state: Path) -> None:
    with pytest.raises(labels.BadDecisions, match="date_errors"):
        labels.save_decisions(TRACE, {"no_reply": 1}, write_score=_Scores())


@pytest.mark.parametrize(
    "decisions",
    [{"no_reply": 1, "date_errors": 2}, {"no_reply": 1, "date_errors": True}, {"no_reply": 1, "date_errors": 0, "made_up": 1}],
)
def test_only_0_or_1_for_known_modes_is_accepted(state: Path, decisions: dict[str, object]) -> None:
    scores = _Scores()

    with pytest.raises(labels.BadDecisions):
        labels.save_decisions(TRACE, decisions, write_score=scores)

    assert scores.calls == []


def test_nothing_is_saved_locally_when_langfuse_fails(state: Path) -> None:
    with pytest.raises(ConnectionError):
        labels.save_decisions(TRACE, {"no_reply": 1, "date_errors": 0}, write_score=_Scores(fail=True))

    assert _lines(state, "no_reply") == []


def _http(status: int, sent: list[httpx.Request]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, json={"id": "x"})

    return httpx.Client(base_url="http://langfuse.test", transport=httpx.MockTransport(answer))


def test_a_score_is_posted_to_langfuse_with_its_fixed_id() -> None:
    sent: list[httpx.Request] = []

    langfuse_io.post_label_score(TRACE, "no_reply", 1, score_id=f"{TRACE}-no_reply", http=_http(200, sent))

    [request] = sent
    assert (request.method, request.url.path) == ("POST", "/api/public/scores")
    assert json.loads(request.content) == {
        "id": f"{TRACE}-no_reply", "traceId": TRACE, "name": "no_reply", "value": 1, "dataType": "NUMERIC",
    }


def test_a_score_langfuse_refuses_raises() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        langfuse_io.post_label_score(TRACE, "no_reply", 1, score_id=f"{TRACE}-no_reply", http=_http(500, []))
