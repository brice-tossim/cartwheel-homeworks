"""Authentication tests for the Homework 2 session routes in server/app.py.

The server, not the conversation, decides who is calling. POST /sessions checks
the claimed identity against the users table and signs it into a token bound to
one session, and every message request must present that token for that
session. These tests call the route functions directly against the seeded temp
world from tests/conftest.py, so they need no Langfuse, Docker, or model
provider key; tracing is checked through the recorded spans in Part E.
"""

from __future__ import annotations

import pytest
from agents import SQLiteSession
from fastapi import HTTPException

from agent.auth import AuthContext
from server import app as server_app

SessionStore = dict[str, tuple[AuthContext, SQLiteSession]]


@pytest.mark.parametrize(
    ("user_id", "claimed_role"),
    [(1, "support"), (9002, "shopper")],
    ids=["shopper-claims-support", "merchant-claims-shopper"],
)
def test_session_creation_rejects_a_role_the_database_does_not_hold(
    server_sessions: SessionStore, user_id: int, claimed_role: str
) -> None:
    with pytest.raises(HTTPException) as rejected:
        server_app.create_session(
            server_app.SessionCreate(user_id=user_id, role=claimed_role)
        )

    assert rejected.value.status_code == 403
    assert server_sessions == {}, "a rejected claim must not open a session"


def test_token_for_one_session_cannot_authorize_another(
    server_sessions: SessionStore,
) -> None:
    first = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    second = server_app.create_session(server_app.SessionCreate(user_id=2, role="shopper"))
    first_token = f"Bearer {first['token']}"

    # Positive control: a token that authorized nothing would also pass the
    # rejection below, so first prove the token opens its own session.
    assert server_app._authorize(first["session_id"], first_token) == AuthContext(
        user_id=1, role="shopper"
    )
    with pytest.raises(HTTPException) as rejected:
        server_app._authorize(second["session_id"], first_token)

    assert rejected.value.status_code == 403
