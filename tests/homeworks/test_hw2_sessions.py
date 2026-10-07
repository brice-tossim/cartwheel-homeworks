"""Edge-case tests for the Homework 2 session creation route in server/app.py.

tests/test_hw_holes.py holds the instructor contract test, which checks the
store a merchant's token carries, and tests/test_observability.py holds the two
authentication cases the handout requires. These tests cover the rest of the
create_session docstring: the 400 and 404 rejections and the order they are
checked in, the identity bound into the token and into the server-side session
for every role, and a separate conversation history per session. Everything
runs offline against the seeded temp world from tests/conftest.py.
"""

from __future__ import annotations

import asyncio
import math
import time

import pytest
from agents import SQLiteSession
from fastapi import HTTPException

from agent.auth import AuthContext
from server import app as server_app

SessionStore = dict[str, tuple[AuthContext, SQLiteSession]]

# Dev-scale seed ids: shoppers 1-500, merchants 9001-9020, support 9501-9505.
UNKNOWN_USER_ID = 999_999

IDENTITIES = [
    pytest.param(AuthContext(user_id=1, role="shopper"), id="shopper"),
    pytest.param(AuthContext(user_id=9001, role="merchant", store_id=1), id="merchant"),
    pytest.param(AuthContext(user_id=9501, role="support"), id="support"),
]


def _rejection_status(user_id: int, role: str) -> int:
    with pytest.raises(HTTPException) as rejected:
        server_app.create_session(server_app.SessionCreate(user_id=user_id, role=role))
    return rejected.value.status_code


@pytest.mark.parametrize("user_id", [1, UNKNOWN_USER_ID], ids=["known-user", "unknown-user"])
def test_unknown_role_is_rejected_before_the_user_is_loaded(
    server_sessions: SessionStore, user_id: int
) -> None:
    """An unknown role is a 400 even for a user who does not exist."""
    assert _rejection_status(user_id, "admin") == 400
    assert server_sessions == {}


def test_unknown_user_is_rejected_with_404(server_sessions: SessionStore) -> None:
    assert _rejection_status(UNKNOWN_USER_ID, "shopper") == 404
    assert server_sessions == {}


@pytest.mark.parametrize("identity", IDENTITIES)
def test_token_binds_the_database_identity(
    server_sessions: SessionStore, identity: AuthContext
) -> None:
    earliest = math.floor(time.time())
    response = server_app.create_session(
        server_app.SessionCreate(user_id=identity.user_id, role=identity.role)
    )
    latest = math.ceil(time.time())
    payload = server_app.verify_token(response["token"])

    assert payload is not None, "the token must verify with the server secret"
    assert payload["session_id"] == response["session_id"]
    assert payload["user_id"] == identity.user_id
    assert payload["role"] == identity.role
    assert payload["store_id"] == identity.store_id
    assert earliest <= payload["issued_at"] <= latest


@pytest.mark.parametrize("identity", IDENTITIES)
def test_session_stores_the_database_identity(
    server_sessions: SessionStore, identity: AuthContext
) -> None:
    response = server_app.create_session(
        server_app.SessionCreate(user_id=identity.user_id, role=identity.role)
    )

    stored_context, _ = server_sessions[response["session_id"]]
    assert stored_context == identity


def test_sessions_for_the_same_user_keep_separate_histories(
    server_sessions: SessionStore,
) -> None:
    """Two sessions must never read each other's conversation."""
    first = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    second = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    _, first_history = server_sessions[first["session_id"]]
    _, second_history = server_sessions[second["session_id"]]

    asyncio.run(
        first_history.add_items([{"role": "user", "content": "Show my recent orders."}])
    )

    assert asyncio.run(second_history.get_items()) == []
