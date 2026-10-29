"""Load the conversations to review: live from Langfuse, else from the export.

The local export (traces/support_traces.json) is only a fallback. When
Langfuse cannot be reached, the reason comes back with the conversations, so
the page can show it and it can be recorded in trace_source_notes.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypedDict

from analysis.helpers import langfuse_io
from analysis.helpers.normalization import (
    SessionGroup,
    TraceRecord,
    group_by_session,
    normalize_trace,
)

EXPORT_PATH = Path(__file__).resolve().parents[2] / "traces" / "support_traces.json"

# Langfuse also holds the HW3 pilot and probe traces; the review covers the
# support scenarios only.
_SUPPORT_PREFIX = "support-"

type Source = Literal["langfuse", "export"]


class SessionsSource(TypedDict):
    source: Source
    fallback_reason: str | None
    sessions: list[SessionGroup]


def load_sessions(
    fetch: Callable[[], list[TraceRecord]] = langfuse_io.fetch_traces,
    export_path: Path = EXPORT_PATH,
) -> SessionsSource:
    """Return the support conversations, oldest first, and where they came from."""
    source, reason, traces = _traces(fetch, export_path)
    sessions = group_by_session(_support_only(traces))
    return {"source": source, "fallback_reason": reason, "sessions": sessions}


def _traces(
    fetch: Callable[[], list[TraceRecord]], export_path: Path
) -> tuple[Source, str | None, list[TraceRecord]]:
    """Read the traces from Langfuse, or from the export when that fails."""
    try:
        return "langfuse", None, fetch()
    except Exception as error:
        return "export", f"{type(error).__name__}: {error}", _exported_traces(export_path)


def _exported_traces(export_path: Path) -> list[TraceRecord]:
    records = json.loads(export_path.read_text(encoding="utf-8"))["traces"]
    return [normalize_trace(record) for record in records]


def _is_support(trace: TraceRecord) -> bool:
    meta = trace.get("meta")
    scenario = meta.get("scenario_id") if isinstance(meta, dict) else None
    return str(scenario or "").startswith(_SUPPORT_PREFIX)


def _support_only(traces: list[TraceRecord]) -> list[TraceRecord]:
    return [trace for trace in traces if _is_support(trace)]
