"""Loader tests for the Homework 4 review: the Langfuse observations export.

Langfuse v4 serves a trace as the list of its observations (Observations API
v2), which is also what scenarios/export_langfuse.py writes to
traces/support_traces.json. Nothing sits at trace level in that shape: the
customer message, the final reply, the session and the caller's role live on
the root observation, and every payload is JSON text. These tests pin how
analysis/helpers/normalization.py reads that shape, using one hand-written
trace. Everything runs offline.
"""

from __future__ import annotations

from analysis.helpers.normalization import normalize_trace
from tests.homeworks.hw4_observations import SESSION_ID, TRACE_ID, observation

SYSTEM_PROMPT = (
    "You are Cartwheel's support assistant.\n\n"
    "## Session context\n- User role: merchant\n- User id: 9001\n- Store id: 16"
)
CUSTOMER_MESSAGE = {"role": "user", "parts": [{"type": "text", "content": "Where is order 12?"}]}
FINAL_REPLY = {"role": "assistant", "parts": [{"type": "text", "content": "Order 12 has shipped."}]}

USER_STEP = {"role": "user", "text": "Where is order 12?"}
REASON_STEP = {"role": "assistant", "text": "I will look up order 12."}
TOOL_CALL_STEP = {"role": "tool_call", "name": "get_order", "arguments": {"order_id": 12}}
TOOL_RESULT_STEP = {
    "role": "tool_result",
    "name": "get_order",
    "content": {"ok": True, "order": {"order_id": 12, "status": "shipped"}},
}
REPLY_STEP = {"role": "assistant", "text": "Order 12 has shipped."}


def _root(*, reply: object = FINAL_REPLY) -> dict[str, object]:
    return observation(
        "root",
        "SPAN",
        "cartwheel.session_message",
        "2026-10-07T02:07:00.000Z",
        payload_in=[{"role": "system", "content": SYSTEM_PROMPT}, CUSTOMER_MESSAGE],
        payload_out=None if reply is None else [reply],
        attributes={
            "cartwheel.prompt_version": "abc123",
            "cartwheel.scenario_id": "support-0001",
            "cartwheel.user_id": 9001,
            "cartwheel.user_role": "merchant",
            "session.id": SESSION_ID,
        },
        root=True,
    )


def _wrappers() -> list[dict[str, object]]:
    """The two empty rows the agent framework adds to every trace."""
    return [
        observation("workflow", "SPAN", "Agent Workflow", "2026-10-07T02:07:00.100Z"),
        observation("agent", "AGENT", "cartwheel-support.agent", "2026-10-07T02:07:00.200Z"),
    ]


def _model_call_asking_for_the_order() -> dict[str, object]:
    return observation(
        "gen-1",
        "GENERATION",
        "openai.response",
        "2026-10-07T02:07:01.000Z",
        payload_in={"messages": [CUSTOMER_MESSAGE], "tools": [{"type": "function"}]},
        payload_out=[
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": "I will look up order 12."}],
                "finish_reason": "stop",
            },
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool_call",
                        "name": "get_order",
                        "id": "call_1",
                        "arguments": {"order_id": 12},
                    }
                ],
                "finish_reason": "tool_call",
            },
        ],
        model="gpt-test",
    )


def _order_lookup() -> dict[str, object]:
    return observation(
        "tool-1",
        "TOOL",
        "get_order",
        "2026-10-07T02:07:03.000Z",
        payload_in={"order_id": 12},
        payload_out={"ok": True, "order": {"order_id": 12, "status": "shipped"}},
        attributes={
            "cartwheel.permission_denied": False,
            "cartwheel.store_id": 16,
            "cartwheel.user_id": 9001,
            "cartwheel.user_role": "merchant",
        },
    )


def _model_call_replying(*, recorded: bool = True) -> dict[str, object]:
    return observation(
        "gen-2",
        "GENERATION",
        "openai.response",
        "2026-10-07T02:07:04.000Z",
        payload_in={"messages": [CUSTOMER_MESSAGE]} if recorded else None,
        payload_out=[{**FINAL_REPLY, "finish_reason": "stop"}] if recorded else None,
        model="gpt-test",
    )


def _export_trace(observations: list[dict[str, object]]) -> dict[str, object]:
    """One trace as scenarios/export_langfuse.py writes it."""
    return {
        "cartwheel_scenario_id": "support-0001",
        "id": TRACE_ID,
        "name": "cartwheel.session_message",
        "observations": observations,
        "timestamp": "2026-10-07T02:07:00.000Z",
        "traceId": TRACE_ID,
    }


def _order_status_trace() -> dict[str, object]:
    """A merchant asks for an order status; observations arrive out of time order."""
    return _export_trace(
        [
            _model_call_replying(),
            _order_lookup(),
            _root(),
            *_wrappers(),
            _model_call_asking_for_the_order(),
        ]
    )


def test_customer_message_is_read_from_the_rootobservation() -> None:
    steps = normalize_trace(_order_status_trace())["trace"]

    assert steps[0] == USER_STEP


def test_agent_text_is_read_from_model_outputs_stored_as_json_text() -> None:
    steps = normalize_trace(_order_status_trace())["trace"]

    assert [step for step in steps if step["role"] == "assistant"] == [REASON_STEP, REPLY_STEP]


def test_tool_steps_carry_decoded_arguments_and_results() -> None:
    steps = normalize_trace(_order_status_trace())["trace"]

    assert [step for step in steps if step["role"].startswith("tool_")] == [
        TOOL_CALL_STEP,
        TOOL_RESULT_STEP,
    ]


def test_caller_and_session_are_read_from_the_rootobservation() -> None:
    record = normalize_trace(_order_status_trace())

    assert record["meta"] == {
        "role": "merchant",
        "prompt_version": "abc123",
        "scenario_id": "support-0001",
        "session_id": SESSION_ID,
    }


def test_system_prompt_and_final_reply_stay_on_the_record() -> None:
    record = normalize_trace(_order_status_trace())

    assert record["input"] == [{"role": "system", "content": SYSTEM_PROMPT}, CUSTOMER_MESSAGE]
    assert record["output"] == [FINAL_REPLY]


def test_trace_without_a_tool_call_is_loaded() -> None:
    trace = _export_trace([_root(), *_wrappers(), _model_call_replying()])

    assert normalize_trace(trace)["trace"] == [USER_STEP, REPLY_STEP]


def test_trace_with_no_recorded_reply_keeps_only_what_was_recorded() -> None:
    trace = _export_trace(
        [
            _root(reply=None),
            *_wrappers(),
            _model_call_asking_for_the_order(),
            _order_lookup(),
            _model_call_replying(recorded=False),
        ]
    )

    assert normalize_trace(trace)["trace"] == [
        USER_STEP,
        REASON_STEP,
        TOOL_CALL_STEP,
        TOOL_RESULT_STEP,
    ]


def test_trace_level_input_is_not_replaced_by_the_rootobservation() -> None:
    trace = _order_status_trace()
    trace["input"] = "What is your returns policy?"

    assert normalize_trace(trace)["trace"][0] == {
        "role": "user",
        "text": "What is your returns policy?",
    }


def test_tool_result_that_is_json_null_is_still_shown() -> None:
    lookup = _order_lookup()
    lookup["output"] = "null"
    trace = _export_trace([_root(), *_wrappers(), lookup])

    tool_result = normalize_trace(trace)["trace"][2]

    assert tool_result == {"role": "tool_result", "name": "get_order", "content": "null"}


def test_tool_text_that_only_looks_like_json_is_kept_as_text() -> None:
    lookup = _order_lookup()
    lookup["output"] = "[draft] reply pending"
    trace = _export_trace([_root(), *_wrappers(), lookup])

    tool_result = normalize_trace(trace)["trace"][2]

    assert tool_result == {
        "role": "tool_result",
        "name": "get_order",
        "content": "[draft] reply pending",
    }
