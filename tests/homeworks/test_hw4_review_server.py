"""Route tests for the trace review server (analysis/review_app/server.py).

Each test starts the real server on a free port with a stand-in conversation
loader and rules loader, so nothing reaches Langfuse, serves the page from a
temporary folder, and points the state folder at a temporary directory.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from analysis.review_app.rules import RulesPanel
from analysis.review_app.server import make_server
from analysis.review_app.sessions import SessionsSource

LOADED: SessionsSource = {
    "source": "export",
    "fallback_reason": "ConnectionError: Langfuse refused the connection",
    "sessions": [{"session_id": "s1", "traces": [{"id": "t1", "trace": []}]}],
}

RULES: RulesPanel = {
    "rules": [{"id": "RESP-2", "text": "Do not claim that an action succeeded too early."}],
    "policy": [{"label": "Automatic refund limit", "value": "$100"}],
}

PAGE = "<!doctype html><title>Trace review</title>"
SCRIPT = "console.log('review page');"


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
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text(PAGE)
    (ui_dir / "app.js").write_text(SCRIPT)
    (tmp_path / "outside.txt").write_text("not part of the page")
    server = make_server(port=0, load_sessions=loader, ui_dir=ui_dir, load_rules=lambda: RULES)
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


def _raw_get(url: str) -> tuple[int, str, str]:
    """Fetch a page or asset: its status, content type and text."""
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read().decode()


def test_the_page_is_served_at_the_root(base_url: str) -> None:
    status, content_type, body = _raw_get(f"{base_url}/")

    assert (status, content_type.split(";")[0], body) == (200, "text/html", PAGE)


def test_page_assets_are_served_with_their_type(base_url: str) -> None:
    status, content_type, body = _raw_get(f"{base_url}/ui/app.js")

    assert (status, content_type, body) == (200, "text/javascript", SCRIPT)


@pytest.mark.parametrize("path", ["/ui/../outside.txt", "/ui/%2e%2e/outside.txt", "/ui/missing.js"])
def test_only_files_inside_the_page_folder_are_served(base_url: str, path: str) -> None:
    status, _, _ = _raw_get(f"{base_url}{path}")

    assert status == 404


def test_conversations_route_serves_what_the_page_draws(base_url: str) -> None:
    status, loaded = _get(f"{base_url}/api/conversations")

    assert status == 200 and isinstance(loaded, dict)
    assert (loaded["source"], loaded["fallback_reason"]) == ("export", LOADED["fallback_reason"])
    assert [
        (conversation["session_id"], [turn["trace_id"] for turn in conversation["turns"]])
        for conversation in loaded["conversations"]
    ] == [("s1", ["t1"])]


def test_conversations_share_the_loaded_traces_until_a_refresh(
    base_url: str, loader: _CountingLoader
) -> None:
    _get(f"{base_url}/api/conversations")
    _get(f"{base_url}/api/sessions")
    assert loader.calls == 1

    _get(f"{base_url}/api/conversations?refresh=1")
    assert loader.calls == 2


def test_rules_route_serves_the_rules_and_policy_numbers(base_url: str) -> None:
    assert _get(f"{base_url}/api/rules") == (200, RULES)


def _suggest(tmp_path: Path) -> None:
    suggestion = {"id": "s1", "trace_id": "t1", "quote": "Refund processed", "note": "too early"}
    (tmp_path / "suggestions.json").write_text(json.dumps([suggestion]))


def test_suggestions_are_listed_with_their_status(base_url: str, tmp_path: Path) -> None:
    _suggest(tmp_path)

    status, listed = _get(f"{base_url}/api/suggestions")

    assert status == 200 and isinstance(listed, list)
    assert [(entry["id"], entry["status"]) for entry in listed] == [("s1", "pending")]


def test_an_accepted_suggestion_becomes_a_note(base_url: str, tmp_path: Path) -> None:
    _suggest(tmp_path)

    status, decided = _post(f"{base_url}/api/suggestions/s1/accept", {})

    assert status == 200 and isinstance(decided, dict) and decided["status"] == "accepted"
    assert [(note["trace_id"], note["quote"], note["note"]) for note in _notes(base_url)] == [
        ("t1", "Refund processed", "too early")
    ]


def test_a_rejected_suggestion_adds_no_note(base_url: str, tmp_path: Path) -> None:
    _suggest(tmp_path)

    status, decided = _post(f"{base_url}/api/suggestions/s1/reject", {})

    assert status == 200 and isinstance(decided, dict) and decided["status"] == "rejected"
    assert _notes(base_url) == []


def test_deciding_an_unknown_suggestion_answers_404(base_url: str, tmp_path: Path) -> None:
    _suggest(tmp_path)

    status, _ = _post(f"{base_url}/api/suggestions/missing/accept", {})

    assert status == 404


def test_conversations_carry_the_langfuse_trace_link_when_langfuse_is_set(
    base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.test/")

    _, loaded = _get(f"{base_url}/api/conversations")

    assert isinstance(loaded, dict) and loaded["trace_link"] == "http://langfuse.test/trace/"


def test_conversations_carry_no_trace_link_without_langfuse(
    base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    _, loaded = _get(f"{base_url}/api/conversations")

    assert isinstance(loaded, dict) and loaded["trace_link"] is None
