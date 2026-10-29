"""Read-back tests for the Homework 4 labels saved as Langfuse scores.

Langfuse v4 answers the v2 scores endpoint with 404; scores are read through
GET /api/public/v3/scores, which pages with a cursor, rejects parameters it
does not know, and returns a score's comment only when the ``details`` field
group is asked for. These tests serve that API from a stand-in HTTP transport,
so everything runs offline.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from analysis.helpers import langfuse_io

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
OTHER_TRACE_ID = "1bf8762a27de54ee9559fc322d91420d"

_KNOWN_PARAMETERS = {"traceId", "name", "fields", "limit", "cursor"}

# Scores as Langfuse stores them; the stand-in serves one per page.
_STORED_SCORES = [
    {
        "id": "score-1",
        "name": "unconfirmed_write",
        "value": 1,
        "dataType": "NUMERIC",
        "traceId": TRACE_ID,
        "comment": "the reply claims the refund is done; the tool queued it",
    },
    {
        "id": "score-2",
        "name": "missing_citation",
        "value": 0,
        "dataType": "NUMERIC",
        "traceId": TRACE_ID,
        "comment": None,
    },
    {
        "id": "score-3",
        "name": "unconfirmed_write",
        "value": 0,
        "dataType": "NUMERIC",
        "traceId": OTHER_TRACE_ID,
        "comment": None,
    },
]


def _v3_score(stored: dict[str, object], fields: set[str]) -> dict[str, object]:
    """One score as v3 returns it: a lean core, plus ``comment`` under ``details``."""
    core = {
        "id": stored["id"],
        "projectId": "project-1",
        "name": stored["name"],
        "value": stored["value"],
        "dataType": stored["dataType"],
        "source": "API",
        "timestamp": "2026-10-13T10:00:00.000Z",
        "environment": "default",
        "createdAt": "2026-10-13T10:00:00.000Z",
        "updatedAt": "2026-10-13T10:00:00.000Z",
    }
    if "details" in fields:
        core.update({"comment": stored["comment"], "configId": None, "metadata": {}})
    return core


def _scores_v3(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    if request.url.path != "/api/public/v3/scores":
        return httpx.Response(404, json={"message": "Not found"})
    unknown = sorted(set(params) - _KNOWN_PARAMETERS)
    if unknown:
        return httpx.Response(400, json={"message": "Invalid request data", "keys": unknown})
    fields = set(params.get("fields", "").split(","))
    matching = [
        stored
        for stored in _STORED_SCORES
        if stored["traceId"] in params.get("traceId", "").split(",")
        and ("name" not in params or stored["name"] in params["name"].split(","))
    ]
    position = int(params.get("cursor", 0))
    meta: dict[str, object] = {"limit": int(params.get("limit", 50))}
    if position + 1 < len(matching):
        meta["cursor"] = str(position + 1)
    page = [_v3_score(stored, fields) for stored in matching[position : position + 1]]
    return httpx.Response(200, content=json.dumps({"data": page, "meta": meta}))


@pytest.fixture
def langfuse_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the score reads to the stand-in v3 API."""
    monkeypatch.setattr(
        langfuse_io,
        "_scores_http",
        lambda: httpx.Client(
            base_url="http://langfuse.test", transport=httpx.MockTransport(_scores_v3)
        ),
    )


@pytest.mark.usefixtures("langfuse_scores")
def test_label_scores_are_read_back_through_the_v3_scores_api() -> None:
    scores = langfuse_io.read_label_scores(TRACE_ID, client=SimpleNamespace())

    assert scores == [
        {
            "name": "unconfirmed_write",
            "value": 1,
            "comment": "the reply claims the refund is done; the tool queued it",
        },
        {"name": "missing_citation", "value": 0, "comment": None},
    ]


@pytest.mark.usefixtures("langfuse_scores")
def test_label_scores_can_be_limited_to_one_failure_mode() -> None:
    scores = langfuse_io.read_label_scores(
        TRACE_ID, mode="missing_citation", client=SimpleNamespace()
    )

    assert scores == [{"name": "missing_citation", "value": 0, "comment": None}]
