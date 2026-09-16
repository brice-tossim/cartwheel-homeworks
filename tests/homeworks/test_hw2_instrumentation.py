"""Edge-case tests for the Homework 2 instrumentation in observability/instrument.py.

tests/test_hw_holes.py holds the instructor contract test for `create_session`,
but nothing there covers `record_tool_result`. These tests cover the rest of its
docstring: the caller identity written as decimal strings, `store_id` only for
merchants, the permission decision recorded on every call, and odd tool results
that must not be mistaken for a denial. Everything runs offline against an
in-memory span exporter: no Langfuse, no Docker, no model provider key.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent.auth import AuthContext, permission_denied
from observability.instrument import record_tool_result

SHOPPER_1 = AuthContext(user_id=1, role="shopper")
MERCHANT_STORE_2 = AuthContext(user_id=9002, role="merchant", store_id=2)
SUPPORT = AuthContext(user_id=9501, role="support")

DENIAL_REASON = "merchants may only view their own store's orders"

# What a tool returns, and what a tool span carries afterwards.
ToolResult = dict[str, object]
SpanAttributes = dict[str, object]
Recorder = Callable[[AuthContext, ToolResult], SpanAttributes]


@pytest.fixture
def record() -> Iterator[Recorder]:
    """Run one tool call under a recording span and return its attributes.

    The supplied wrappers in agent/agent.py call `record_tool_result` while
    OpenLLMetry's tool span is active. This stands in for that span so the
    attributes can be read back without an exporter to a trace backend.
    """
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    def run(ctx: AuthContext, result: ToolResult) -> SpanAttributes:
        with tracer.start_as_current_span("execute_tool"):
            record_tool_result(ctx, result)
        # A span that was given no attributes at all reports None, not {}.
        recorded = exporter.get_finished_spans()[-1].attributes or {}
        attributes: SpanAttributes = dict(recorded)
        return attributes

    yield run
    provider.shutdown()


def test_identity_is_recorded_as_decimal_strings(record: Recorder) -> None:
    attributes = record(SHOPPER_1, {"ok": True, "orders": []})

    assert attributes["cartwheel.user_role"] == "shopper"
    assert attributes["cartwheel.user_id"] == "1"


def test_store_id_is_recorded_only_for_merchants(record: Recorder) -> None:
    merchant = record(MERCHANT_STORE_2, {"ok": True, "orders": []})
    support = record(SUPPORT, {"ok": True, "orders": []})

    assert merchant["cartwheel.store_id"] == "2"
    # None is not a legal attribute value, so the key is absent, not empty.
    assert "cartwheel.store_id" not in support
    assert "cartwheel.store_id" not in record(SHOPPER_1, {"ok": True})


def test_allowed_call_records_a_false_decision_with_no_reason(record: Recorder) -> None:
    """The decision is recorded on every call, so denials stay countable."""
    attributes = record(SHOPPER_1, {"ok": True, "orders": []})

    assert attributes["cartwheel.permission_denied"] is False
    assert "cartwheel.permission_denied.reason" not in attributes


def test_denied_call_records_the_decision_and_its_reason(record: Recorder) -> None:
    attributes = record(MERCHANT_STORE_2, permission_denied(DENIAL_REASON))

    assert attributes["cartwheel.permission_denied"] is True
    assert attributes["cartwheel.permission_denied.reason"] == DENIAL_REASON


def test_denial_without_a_reason_records_an_empty_string(record: Recorder) -> None:
    attributes = record(SHOPPER_1, {"ok": False, "error": "permission_denied"})

    assert attributes["cartwheel.permission_denied"] is True
    assert attributes["cartwheel.permission_denied.reason"] == ""


@pytest.mark.parametrize(
    "result",
    [
        {"ok": False, "error": "not_found", "reason": "no such order"},
        {"ok": False, "error": "not_eligible", "reason": "past the return window"},
        {"ok": False, "error": "invalid_argument", "reason": "limit must be positive"},
        {"ok": False, "error": "not_implemented", "reason": "HW1 stub"},
        {},
    ],
    ids=["not_found", "not_eligible", "invalid_argument", "not_implemented", "empty"],
)
def test_other_failures_are_not_permission_denials(
    record: Recorder, result: ToolResult
) -> None:
    """Only the permission_denied code counts; odd input must not raise."""
    attributes = record(SUPPORT, result)

    assert attributes["cartwheel.permission_denied"] is False
    assert "cartwheel.permission_denied.reason" not in attributes


def test_recording_is_a_no_op_when_tracing_is_off() -> None:
    """Outside a recording span the helper returns without touching anything."""
    assert isinstance(trace.get_current_span(), trace.NonRecordingSpan)

    record_tool_result(MERCHANT_STORE_2, permission_denied(DENIAL_REASON))
