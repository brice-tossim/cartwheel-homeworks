"""Review server for the Homework 4 trace review.

Start it from the repository root, so the analysis helpers import and the
LANGFUSE_* settings load from .env:

    uv run python -m analysis.review_app.server     # http://127.0.0.1:8030/
    uv run python -m analysis.review_app.server --port 8031

Routes:

    GET  /api/sessions[?refresh=1]      the support conversations and their source
    GET  /api/notes                     every saved note, removed ones included
    POST /api/notes                     add a note {trace_id, note, quote?, step?}
    POST /api/notes/<id>                reword a note {note}
    POST /api/notes/<id>/remove         remove a note; it stays in the file
    POST /api/traces/<id>/no-failure    record "no failure observed" for a trace
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from analysis.review_app import notes
from analysis.review_app.sessions import SessionsSource
from analysis.review_app.sessions import load_sessions as load_support_sessions

DEFAULT_PORT = 8030

type Response = tuple[int, object]
type Route = tuple[re.Pattern[str], str]

_NOTE = r"/api/notes/(?P<note_id>[^/]+)"
_ROUTES: dict[str, list[Route]] = {
    "GET": [
        (re.compile(r"/api/sessions"), "_sessions"),
        (re.compile(r"/api/notes"), "_notes"),
    ],
    "POST": [
        (re.compile(r"/api/notes"), "_add_note"),
        (re.compile(_NOTE), "_reword_note"),
        (re.compile(_NOTE + r"/remove"), "_remove_note"),
        (re.compile(r"/api/traces/(?P<trace_id>[^/]+)/no-failure"), "_no_failure"),
    ],
}


class _BadRequest(ValueError):
    """The request body is not the JSON object a route expects."""


class ReviewServer(ThreadingHTTPServer):
    """Serves the review routes, loading the conversations once until a refresh."""

    def __init__(self, port: int, load_sessions: Callable[[], SessionsSource]) -> None:
        super().__init__(("127.0.0.1", port), ReviewHandler)
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

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802  (http.server naming)
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._respond("POST")

    # -- dispatch ---------------------------------------------------------

    def _respond(self, method: str) -> None:
        path, _, query = self.path.partition("?")
        for pattern, action in _ROUTES[method]:
            if match := pattern.fullmatch(path):
                self._send(*self._run(action, match, query))
                return
        self._send(404, {"error": f"unknown route: {method} {path}"})

    def _run(self, action: str, match: re.Match[str], query: str) -> Response:
        try:
            return getattr(self, action)(match, query)
        except _BadRequest as error:
            return 400, {"error": str(error)}
        except notes.UnknownNote as error:
            return 404, {"error": f"unknown note: {error}"}

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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

    # -- routes -----------------------------------------------------------

    def _sessions(self, match: re.Match[str], query: str) -> Response:
        return 200, self.server.sessions(refresh="refresh=1" in query.split("&"))

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
        return 200, notes.edit_note(match["note_id"], _required_text(self._body(), "note"))

    def _remove_note(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.remove_note(match["note_id"])

    def _no_failure(self, match: re.Match[str], query: str) -> Response:
        return 200, notes.mark_no_failure(match["trace_id"])


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
) -> ReviewServer:
    return ReviewServer(port, load_sessions)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Homework 4 review server")
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
