"""Trace review server: the review page and the JSON routes it uses.

Start it from the repository root, so the analysis helpers import and the
LANGFUSE_* settings load from .env:

    uv run python -m analysis.review_app.server     # http://127.0.0.1:8030/
    uv run python -m analysis.review_app.server --port 8031

Routes:

    GET  /                                    the review page (files under ui/)
    GET  /ui/<file>                           the page's stylesheet and script
    GET  /api/conversations[?refresh=1]       what the page draws, with the Langfuse trace link
                                              and the review batches
    GET  /api/sessions[?refresh=1]            the raw conversations and their source
    GET  /api/rules                           SPEC.md rules and facts.yaml numbers
    GET  /api/notes                           every saved note, removed ones included
    POST /api/notes                           add a note {trace_id, note, quote?, step?}
    POST /api/notes/<id>                      reword a note {note}
    POST /api/notes/<id>/remove               remove a note; it stays in the file
    POST /api/traces/<id>/no-failure          record "no failure observed" for a trace
    GET  /api/suggestions                     AI suggestions with their status
    POST /api/suggestions/<id>/accept         turn a suggestion into a note
    POST /api/suggestions/<id>/reject         record a rejected suggestion
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

from analysis.review_app import batches, notes, suggestions
from analysis.review_app.rules import RulesPanel
from analysis.review_app.rules import load_rules as load_spec_rules
from analysis.review_app.sessions import SessionsSource
from analysis.review_app.sessions import load_sessions as load_support_sessions
from analysis.review_app.view import conversation_views

DEFAULT_PORT = 8030
UI_DIR = Path(__file__).resolve().parent / "ui"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
    ".json": "application/json",
}


class File(NamedTuple):
    """A file to send as it is, with its content type."""

    path: Path
    content_type: str


type Response = tuple[int, object] | File
type Route = tuple[re.Pattern[str], str]

_NOTE = r"/api/notes/(?P<note_id>[^/]+)"
_SUGGESTION = r"/api/suggestions/(?P<suggestion_id>[^/]+)"
_ROUTES: dict[str, list[Route]] = {
    "GET": [
        (re.compile(r"/"), "_page"),
        (re.compile(r"/ui/(?P<asset>.+)"), "_asset"),
        (re.compile(r"/api/conversations"), "_conversations"),
        (re.compile(r"/api/sessions"), "_sessions"),
        (re.compile(r"/api/rules"), "_rules"),
        (re.compile(r"/api/notes"), "_notes"),
        (re.compile(r"/api/suggestions"), "_suggestions"),
    ],
    "POST": [
        (re.compile(r"/api/notes"), "_add_note"),
        (re.compile(_NOTE), "_reword_note"),
        (re.compile(_NOTE + r"/remove"), "_remove_note"),
        (re.compile(r"/api/traces/(?P<trace_id>[^/]+)/no-failure"), "_no_failure"),
        (re.compile(_SUGGESTION + r"/accept"), "_accept_suggestion"),
        (re.compile(_SUGGESTION + r"/reject"), "_reject_suggestion"),
    ],
}


class _BadRequest(ValueError):
    """The request body is not the JSON object a route expects."""


class ReviewServer(ThreadingHTTPServer):
    """Serves the review page and routes, loading the conversations once until a refresh."""

    def __init__(
        self,
        port: int,
        load_sessions: Callable[[], SessionsSource],
        ui_dir: Path,
        load_rules: Callable[[], RulesPanel],
    ) -> None:
        super().__init__(("127.0.0.1", port), ReviewHandler)
        self.ui_dir = ui_dir.resolve()
        self.load_rules = load_rules
        self._load_sessions = load_sessions
        self._loaded: SessionsSource | None = None
        self._loading = threading.Lock()

    def sessions(self, refresh: bool) -> SessionsSource:
        return self._cached_or_loaded(refresh)

    def _cached_or_loaded(self, refresh: bool) -> SessionsSource:
        with self._loading:
            if refresh or self._loaded is None:
                self._loaded = self._load_sessions()
            return self._loaded


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self._respond("GET")

    def do_POST(self) -> None:
        self._respond("POST")

    # -- dispatch ---------------------------------------------------------

    def _respond(self, method: str) -> None:
        path, _, query = self.path.partition("?")
        for pattern, action in _ROUTES[method]:
            if match := pattern.fullmatch(path):
                self._reply(self._run(action, match, query))
                return
        self._send(404, {"error": f"unknown route: {method} {path}"})

    def _run(self, action: str, match: re.Match[str], query: str) -> Response:
        try:
            return getattr(self, action)(match, query)
        except _BadRequest as error:
            return 400, {"error": str(error)}
        except notes.UnknownNote as error:
            return 404, {"error": f"unknown note: {error}"}
        except suggestions.UnknownSuggestion as error:
            return 404, {"error": f"unknown suggestion: {error}"}

    def _reply(self, response: Response) -> None:
        if isinstance(response, File):
            self._send_file(response)
        else:
            self._send(*response)

    def _send(self, status: int, payload: object) -> None:
        self._send_bytes(status, json.dumps(payload).encode(), "application/json")

    def _send_file(self, file: File) -> None:
        self._send_bytes(200, file.path.read_bytes(), file.content_type)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as error:
            raise _BadRequest("expected a JSON body") from error
        if not isinstance(body, dict):
            raise _BadRequest("expected a JSON object")
        return body

    # -- page -------------------------------------------------------------

    def _page(self, match: re.Match[str], query: str) -> Response:
        return _ui_file(self.server.ui_dir, "index.html")

    def _asset(self, match: re.Match[str], query: str) -> Response:
        return _ui_file(self.server.ui_dir, unquote(match["asset"]))

    # -- conversations and rules ------------------------------------------

    def _conversations(self, match: re.Match[str], query: str) -> Response:
        loaded = self.server.sessions(refresh=_wants_refresh(query))
        return 200, {
            "source": loaded["source"],
            "fallback_reason": loaded["fallback_reason"],
            "trace_link": _trace_link(),
            "conversations": conversation_views(loaded["sessions"]),
            "batches": batches.load_batches(),
        }

    def _sessions(self, match: re.Match[str], query: str) -> Response:
        return 200, self.server.sessions(refresh=_wants_refresh(query))

    def _rules(self, match: re.Match[str], query: str) -> Response:
        return 200, self.server.load_rules()

    # -- notes ------------------------------------------------------------

    def _notes(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.list_notes()

    def _add_note(self, match: re.Match[str], query: str) -> Response:
        body = self._body()
        added = notes.add_note(
            _required_text(body, "trace_id"),
            _required_text(body, "note"),
            quote=_optional_text(body, "quote"),
            step=_optional_step(body),
        )
        return 201, added

    def _reword_note(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.edit_note(
            match["note_id"], _required_text(self._body(), "note")
        )

    def _remove_note(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.remove_note(match["note_id"])

    def _no_failure(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.mark_no_failure(match["trace_id"])

    # -- AI suggestions ---------------------------------------------------

    def _suggestions(self, match: re.Match[str], query: str) -> Response:
        return 200, suggestions.list_suggestions()

    def _accept_suggestion(self, match: re.Match[str], query: str) -> Response:
        return 200, suggestions.accept_suggestion(match["suggestion_id"])

    def _reject_suggestion(self, match: re.Match[str], query: str) -> Response:
        return 200, suggestions.reject_suggestion(match["suggestion_id"])


def _ui_file(ui_dir: Path, name: str) -> Response:
    """Return a file of the page folder; anything outside it, or missing, is a 404."""
    requested = (ui_dir / name).resolve()
    if ui_dir not in requested.parents or not requested.is_file():
        return 404, {"error": f"not found: {name}"}
    return File(
        requested, _CONTENT_TYPES.get(requested.suffix, "application/octet-stream")
    )


def _trace_link() -> str | None:
    """Return where a trace opens in Langfuse, followed by its id; none without Langfuse."""
    host = os.environ.get("LANGFUSE_HOST", "").rstrip("/")
    return f"{host}/trace/" if host else None


def _wants_refresh(query: str) -> bool:
    return "refresh=1" in query.split("&")


def _required_text(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _BadRequest(f"'{key}' must be non-empty text")
    return value


def _optional_text(body: dict[str, object], key: str) -> str | None:
    value = body.get(key)
    return value if isinstance(value, str) and value else None


def _optional_step(body: dict[str, object]) -> int | None:
    value = body.get("step")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def make_server(
    port: int = DEFAULT_PORT,
    load_sessions: Callable[[], SessionsSource] = load_support_sessions,
    ui_dir: Path = UI_DIR,
    load_rules: Callable[[], RulesPanel] = load_spec_rules,
) -> ReviewServer:
    return ReviewServer(port, load_sessions, ui_dir, load_rules)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace review server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def _load_langfuse_settings() -> None:
    """Load LANGFUSE_* from .env; the import is local because it pulls in tracing."""
    from observability.instrument import load_env

    load_env()


def _announce(server: ReviewServer) -> None:
    host, port = server.server_address[:2]
    print(f"review server on http://{host}:{port}/")


def _serve(server: ReviewServer) -> None:
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


def main() -> None:
    port = _arguments().port
    _load_langfuse_settings()
    server = make_server(port)
    _announce(server)
    _serve(server)


if __name__ == "__main__":
    main()
