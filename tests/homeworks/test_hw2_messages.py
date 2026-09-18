"""Edge-case tests for the Homework 2 traced message route in server/app.py.

No instructor contract test covers post_message; the handout checks its root
span by eye in Langfuse (Part E). These tests pin the same contract offline: a
rejected token never reaches the agent, the reply comes back with the session
and prompt version, the agent runs inside the cartwheel.session_message root
span, that span records the caller, session, prompt version, and any scenario
id, the OTel GenAI messages and system prompt follow the content-capture
setting, the requested model is used, and a session keeps its history across
messages. A scripted
FakeModel stands in for the provider and an in-memory exporter for Langfuse.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass

import pytest
from agents import SQLiteSession
from fastapi import HTTPException
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext

from agent import agent as support
from agent.auth import AuthContext
from server import app as server_app
from tests.eval.fake_model import FakeModel, text_message

SessionStore = dict[str, tuple[AuthContext, SQLiteSession]]

MESSAGE = "Show my recent orders."
REPLY = "Here are your recent orders."


@dataclass(frozen=True)
class Harness:
    """What a message test scripts and inspects around the server."""

    model: FakeModel
    exporter: InMemorySpanExporter
    requested_models: list[str | None]
    active_spans: list[SpanContext]

    def root_span(self) -> ReadableSpan:
        (root,) = [
            span
            for span in self.exporter.get_finished_spans()
            if span.name == "cartwheel.session_message"
        ]
        return root

    def root_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = dict(self.root_span().attributes or {})
        return attributes


def _noting_active_span[**P, R](
    call: Callable[P, Awaitable[R]], seen: list[SpanContext]
) -> Callable[P, Awaitable[R]]:
    """Wrap a model call so a test can see which span was active during it."""

    async def call_noting_span(*args: P.args, **kwargs: P.kwargs) -> R:
        seen.append(trace.get_current_span().get_span_context())
        return await call(*args, **kwargs)

    return call_noting_span


@pytest.fixture
def harness(
    server_sessions: SessionStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Harness]:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(server_app, "_tracer", provider.get_tracer(__name__))
    monkeypatch.setenv("TRACELOOP_TRACE_CONTENT", "true")

    model = FakeModel()
    requested_models: list[str | None] = []
    active_spans: list[SpanContext] = []
    monkeypatch.setattr(
        model, "get_response", _noting_active_span(model.get_response, active_spans)
    )

    def resolve_model(name: str | None) -> FakeModel:
        requested_models.append(name)
        return model

    monkeypatch.setattr(support, "resolve_model", resolve_model)
    yield Harness(model, exporter, requested_models, active_spans)
    provider.shutdown()


def _open_session(user_id: int, role: str) -> tuple[str, str]:
    created = server_app.create_session(
        server_app.SessionCreate(user_id=user_id, role=role)
    )
    return created["session_id"], f"Bearer {created['token']}"


def _send(
    session_id: str,
    authorization: str | None,
    *,
    message: str = MESSAGE,
    model: str | None = None,
    scenario_id: str | None = None,
) -> dict[str, str]:
    body = server_app.MessageIn(message=message, model=model, scenario_id=scenario_id)
    return asyncio.run(
        server_app.post_message(session_id, body, authorization=authorization)
    )


def _json_attribute(attributes: dict[str, object], name: str) -> object:
    value = attributes[name]
    assert isinstance(value, str), f"{name} must be recorded as a JSON string"
    return json.loads(value)


@pytest.mark.parametrize(
    ("case", "status"),
    [("missing", 401), ("forged", 401), ("another-session", 403), ("unknown-session", 404)],
)
def test_a_rejected_token_never_reaches_the_agent(
    harness: Harness, case: str, status: int
) -> None:
    session_id, _ = _open_session(1, "shopper")
    _, other_token = _open_session(2, "shopper")
    unknown_token = server_app.create_token({"session_id": "no-such-session"})
    target, authorization = {
        "missing": (session_id, None),
        "forged": (session_id, "Bearer forged.signature"),
        "another-session": (session_id, other_token),
        "unknown-session": ("no-such-session", f"Bearer {unknown_token}"),
    }[case]

    with pytest.raises(HTTPException) as rejected:
        _send(target, authorization)

    assert rejected.value.status_code == status
    assert harness.model.requests == []


def test_reply_comes_back_with_the_session_and_prompt_version(harness: Harness) -> None:
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    response = _send(session_id, token)

    assert response["session_id"] == session_id
    assert response["reply"] == REPLY
    # Only the template is hashed: the rendered prompt differs for every caller.
    assert response["prompt_version"] == support.prompt_version()


def test_agent_runs_inside_the_root_span(harness: Harness) -> None:
    """Model and tool spans join the request's trace only if the run is inside it."""
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    root = harness.root_span().context
    assert root is not None
    assert [seen.span_id for seen in harness.active_spans] == [root.span_id]


def test_root_span_records_the_caller_session_and_prompt_version(harness: Harness) -> None:
    session_id, token = _open_session(9001, "merchant")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    attributes = harness.root_attributes()
    assert attributes["cartwheel.user_role"] == "merchant"
    assert attributes["cartwheel.user_id"] == "9001"
    assert attributes["cartwheel.prompt_version"] == support.prompt_version()
    assert attributes["session.id"] == session_id


@pytest.mark.parametrize(
    ("scenario_id", "recorded"),
    [("fm-017", "fm-017"), (None, None), ("", None)],
    ids=["supplied", "absent", "empty"],
)
def test_scenario_id_is_recorded_only_when_supplied(
    harness: Harness, scenario_id: str | None, recorded: str | None
) -> None:
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token, scenario_id=scenario_id)

    assert harness.root_attributes().get("cartwheel.scenario_id") == recorded


def test_messages_are_recorded_in_the_otel_genai_format(harness: Harness) -> None:
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    attributes = harness.root_attributes()
    assert _json_attribute(attributes, "gen_ai.input.messages") == [
        {"role": "user", "parts": [{"type": "text", "content": MESSAGE}]}
    ]
    assert _json_attribute(attributes, "gen_ai.output.messages") == [
        {"role": "assistant", "parts": [{"type": "text", "content": REPLY}]}
    ]


def test_messages_are_left_out_when_content_capture_is_off(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRACELOOP_TRACE_CONTENT", "false")
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    attributes = harness.root_attributes()
    assert "gen_ai.input.messages" not in attributes
    assert "gen_ai.output.messages" not in attributes


def test_the_system_prompt_the_model_received_is_recorded(harness: Harness) -> None:
    """Langfuse shows gen_ai.system_instructions as the root span's System message."""
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    (request,) = harness.model.requests
    assert _json_attribute(harness.root_attributes(), "gen_ai.system_instructions") == [
        {"type": "text", "content": request["system_instructions"]}
    ]


def test_the_system_prompt_is_left_out_when_content_capture_is_off(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRACELOOP_TRACE_CONTENT", "false")
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token)

    assert "gen_ai.system_instructions" not in harness.root_attributes()


def test_the_requested_model_is_used(harness: Harness) -> None:
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])

    _send(session_id, token, model="gpt-5.5")

    assert harness.requested_models == ["gpt-5.5"]


def test_a_session_keeps_its_history_across_messages(harness: Harness) -> None:
    session_id, token = _open_session(1, "shopper")
    harness.model.set_next_output([text_message(REPLY)])
    harness.model.set_next_output([text_message("You're welcome.")])

    _send(session_id, token, message=MESSAGE)
    _send(session_id, token, message="Thanks!")

    second_request = str(harness.model.requests[1]["input"])
    assert MESSAGE in second_request
    assert REPLY in second_request
