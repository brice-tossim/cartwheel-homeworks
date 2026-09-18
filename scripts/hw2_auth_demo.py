"""Replay the Homework 2 authentication tests against the running server.

tests/test_observability.py checks two rules in-process: a session needs the
role stored in the database, and a session's token opens only that session.
This script sends the same requests over HTTP, as curl would, and prints what
each step tests, what it sends, and what it receives.

Usage:
    uv run uvicorn server.app:app --port 8010    # first, in another terminal
    uv run python scripts/hw2_auth_demo.py        # --base-url for another address

The token steps call GET /sessions/{id}/messages, which runs the same
authorization check as POST without running the agent: no model call, no trace.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from typing import NamedTuple

import httpx

RULE = "=" * 80
INDENT = " " * len("- What we receive: ")


class Session(NamedTuple):
    id: str
    token: str


def main() -> None:
    base_url = _base_url()
    with httpx.Client(base_url=base_url) as client:
        _require_server(client, base_url)
        results = [_role_claim_step(client), *_token_steps(client)]
    _conclude(results)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _role_claim_step(client: httpx.Client) -> bool:
    print("Test 1: a claimed role must match the role stored in the database\n")
    response = client.post("/sessions", json={"user_id": 9002, "role": "shopper"})
    return _show(
        "User 9002 is a merchant but claims shopper: expect 403.",
        sent=_request_lines(response),
        received=[_response_line(response)],
        passed=response.status_code == 403,
    )


def _token_steps(client: httpx.Client) -> list[bool]:
    print("Test 2: a token issued for one session cannot authorize another\n")
    a, b = _open_sessions(client)
    return [
        _token_step(
            client,
            test="Positive control, session A's token on session A: expect 200.",
            token=a.token,
            session_id=a.id,
            expected=200,
        ),
        _token_step(
            client,
            test="Session A's token on session B: expect 403.",
            token=a.token,
            session_id=b.id,
            expected=403,
        ),
    ]


def _open_sessions(client: httpx.Client) -> tuple[Session, Session]:
    first = client.post("/sessions", json={"user_id": 1, "role": "shopper"})
    second = client.post("/sessions", json={"user_id": 2, "role": "shopper"})
    opened = _show(
        "Setup: shopper 1 opens session A, shopper 2 opens session B.",
        sent=[*_request_lines(first), *_request_lines(second)],
        received=[_response_line(first), _response_line(second)],
        passed=first.status_code == second.status_code == 200,
    )
    if not opened:
        sys.exit("Stopped: test 2 needs sessions A and B.")
    return _session(first), _session(second)


def _token_step(
    client: httpx.Client, *, test: str, token: str, session_id: str, expected: int
) -> bool:
    response = client.get(
        f"/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    return _show(
        test,
        sent=_request_lines(response),
        received=[_response_line(response)],
        passed=response.status_code == expected,
    )


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def _base_url() -> str:
    parser = argparse.ArgumentParser(description="Replay the HW2 authentication tests.")
    parser.add_argument("--base-url", default="http://localhost:8010")
    return parser.parse_args().base_url


def _require_server(client: httpx.Client, base_url: str) -> None:
    try:
        client.get("/health")
    except httpx.ConnectError:
        sys.exit(
            f"No server at {base_url}. Start it first: "
            "uv run uvicorn server.app:app --port 8010"
        )
    print(f"Replaying tests/test_observability.py against {base_url}\n")


def _session(response: httpx.Response) -> Session:
    body = response.json()
    return Session(id=body["session_id"], token=body["token"])


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def _show(test: str, *, sent: list[str], received: list[str], passed: bool) -> bool:
    """Print one step as a block: what it tests, sends, and receives."""
    verdict = "✓ as expected" if passed else "✗ NOT as expected"
    print(RULE)
    _print_item("What we test", textwrap.wrap(test, len(RULE) - len(INDENT)))
    _print_item("What we send", sent)
    _print_item("What we receive", [*received, verdict])
    print(RULE + "\n")
    return passed


def _print_item(label: str, lines: list[str]) -> None:
    first, *rest = lines
    print(f"- {label}:".ljust(len(INDENT)) + first)
    for line in rest:
        print(INDENT + line)


def _request_lines(response: httpx.Response) -> list[str]:
    """What was sent, read back from the request itself, token shortened."""
    request = response.request
    lines = [f"{request.method} {request.url.path} {request.content.decode()}".rstrip()]
    if authorization := request.headers.get("Authorization"):
        scheme, token = authorization.split(" ", 1)
        lines.append(f"Authorization: {scheme} {_short(token)}")
    return lines


def _response_line(response: httpx.Response) -> str:
    """The status and body, with a returned token shortened."""
    body = response.text
    token = response.json().get("token")
    if isinstance(token, str):
        body = body.replace(token, _short(token))
    return f"{response.status_code} {response.reason_phrase}  {body}"


def _short(token: str) -> str:
    """Keep the ends of a token, enough to tell tokens apart: eyJpc...bd2."""
    return f"{token[:5]}...{token[-3:]}"


def _conclude(results: list[bool]) -> None:
    failed = results.count(False)
    if failed:
        sys.exit(f"{failed} step(s) did not behave as the tests expect.")
    print("Every step behaved as the tests expect.")


if __name__ == "__main__":
    main()
