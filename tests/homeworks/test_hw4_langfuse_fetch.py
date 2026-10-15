"""Fetch tests for the Homework 4 review: reading traces from Langfuse v4.

Langfuse v4 no longer serves the legacy traces endpoint; a trace is read as
its observations, page by page, through the Observations API v2. These tests
drive analysis/helpers/langfuse_io.fetch_traces against a stand-in for that
API, so everything runs offline. The stand-in returns only the field groups a
request asks for, as the real API does.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langfuse.api.core.api_error import ApiError

from analysis.helpers.langfuse_io import fetch_traces
from tests.homeworks.hw4_observations import observation

TRACE_A = "a" * 32
TRACE_B = "b" * 32
TRACE_C = "c" * 32

# The keys each requestable field group adds to an observation row.
_FIELD_GROUPS = {
    "io": ("input", "output"),
    "metadata": ("metadata",),
    "model": ("model",),
    "trace_context": ("sessionId", "tags", "traceName"),
}


class _ObservationsV2:
    """Serves observations two at a time behind a cursor.

    Each error in ``failing_with`` is raised by one request before any page
    is served again.
    """

    def __init__(
        self, rows: list[dict[str, object]], failing_with: list[ApiError] | None = None
    ) -> None:
        self._rows = rows
        self._failures = list(failing_with or [])
        self.requests = 0

    def get_many(
        self, *, limit: int, cursor: str | None = None, fields: str = ""
    ) -> SimpleNamespace:
        self.requests += 1
        if self._failures:
            raise self._failures.pop(0)
        start = int(cursor or 0)
        end = start + min(limit, 2)
        next_cursor = str(end) if end < len(self._rows) else None
        page = [_only_requested(row, fields) for row in self._rows[start:end]]
        return SimpleNamespace(data=page, meta=SimpleNamespace(cursor=next_cursor))


class _LegacyTraces:
    """The endpoint Langfuse v4 answers with 404."""

    def list(self, **_: object) -> SimpleNamespace:
        raise RuntimeError("404: the legacy traces endpoint is not served by Langfuse v4")


def _only_requested(row: dict[str, object], fields: str) -> dict[str, object]:
    requested = set(fields.split(","))
    hidden = {
        key for group, keys in _FIELD_GROUPS.items() if group not in requested for key in keys
    }
    return {key: value for key, value in row.items() if key not in hidden}


def _langfuse_serving(
    rows: list[dict[str, object]], failing_with: list[ApiError] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        api=SimpleNamespace(
            observations_v_2=_ObservationsV2(rows, failing_with), trace=_LegacyTraces()
        )
    )


def _too_busy() -> ApiError:
    """What Langfuse v4 answers when ClickHouse stops a query at its memory limit."""
    return ApiError(
        status_code=422,
        body={
            "message": "Your query could not be completed. Please narrow your request.",
            "error": "Request timed out",
        },
    )


def _rejected() -> ApiError:
    return ApiError(status_code=401, body={"message": "Invalid credentials"})


def _trace_rows(
    trace_id: str,
    said: str,
    started: str,
    *,
    scenario: str | None,
    tags: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    """The root and the one model call of a trace that used no tool."""
    attributes: dict[str, object] = {"cartwheel.user_role": "shopper"}
    if scenario:
        attributes["cartwheel.scenario_id"] = scenario
    reply = {"role": "assistant", "parts": [{"type": "text", "content": "Done."}]}
    return [
        observation(
            f"{trace_id}-root",
            "SPAN",
            "cartwheel.session_message",
            started,
            trace_id=trace_id,
            session_id=f"session-{trace_id[0]}",
            payload_in=[
                {"role": "system", "content": "You are Cartwheel's support assistant."},
                {"role": "user", "parts": [{"type": "text", "content": said}]},
            ],
            payload_out=[reply],
            attributes=attributes,
            root=True,
            tags=tags,
        ),
        observation(
            f"{trace_id}-model",
            "GENERATION",
            "openai.response",
            started,
            trace_id=trace_id,
            payload_out=[{**reply, "finish_reason": "stop"}],
            model="gpt-test",
            tags=tags,
        ),
    ]


def _two_scenario_traces() -> list[dict[str, object]]:
    """Traces A and B, with each trace's two rows landing on different pages."""
    a_root, a_model = _trace_rows(
        TRACE_A, "Where is order 12?", "2026-10-07T02:00:00.000Z", scenario="support-0001"
    )
    b_root, b_model = _trace_rows(
        TRACE_B, "Cancel order 13.", "2026-10-07T03:00:00.000Z", scenario="support-0002"
    )
    return [a_root, b_model, b_root, a_model]


def test_traces_are_assembled_from_observations_spread_over_pages() -> None:
    traces = fetch_traces(client=_langfuse_serving(_two_scenario_traces()))

    assert [trace["trace_id"] for trace in traces] == [TRACE_A, TRACE_B]
    assert [trace["trace"] for trace in traces] == [
        [{"role": "user", "text": "Where is order 12?"}, {"role": "assistant", "text": "Done."}],
        [{"role": "user", "text": "Cancel order 13."}, {"role": "assistant", "text": "Done."}],
    ]
    assert [trace["models"] for trace in traces] == [["gpt-test"], ["gpt-test"]]


def test_each_trace_starts_when_its_root_observation_started() -> None:
    traces = fetch_traces(client=_langfuse_serving(_two_scenario_traces()))

    assert [trace["timestamp"] for trace in traces] == [
        "2026-10-07T02:00:00.000Z",
        "2026-10-07T03:00:00.000Z",
    ]


def test_each_trace_keeps_its_langfuse_session() -> None:
    traces = fetch_traces(client=_langfuse_serving(_two_scenario_traces()))

    assert [trace["meta"]["session_id"] for trace in traces] == ["session-a", "session-b"]


def test_traces_without_a_scenario_id_are_left_out() -> None:
    rows = [
        *_trace_rows(TRACE_A, "Where is order 12?", "2026-10-07T02:00:00.000Z", scenario="support-0001"),
        *_trace_rows(TRACE_C, "Hello?", "2026-10-07T02:30:00.000Z", scenario=None),
    ]

    traces = fetch_traces(client=_langfuse_serving(rows))

    assert [trace["trace_id"] for trace in traces] == [TRACE_A]


def test_tag_keeps_tagged_traces_whatever_their_scenario() -> None:
    rows = [
        *_trace_rows(TRACE_A, "Where is order 12?", "2026-10-07T02:00:00.000Z", scenario="support-0001"),
        *_trace_rows(
            TRACE_C, "Hello?", "2026-10-07T02:30:00.000Z", scenario=None, tags=("error-analysis-seed",)
        ),
    ]

    traces = fetch_traces(tag="error-analysis-seed", client=_langfuse_serving(rows))

    assert [trace["trace_id"] for trace in traces] == [TRACE_C]


def test_limit_keeps_the_most_recent_traces() -> None:
    traces = fetch_traces(limit=1, client=_langfuse_serving(_two_scenario_traces()))

    assert [trace["trace_id"] for trace in traces] == [TRACE_B]


def test_a_page_langfuse_was_too_busy_to_serve_is_asked_again() -> None:
    langfuse = _langfuse_serving(_two_scenario_traces(), failing_with=[_too_busy()])

    traces = fetch_traces(client=langfuse)

    assert [trace["trace_id"] for trace in traces] == [TRACE_A, TRACE_B]


def test_langfuse_staying_too_busy_is_reported_after_three_attempts() -> None:
    langfuse = _langfuse_serving(_two_scenario_traces(), failing_with=[_too_busy()] * 5)

    with pytest.raises(ApiError):
        fetch_traces(client=langfuse)

    assert langfuse.api.observations_v_2.requests == 3


def test_a_rejected_request_is_not_asked_again() -> None:
    langfuse = _langfuse_serving(_two_scenario_traces(), failing_with=[_rejected()] * 5)

    with pytest.raises(ApiError):
        fetch_traces(client=langfuse)

    assert langfuse.api.observations_v_2.requests == 1
