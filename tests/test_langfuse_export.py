from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scenarios import export_langfuse
from scenarios.export_langfuse import _json_default, export_scenario_traces

type Observation = dict[str, object]


class FakeObservationsApi:
    """Serves observations in cursor pages, like ``observations_v_2.get_many``."""

    def __init__(self, observations: list[Observation], page_size: int) -> None:
        self.pages = [
            observations[start : start + page_size]
            for start in range(0, len(observations), page_size)
        ]
        self.cursors: list[str | None] = []

    def get_many(
        self, *, limit: int, cursor: str | None, fields: str
    ) -> SimpleNamespace:
        self.cursors.append(cursor)
        index = int(cursor) if cursor else 0
        has_next = index + 1 < len(self.pages)
        return SimpleNamespace(
            data=self.pages[index],
            meta=SimpleNamespace(cursor=str(index + 1) if has_next else None),
        )


def _client(observations: list[Observation], page_size: int) -> SimpleNamespace:
    api = FakeObservationsApi(observations, page_size)
    return SimpleNamespace(api=SimpleNamespace(observations_v_2=api))


def test_export_groups_observations_by_trace_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(export_langfuse, "_PAGE_SIZE", 2)
    observations: list[Observation] = [
        {
            "traceId": "t1",
            "isRootObservation": True,
            "startTime": "2026-09-05T10:00:00Z",
            "traceName": "chat",
            "metadata": {"attributes.cartwheel.scenario_id": "support-1"},
        },
        {"traceId": "noise", "metadata": {}},
        {"traceId": "t1", "metadata": {}},
        {"traceId": "t2", "metadata": {"attributes.cartwheel.scenario_id": "support-2"}},
        {"traceId": "t3", "metadata": {"attributes.cartwheel.scenario_id": "other"}},
    ]
    client = _client(observations, page_size=2)

    records = export_scenario_traces({"support-1", "support-2"}, client)

    assert client.api.observations_v_2.cursors == [None, "1", "2"]
    assert [record["id"] for record in records] == ["t1", "t2"]
    assert [record["cartwheel_scenario_id"] for record in records] == [
        "support-1",
        "support-2",
    ]
    first = records[0]
    assert first["timestamp"] == "2026-09-05T10:00:00Z"
    assert first["name"] == "chat"
    assert len(first["observations"]) == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"attributes.cartwheel.scenario_id": "support-4"},
        {"cartwheel.scenario_id": "support-4"},
        {"attributes": {"cartwheel.scenario_id": "support-4"}},
        {"attributes": json.dumps({"cartwheel.scenario_id": "support-4"})},
    ],
)
def test_export_reads_each_scenario_id_shape(metadata: dict[str, object]) -> None:
    observations: list[Observation] = [
        {"traceId": "t4", "metadata": {"scope": {}}},
        {"traceId": "t4", "metadata": metadata},
    ]

    records = export_scenario_traces({"support-4"}, _client(observations, page_size=10))

    assert [record["cartwheel_scenario_id"] for record in records] == ["support-4"]


def test_export_skips_observations_without_a_trace_id() -> None:
    observations: list[Observation] = [
        {"metadata": {"attributes.cartwheel.scenario_id": "support-5"}},
    ]

    assert export_scenario_traces({"support-5"}, _client(observations, page_size=10)) == []


def test_json_default_serializes_datetimes() -> None:
    payload = {"timestamp": datetime(2026, 9, 5, tzinfo=timezone.utc)}

    assert json.loads(json.dumps(payload, default=_json_default))["timestamp"].startswith(
        "2026-09-05"
    )
