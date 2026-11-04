"""What the Read view shows of each conversation.

Each conversation names who is asking, read from the session context the
server writes into the system prompt, and each turn holds the customer
message, the agent's steps (its reason, the tool call, what the tool answered)
and the reply. Long answers are folded until the reviewer opens them, except
for steps that change data, which always stay open.
"""

from __future__ import annotations

import json
import re
from typing import TypedDict

from analysis.helpers.normalization import SessionGroup, TraceRecord

# Tools that change data rather than only read it, by the action they perform.
_DATA_CHANGING_TOOLS = {
    "issue_refund": "refund",
    "cancel_order": "cancel",
    "escalate_to_human": "hand-off",
}

# Answers longer than this are folded until the reviewer opens them.
_FOLD_AFTER_CHARS = 400

_CONTEXT_LINE = re.compile(r"^- (User role|User id|Store id): (.+)$", re.MULTILINE)

# A tool call with the agent's reason before it and the tool's answer, if any.
type Pair = tuple[str | None, dict[str, object], dict[str, object] | None]


class Step(TypedDict):
    reason: str | None
    tool: str
    arguments: object
    ok: bool | None
    error: str | None
    error_reason: str | None
    summary: str
    result: object
    result_chars: int
    folded: bool
    changes_data: bool


class Turn(TypedDict):
    trace_id: str
    timestamp: str | None
    system_prompt: str | None
    customer: str | None
    steps: list[Step]
    reply: str | None


class Conversation(TypedDict):
    session_id: str
    scenario_id: str | None
    prompt_version: str | None
    role: str | None
    user_id: str | None
    store_id: str | None
    turns: list[Turn]
    tools: list[str]
    actions: list[str]


def conversation_views(sessions: list[SessionGroup]) -> list[Conversation]:
    """Return what the Read view draws for each conversation, in the same order."""
    return [_conversation(session) for session in sessions]


# -- conversations ------------------------------------------------------------


def _conversation(session: SessionGroup) -> Conversation:
    first = session["traces"][0]
    turns = [_turn(trace) for trace in session["traces"]]
    context = _session_context(turns[0]["system_prompt"])
    tools = _tools(turns)
    return {
        "session_id": session["session_id"],
        "scenario_id": _meta(first, "scenario_id"),
        "prompt_version": _meta(first, "prompt_version"),
        "role": _known(context.get("User role")) or _meta(first, "role"),
        "user_id": _known(context.get("User id")),
        "store_id": _known(context.get("Store id")),
        "turns": turns,
        "tools": tools,
        "actions": [_DATA_CHANGING_TOOLS[tool] for tool in tools if tool in _DATA_CHANGING_TOOLS],
    }


def _meta(trace: TraceRecord, key: str) -> str | None:
    meta = trace.get("meta")
    value = meta.get(key) if isinstance(meta, dict) else None
    return str(value) if value else None


def _session_context(system_prompt: str | None) -> dict[str, str]:
    return {key: value.strip() for key, value in _CONTEXT_LINE.findall(system_prompt or "")}


def _known(value: str | None) -> str | None:
    return None if value is None or value.lower() in {"", "none"} else value


def _tools(turns: list[Turn]) -> list[str]:
    """Distinct tools the conversation used, in the order it first used them."""
    return list(dict.fromkeys(step["tool"] for turn in turns for step in turn["steps"]))


# -- turns --------------------------------------------------------------------


def _turn(trace: TraceRecord) -> Turn:
    messages = _messages(trace)
    pairs, reply = _pairs_and_reply(messages)
    return {
        "trace_id": str(trace["id"]),
        "timestamp": str(trace["timestamp"]) if trace.get("timestamp") else None,
        "system_prompt": _system_prompt(trace.get("input")),
        "customer": _customer(messages),
        "steps": [_step(*pair) for pair in pairs],
        "reply": reply,
    }


def _messages(trace: TraceRecord) -> list[dict[str, object]]:
    steps = trace.get("trace")
    return [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []


def _system_prompt(payload: object) -> str | None:
    if not isinstance(payload, list):
        return None
    for message in payload:
        if isinstance(message, dict) and message.get("role") == "system":
            content = message.get("content")
            return content if isinstance(content, str) else None
    return None


def _customer(messages: list[dict[str, object]]) -> str | None:
    return next((str(m.get("text") or "") for m in messages if m.get("role") == "user"), None)


def _pairs_and_reply(messages: list[dict[str, object]]) -> tuple[list[Pair], str | None]:
    """Pair each tool call with the agent text before it and the tool's answer.

    Agent text left after the last tool call is the reply to the customer.
    """
    pairs: list[Pair] = []
    pending: list[str] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            pending.append(str(message.get("text") or ""))
        elif role == "tool_call":
            pairs.append(("\n\n".join(pending) or None, message, None))
            pending = []
        elif role == "tool_result":
            _attach_answer(pairs, message)
    return pairs, "\n\n".join(pending) or None


def _attach_answer(pairs: list[Pair], answer: dict[str, object]) -> None:
    """Give the answer to the latest call of the same tool still waiting for one."""
    for position in range(len(pairs) - 1, -1, -1):
        reason, call, existing = pairs[position]
        if existing is None and call.get("name") == answer.get("name"):
            pairs[position] = (reason, call, answer)
            return


# -- steps --------------------------------------------------------------------


def _step(
    reason: str | None, call: dict[str, object], answer_message: dict[str, object] | None
) -> Step:
    tool = str(call.get("name") or "")
    answer = answer_message.get("content") if answer_message else None
    ok, error, error_reason = _outcome(answer)
    chars = _chars(answer)
    changes_data = tool in _DATA_CHANGING_TOOLS
    return {
        "reason": reason,
        "tool": tool,
        "arguments": call.get("arguments"),
        "ok": ok,
        "error": error,
        "error_reason": error_reason,
        "summary": _summary(answer),
        "result": answer,
        "result_chars": chars,
        "folded": chars > _FOLD_AFTER_CHARS and not changes_data,
        "changes_data": changes_data,
    }


def _outcome(answer: object) -> tuple[bool | None, str | None, str | None]:
    """Return whether the tool succeeded, with its error code and reason if not."""
    if not isinstance(answer, dict):
        return None, None, None
    if answer.get("ok") is False:
        reason = answer.get("reason")
        return False, str(answer.get("error") or "failed"), str(reason) if reason else None
    return (True if answer.get("ok") is True else None), None, None


def _chars(answer: object) -> int:
    if answer is None:
        return 0
    return len(answer) if isinstance(answer, str) else len(json.dumps(answer))


def _summary(answer: object) -> str:
    """One line for a successful answer; empty when the answer is short enough to show."""
    if not isinstance(answer, dict) or answer.get("ok") is False:
        return ""
    listed = next(((key, value) for key, value in answer.items() if isinstance(value, list)), None)
    return _list_summary(*listed) if listed else _status_summary(answer)


def _list_summary(name: str, items: list[object]) -> str:
    stores = [item.get("store_id") for item in items if isinstance(item, dict)]
    if not items or None in stores or len(stores) != len(items):
        return f"{len(items)} {name}"
    distinct = sorted({str(store) for store in stores})
    if len(distinct) == 1:
        return f"{len(items)} {name}, all from store {distinct[0]}"
    return f"{len(items)} {name} across {len(distinct)} stores"


def _status_summary(answer: dict[str, object]) -> str:
    if "status" not in answer:
        return ""
    details = [
        f"{key} {value}"
        for key, value in answer.items()
        if key not in {"ok", "status", "note"} and isinstance(value, (str, int, float))
    ]
    return " · ".join([str(answer["status"]), *details])
