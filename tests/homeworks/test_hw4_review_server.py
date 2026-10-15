"""Route tests for the Homework 4 review server (analysis/review_app/server.py).

Each test starts the real server on a free port with a stand-in conversation
loader, so nothing reaches Langfuse, and points the state folder at a
temporary directory.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from analysis.review_app.server import make_server
from analysis.review_app.sessions import SessionsSource

LOADED: SessionsSource = {
    "source": "export",
    "fallback_reason": "ConnectionError: Langfuse refused the connection",
    "sessions": [{"session_id": "s1", "traces": [{"id": "t1", "trace": []}]}],
}


class _CountingLoader:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> SessionsSource:
        self.calls += 1
        return LOADED


@pytest.fixture
def loader() -> _CountingLoader:
    return _CountingLoader()


@pytest.fixture
def base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, loader: _CountingLoader
) -> Iterator[str]:
    monkeypatch.setenv("CARTWHEEL_ANALYSIS_STATE", str(tmp_path))
    server = make_server(port=0, load_sessions=loader)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _request(
    url: str, body: object = None, method: str = "GET"
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _get(url: str) -> tuple[int, object]:
    return _request(url)


def _post(url: str, body: object) -> tuple[int, object]:
    return _request(url, body, method="POST")


def _added(base_url: str, note: str = "refund wrong") -> dict[str, object]:
    status, created = _post(f"{base_url}/api/notes", {"trace_id": "t1", "note": note})
    assert status == 201 and isinstance(created, dict)
    return created


def _notes(base_url: str) -> list[dict[str, object]]:
    _, listed = _get(f"{base_url}/api/notes")
    assert isinstance(listed, list)
    return listed


def test_sessions_route_serves_the_loaded_conversations(base_url: str) -> None:
    assert _get(f"{base_url}/api/sessions") == (200, LOADED)


def test_conversations_are_loaded_once_until_a_refresh_is_asked(
    base_url: str, loader: _CountingLoader
) -> None:
    _get(f"{base_url}/api/sessions")
    _get(f"{base_url}/api/sessions")
    assert loader.calls == 1

    _get(f"{base_url}/api/sessions?refresh=1")
    assert loader.calls == 2


def test_a_note_added_through_the_route_is_listed(base_url: str) -> None:
    status, created = _post(
        f"{base_url}/api/notes",
        {"trace_id": "t1", "note": "refund wrong", "quote": "Refund processed", "step": 3},
    )

    assert status == 201
    assert [(note["trace_id"], note["quote"], note["step"], note["note"]) for note in _notes(base_url)] == [
        ("t1", "Refund processed", 3, "refund wrong")
    ]
    assert isinstance(created, dict) and created["id"] == _notes(base_url)[0]["id"]


def test_an_edited_note_keeps_its_first_wording(base_url: str) -> None:
    created = _added(base_url)

    status, _ = _post(f"{base_url}/api/notes/{created['id']}", {"note": "the tool only queued it"})

    listed = _notes(base_url)[0]
    assert status == 200
    assert (listed["note"], [version["note"] for version in listed["history"]]) == (
        "the tool only queued it",
        ["refund wrong"],
    )


def test_a_removed_note_is_listed_as_removed(base_url: str) -> None:
    created = _added(base_url)

    status, _ = _post(f"{base_url}/api/notes/{created['id']}/remove", {})

    assert status == 200
    assert _notes(base_url)[0]["removed_ts"] is not None


def test_no_failure_route_marks_the_trace(base_url: str) -> None:
    status, _ = _post(f"{base_url}/api/traces/t1/no-failure", {})

    assert status == 200
    assert [(note["trace_id"], note["kind"]) for note in _notes(base_url)] == [("t1", "no_failure")]


@pytest.mark.parametrize(
    "body",
    [{"trace_id": "t1"}, {"trace_id": "t1", "note": "  "}, {"note": "no trace"}],
    ids=["no-text", "blank-text", "no-trace"],
)
def test_an_incomplete_note_is_refused(base_url: str, body: dict[str, object]) -> None:
    status, _ = _post(f"{base_url}/api/notes", body)

    assert status == 400
    assert _notes(base_url) == []


def test_editing_an_unknown_note_answers_404(base_url: str) -> None:
    status, _ = _post(f"{base_url}/api/notes/missing", {"note": "the tool only queued it"})

    assert status == 404


@pytest.mark.parametrize("call", [_get, lambda url: _post(url, {})], ids=["GET", "POST"])
def test_an_unknown_route_answers_404(
    base_url: str, call: Callable[[str], tuple[int, object]]
) -> None:
    status, _ = call(f"{base_url}/api/unknown")

    assert status == 404
