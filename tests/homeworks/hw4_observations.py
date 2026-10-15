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
