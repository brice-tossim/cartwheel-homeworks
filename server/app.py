"""The Cartwheel endpoint, with the session routes completed in Homework 2.

A thin FastAPI wrapper with three routes (Lecture 2.3):

  - POST /sessions            binds a user + role, returns a signed dev token
  - POST /sessions/{id}/messages   one conversation turn
  - GET  /health              liveness

Why an endpoint at all: one choke point to authenticate, log, sample,
rate-limit, and replay. Modules 3 and 4 need a surface to monitor and attack.

The token is dev-only auth: a base64 JSON payload signed with an HMAC over a
shared secret (CARTWHEEL_DEV_SECRET). It is not real auth; the *shape* (a
server-issued credential carrying user id + role that tools trust) is what
Module 4 attacks. In production you would stream responses and assemble the
final message in middleware; this server does not stream.

Run with:
    uv run uvicorn server.app:app --port 8010
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal

from agents import Runner, SQLiteSession
from fastapi import FastAPI, Header, HTTPException
from opentelemetry import trace
from opentelemetry.instrumentation.openai_agents.utils import should_send_prompts
from pydantic import BaseModel

from agent import db
from agent.agent import build_agent, prompt_version, render_system_prompt
from agent.auth import ROLES, AuthContext
from agent.config import REPO_ROOT, db_path
from observability.instrument import load_env, setup_tracing

MAX_TURNS = 12  # cap runaway loops; keeps conversations bounded
SESSIONS_DB = REPO_ROOT / ".sessions.db"

_tracer = trace.get_tracer("cartwheel.server")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_env()
    setup_tracing()  # no-op with a warning if LANGFUSE_PUBLIC_KEY is unset
    yield


app = FastAPI(title="Cartwheel support agent", lifespan=lifespan)

# session_id -> (AuthContext, SQLiteSession). In-memory on purpose: the trace
# store is the durable record, not this dict.
_SESSIONS: dict[str, tuple[AuthContext, SQLiteSession]] = {}


# ---------------------------------------------------------------------------
# Signed dev token: base64url(JSON payload) + "." + HMAC-SHA256 signature.
# ---------------------------------------------------------------------------


def _secret() -> bytes:
    return os.environ.get("CARTWHEEL_DEV_SECRET", "cartwheel-dev-secret").encode()


def create_token(payload: dict[str, Any]) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True).encode()
    ).decode()
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> dict[str, Any] | None:
    """Return the payload if the signature checks out, else None."""
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(body.encode()))
    except (binascii.Error, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    user_id: int
    role: str


class MessageIn(BaseModel):
    message: str
    model: str | None = None
    # Set by the scenario runner (Lecture 3) so a trace links back to its
    # ground truth. Manual sessions leave it null.
    scenario_id: str | None = None


class TranscriptMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionTranscript(BaseModel):
    session_id: str
    messages: list[TranscriptMessage]


@app.post("/sessions")
def create_session(body: SessionCreate) -> dict[str, str]:
    """Bind a verified database user to a new server-side session.

    Validate the requested role, load the user from the database, and reject
    a request whose claimed role differs from the stored role. Create an
    AuthContext and SQLiteSession, save them in _SESSIONS, then return the
    session id and a signed token. The token payload must contain session_id,
    user_id, role, store_id, and issued_at.
    """
    _require_known_role(body.role)
    user = _load_user(body.user_id)
    _require_claimed_role(user, body.role)
    ctx = _auth_context(user)
    session_id = _open_session(ctx)
    return _signed_session(session_id, ctx)


def _require_known_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"unknown role: {role!r}")


def _load_user(user_id: int) -> db.User:
    with db.connection() as conn:
        user = db.get_user(conn, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"unknown user: {user_id}")
    return user


def _require_claimed_role(user: db.User, claimed_role: str) -> None:
    # Say only that the claim failed: naming the stored role would disclose it.
    if user.role != claimed_role:
        raise HTTPException(status_code=403, detail="role does not match this user")


def _auth_context(user: db.User) -> AuthContext:
    """Build the caller's identity from the database row, never from the request."""
    return AuthContext(user_id=user.id, role=user.role, store_id=user.store_id)


def _open_session(ctx: AuthContext) -> str:
    """Save the identity with its own conversation history under a new id."""
    session_id = uuid.uuid4().hex
    _SESSIONS[session_id] = (ctx, SQLiteSession(session_id, SESSIONS_DB))
    return session_id


def _signed_session(session_id: str, ctx: AuthContext) -> dict[str, str]:
    token = create_token(
        {
            "session_id": session_id,
            "user_id": ctx.user_id,
            "role": ctx.role,
            "store_id": ctx.store_id,
            "issued_at": int(time.time()),
        }
    )
    return {"session_id": session_id, "token": token}


def _authorize(session_id: str, authorization: str | None) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = verify_token(authorization.removeprefix("Bearer "))
    if payload is None:
        raise HTTPException(status_code=401, detail="bad token signature")
    if payload.get("session_id") != session_id:
        raise HTTPException(status_code=403, detail="token is for another session")
    if session_id not in _SESSIONS:
        raise HTTPException(status_code=404, detail="unknown session (server restarted?)")
    return _SESSIONS[session_id][0]


@app.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str,
    body: MessageIn,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Run one authenticated conversation turn inside a root trace span.

    Authorize the token, recover the server-side session, and build the agent
    for the authenticated context. Hash only the system prompt template.
    The cartwheel.session_message span must record the session id, user role,
    user id, prompt version, and a nonempty scenario id when one is supplied. Run the
    agent inside that span, then return the session id, final reply, and
    prompt version.
    When TRACELOOP_TRACE_CONTENT is true, record gen_ai.input.messages and
    gen_ai.output.messages on the root span as JSON arrays of OTel GenAI
    messages with role and parts fields.
    """
    ctx = _authorize(session_id, authorization)
    _, history = _SESSIONS[session_id]
    version = prompt_version()
    reply = await _run_in_root_span(session_id, body, ctx, history, version)
    return {"session_id": session_id, "reply": reply, "prompt_version": version}


async def _run_in_root_span(
    session_id: str,
    body: MessageIn,
    ctx: AuthContext,
    history: SQLiteSession,
    version: str,
) -> str:
    """Run the turn inside the root span, so model and tool spans nest under it."""
    with _tracer.start_as_current_span("cartwheel.session_message") as span:
        _record_request(span, session_id, ctx, version, body.scenario_id)
        _record_instructions(span, render_system_prompt(ctx))
        _record_message(span, "gen_ai.input.messages", "user", body.message)
        reply = await _run_agent(ctx, history, body)
        _record_message(span, "gen_ai.output.messages", "assistant", reply)
    return reply


def _record_request(
    span: trace.Span,
    session_id: str,
    ctx: AuthContext,
    version: str,
    scenario_id: str | None,
) -> None:
    # session.id is the standard OTel attribute Langfuse uses to group the
    # turns of one conversation into a session.
    span.set_attribute("session.id", session_id)
    span.set_attribute("cartwheel.user_role", ctx.role)
    span.set_attribute("cartwheel.user_id", str(ctx.user_id))
    span.set_attribute("cartwheel.prompt_version", version)
    if scenario_id:
        span.set_attribute("cartwheel.scenario_id", scenario_id)


def _record_instructions(span: trace.Span, instructions: str) -> None:
    """Record the rendered system prompt as OTel GenAI system instructions.

    An extension beyond Homework 2: Langfuse shows gen_ai.system_instructions
    as a System message above the user message in the root span's preview.
    Like the messages, it is recorded only when content capture is on.
    """
    if should_send_prompts():
        span.set_attribute(
            "gen_ai.system_instructions",
            json.dumps([{"type": "text", "content": instructions}]),
        )


def _record_message(span: trace.Span, attribute: str, role: str, text: str) -> None:
    """Record one message in the OTel GenAI format when content capture is on.

    should_send_prompts reads TRACELOOP_TRACE_CONTENT exactly as OpenLLMetry
    does for the model spans, so the root span never records content they omit.
    """
    if should_send_prompts():
        message = {"role": role, "parts": [{"type": "text", "content": text}]}
        span.set_attribute(attribute, json.dumps([message]))


async def _run_agent(ctx: AuthContext, history: SQLiteSession, body: MessageIn) -> str:
    agent = build_agent(ctx, model=body.model)
    result = await Runner.run(
        agent, body.message, session=history, context=ctx, max_turns=MAX_TURNS
    )
    return result.final_output_as(str)


@app.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> SessionTranscript:
    """List a session's conversation as a plain chat transcript.

    An extension beyond Homework 2, behind the same bearer token as POST. Only
    user and assistant text is listed; tool calls, tool results, and reasoning
    stay in the stored history and in the traces. No span is recorded: nothing
    runs, and a trace per read would crowd the per-turn traces.
    """
    _authorize(session_id, authorization)
    _, history = _SESSIONS[session_id]
    items = await history.get_items()
    return SessionTranscript(session_id=session_id, messages=_transcript(items))


def _transcript(items: Sequence[Mapping[str, object]]) -> list[TranscriptMessage]:
    entries = (_transcript_entry(item) for item in items)
    return [entry for entry in entries if entry is not None]


def _transcript_entry(item: Mapping[str, object]) -> TranscriptMessage | None:
    """A user or assistant message as plain text; None for every other item."""
    role = _transcript_role(item.get("role"))
    text = _text_of(item.get("content"))
    if role is None or not text:
        return None
    return TranscriptMessage(role=role, content=text)


def _transcript_role(role: object) -> Literal["user", "assistant"] | None:
    match role:
        case "user":
            return "user"
        case "assistant":
            return "assistant"
        case _:
            return None


def _text_of(content: object) -> str:
    """A message's text: the string itself, or its output_text parts joined."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for part in content:
        if isinstance(part, Mapping) and part.get("type") == "output_text":
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
    return "".join(texts)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "db_exists": db_path().exists(),
        "active_sessions": len(_SESSIONS),
    }
