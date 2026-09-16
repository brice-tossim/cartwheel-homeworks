"""Tests for listing a session's conversation with GET /sessions/{id}/messages.

An extension beyond Homework 2: the route returns a session's history as a
plain chat transcript of user and assistant text, behind the same bearer token
as POST. Histories are seeded with the items the Agents SDK stores for a turn,
so no agent run or model is needed. Everything runs offline against the seeded
temp world from tests/conftest.py.
"""

from __future__ import annotations

import asyncio

import pytest
from agents import SQLiteSession
from agents.items import TResponseInputItem
from fastapi import HTTPException

from agent.auth import AuthContext
from server import app as server_app

SessionStore = dict[str, tuple[AuthContext, SQLiteSession]]

# One turn as SQLiteSession stores it: the user message, a reasoning item, an
# explanation, the tool call and its raw output, then the final reply.
TURN_WITH_A_TOOL_CALL: list[TResponseInputItem] = [
    {"role": "user", "content": "Show my recent orders."},
    {"id": "rs-0", "type": "reasoning", "summary": []},
    {
        "id": "msg-1",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [
            {"type": "output_text", "text": "Let me look up your orders.", "annotations": []}
        ],
    },
    {
        "id": "fc-2",
        "type": "function_call",
        "call_id": "call-3",
        "name": "list_my_orders",
        "arguments": "{}",
    },
    {"type": "function_call_output", "call_id": "call-3", "output": "{'ok': True, 'orders': []}"},
    {
        "id": "msg-4",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [
            {
                "type": "output_text",
                "text": "Here are your 20 most recent orders.",
                "annotations": [],
            }
        ],
    },
]


def _open_session(user_id: int, role: str) -> tuple[str, str]:
    created = server_app.create_session(
        server_app.SessionCreate(user_id=user_id, role=role)
    )
    return created["session_id"], f"Bearer {created['token']}"


def _record(
    sessions: SessionStore, session_id: str, items: list[TResponseInputItem]
) -> None:
    _, history = sessions[session_id]
    asyncio.run(history.add_items(items))


def _listed(session_id: str, authorization: str | None) -> dict[str, object]:
    transcript = asyncio.run(
        server_app.list_messages(session_id, authorization=authorization)
    )
    return transcript.model_dump()


@pytest.mark.parametrize(
    ("case", "status"),
    [("missing", 401), ("forged", 401), ("another-session", 403), ("unknown-session", 404)],
)
def test_a_rejected_token_lists_nothing(
    server_sessions: SessionStore, case: str, status: int
) -> None:
    session_id, _ = _open_session(1, "shopper")
    _, other_token = _open_session(2, "shopper")
    _record(server_sessions, session_id, TURN_WITH_A_TOOL_CALL)
    unknown_token = server_app.create_token({"session_id": "no-such-session"})
    target, authorization = {
        "missing": (session_id, None),
        "forged": (session_id, "Bearer forged.signature"),
        "another-session": (session_id, other_token),
        "unknown-session": ("no-such-session", f"Bearer {unknown_token}"),
    }[case]

    with pytest.raises(HTTPException) as rejected:
        _listed(target, authorization)

    assert rejected.value.status_code == status


def test_a_new_session_has_no_messages(server_sessions: SessionStore) -> None:
    session_id, token = _open_session(1, "shopper")

    assert _listed(session_id, token) == {"session_id": session_id, "messages": []}


def test_a_turn_lists_only_user_and_assistant_text_in_order(
    server_sessions: SessionStore,
) -> None:
    session_id, token = _open_session(1, "shopper")
    _record(server_sessions, session_id, TURN_WITH_A_TOOL_CALL)

    assert _listed(session_id, token)["messages"] == [
        {"role": "user", "content": "Show my recent orders."},
        {"role": "assistant", "content": "Let me look up your orders."},
        {"role": "assistant", "content": "Here are your 20 most recent orders."},
    ]


def test_an_assistant_message_in_several_text_parts_is_one_entry(
    server_sessions: SessionStore,
) -> None:
    session_id, token = _open_session(1, "shopper")
    _record(
        server_sessions,
        session_id,
        [
            {"role": "user", "content": "Where is order 4455?"},
            {
                "id": "msg-9",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "Order 4455 ", "annotations": []},
                    {
                        "type": "output_text",
                        "text": "was delivered on June 26.",
                        "annotations": [],
                    },
                ],
            },
        ],
    )

    assert _listed(session_id, token)["messages"] == [
        {"role": "user", "content": "Where is order 4455?"},
        {"role": "assistant", "content": "Order 4455 was delivered on June 26."},
    ]


def test_an_assistant_message_without_text_is_left_out(
    server_sessions: SessionStore,
) -> None:
    session_id, token = _open_session(1, "shopper")
    _record(
        server_sessions,
        session_id,
        [
            {"role": "user", "content": "Give me another shopper's address."},
            {
                "id": "msg-7",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "refusal", "refusal": "I can't share that."}],
            },
        ],
    )

    assert _listed(session_id, token)["messages"] == [
        {"role": "user", "content": "Give me another shopper's address."}
    ]


def test_a_session_lists_only_its_own_messages(server_sessions: SessionStore) -> None:
    first_id, _ = _open_session(1, "shopper")
    second_id, second_token = _open_session(1, "shopper")
    _record(server_sessions, first_id, TURN_WITH_A_TOOL_CALL)

    assert _listed(second_id, second_token)["messages"] == []
