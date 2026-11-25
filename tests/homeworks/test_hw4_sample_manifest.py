"""Tests for the trace source that select_traces records in sample_manifest.json.

The manifest is committed, so a source file inside the repository is recorded
relative to the repository root: no path from the reviewer's machine leaks, and
next_to_label still finds the file from any working directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.helpers import next_to_label, select_traces, tools
from analysis.helpers.normalization import normalize_traces


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / "traces").mkdir(parents=True)
    traces = [{"id": f"x{i}", "features": {"turn_count": i}} for i in range(5)]
    (root / "traces" / "export.json").write_text(json.dumps({"traces": traces}))
    monkeypatch.setattr(tools, "_REPO_ROOT", root)
    return root


def _recorded_source(analysis_state: Path) -> str:
    return json.loads((analysis_state / "sample_manifest.json").read_text())["source"]


def test_a_source_inside_the_repository_is_recorded_relative_to_it(
    repo: Path, analysis_state: Path
) -> None:
    select_traces(repo / "traces" / "export.json", k=2, strategy="random")

    assert _recorded_source(analysis_state) == "traces/export.json"


def test_a_relative_source_is_recorded_from_the_repository_root(
    repo: Path, analysis_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo / "traces")

    select_traces("export.json", k=2, strategy="random")

    assert _recorded_source(analysis_state) == "traces/export.json"


def test_the_recorded_source_is_found_from_another_directory(
    repo: Path, analysis_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    select_traces(repo / "traces" / "export.json", k=2, strategy="random")
    monkeypatch.chdir(tmp_path)

    candidates = next_to_label("resumed", k=5, strategy="random")

    assert {candidate["trace_id"] for candidate in candidates} == {f"x{i}" for i in range(5)}


def test_langfuse_is_recorded_as_is(
    repo: Path, analysis_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = normalize_traces([{"id": "x0", "input": "hi", "output": "hello"}])
    monkeypatch.setattr(tools, "_load_trace_source", lambda source: live)

    select_traces("langfuse", k=1, strategy="random")

    assert _recorded_source(analysis_state) == "langfuse"
