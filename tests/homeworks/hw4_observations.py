"""Hand-written Langfuse observations shared by the Homework 4 tests.

Each one mirrors a row of the Observations API v2, the shape Langfuse v4
serves and scenarios/export_langfuse.py writes: payloads are JSON text, span
attributes are flattened into ``attributes.``-prefixed metadata keys, and the
session sits on the root observation only.
"""

from __future__ import annotations

import json

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SESSION_ID = "session-a"


def observation(
    observation_id: str,
    kind: str,
    name: str,
    started: str,
    *,
    trace_id: str = TRACE_ID,
    session_id: str = SESSION_ID,
    payload_in: object = None,
    payload_out: object = None,
    attributes: dict[str, object] | None = None,
    root: bool = False,
    model: str | None = None,
    tags: tuple[str, ...] = (),
) -> dict[str, object]:
    """One observation as the Observations API v2 returns it."""
    metadata: dict[str, object] = {
        "resourceAttributes.service.name": "cartwheel-support",
        "scope.name": "cartwheel",
    }
    metadata.update({f"attributes.{key}": value for key, value in (attributes or {}).items()})
    return {
        "id": observation_id,
        "traceId": trace_id,
        "traceName": "cartwheel.session_message",
        "type": kind,
        "name": name,
        "startTime": started,
        "endTime": started,
        "isRootObservation": root,
        "parentObservationId": None if root else "root",
        "sessionId": session_id if root else "",
        "tags": list(tags),
        "environment": "default",
        "level": "DEFAULT",
        "latency": 0.01,
        "model": model,
        "metadata": metadata,
        "input": None if payload_in is None else json.dumps(payload_in),
        "output": None if payload_out is None else json.dumps(payload_out),
    }


MERCHANT_PROMPT = (
    "You are Cartwheel's support assistant.\n\n"
    "## Session context (injected by the server; never taken from chat)\n"
    "- User role: merchant\n- User id: 9001\n- Store id: 16\n\n"
    "## Tool guidance\n- Prefer a tool lookup over memory."
)

# One tool step of a conversation: the agent's reason, the tool, what it sent,
# and what the tool answered (None when no answer was recorded).
type ToolStep = tuple[str, str, object, object]


def _text_message(role: str, text: str) -> dict[str, object]:
    return {"role": role, "parts": [{"type": "text", "content": text}]}


def _at(second: int) -> str:
    return f"2026-10-07T02:07:{second:02d}.000Z"


def _step_rows(trace_id: str, number: int, step: ToolStep) -> list[dict[str, object]]:
    reason, tool, arguments, result = step
    asking = [
        _text_message("assistant", reason),
        {
            "role": "assistant",
            "parts": [{"type": "tool_call", "name": tool, "id": f"call_{number}", "arguments": arguments}],
        },
    ]
    return [
        observation(f"{trace_id}-gen-{number}", "GENERATION", "openai.response", _at(2 * number),
                    trace_id=trace_id, payload_out=asking, model="gpt-test"),
        observation(f"{trace_id}-tool-{number}", "TOOL", tool, _at(2 * number + 1),
                    trace_id=trace_id, payload_in=arguments, payload_out=result),
    ]


def conversation_trace(
    *,
    trace_id: str = TRACE_ID,
    session_id: str = SESSION_ID,
    scenario: str = "support-0001",
    system_prompt: str = MERCHANT_PROMPT,
    customer: str = "Where is order 12?",
    steps: tuple[ToolStep, ...] = (),
    reply: str | None = "Order 12 has shipped.",
) -> dict[str, object]:
    """One exported trace: a customer message, tool steps, and the reply if recorded."""
    root = observation(
        f"{trace_id}-root", "SPAN", "cartwheel.session_message", _at(0),
        trace_id=trace_id, session_id=session_id,
        payload_in=[{"role": "system", "content": system_prompt}, _text_message("user", customer)],
        payload_out=None if reply is None else [_text_message("assistant", reply)],
        attributes={"cartwheel.scenario_id": scenario, "cartwheel.prompt_version": "abc123"},
        root=True,
    )
    rows = [root]
    for number, step in enumerate(steps, start=1):
        rows.extend(_step_rows(trace_id, number, step))
    if reply is not None:
        rows.append(observation(f"{trace_id}-gen-last", "GENERATION", "openai.response", _at(59),
                                trace_id=trace_id, payload_out=[_text_message("assistant", reply)], model="gpt-test"))
    return {"id": trace_id, "traceId": trace_id, "cartwheel_scenario_id": scenario, "timestamp": _at(0), "observations": rows}
