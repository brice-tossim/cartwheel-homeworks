"""Export all Langfuse traces joined to a scenario JSONL file.

Usage (after loading ``.env`` and completing the runs):

    uv run python -m scenarios.export_langfuse \
      scenarios/support_scenarios.jsonl traces/support_traces.json

Reads the Langfuse Observations API v2 (``client.api.observations_v_2``),
which serves Langfuse v4 deployments. A trace is the set of observations
sharing a ``traceId``; the root observation carries the conversation input
and output, and every Cartwheel span carries ``cartwheel.scenario_id`` in
its OTel attributes (exposed as ``metadata['attributes.cartwheel.scenario_id']``).
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from observability.instrument import load_env
from scenarios.validate import load_jsonl, validate_scenarios

# Field groups covering identity, timing, conversation content, model, and
# usage for every observation, per the Observations API v2 schema.
_FIELDS = "basic,time,io,metadata,model,usage,trace_context"
_PAGE_SIZE = 100


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _attribute_scenario_id(metadata: Any) -> str | None:
    """Read the scenario id from observation metadata.

    Langfuse v4 flattens OpenTelemetry span attributes into metadata keys
    with an ``attributes.`` prefix; v3 nested them under a JSON string.
    Both shapes are accepted.
    """
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("attributes.cartwheel.scenario_id")
    if not value:
        value = metadata.get("cartwheel.scenario_id")
    if not value:
        attributes = metadata.get("attributes")
        if isinstance(attributes, str):
            try:
                attributes = json.loads(attributes)
            except ValueError:
                attributes = None
        if isinstance(attributes, dict):
            value = attributes.get("cartwheel.scenario_id")
    return str(value) if value else None


def _iter_observations(client: Any, **params: Any) -> Any:
    """Yield observations page by page via the v2 cursor."""
    cursor: str | None = None
    while True:
        response = client.api.observations_v_2.get_many(
            limit=_PAGE_SIZE, cursor=cursor, fields=_FIELDS, **params
        )
        batch = list(response.data or [])
        yield from batch
        cursor = response.meta.cursor if response.meta else None
        if not cursor or len(batch) < _PAGE_SIZE:
            return


def export_scenario_traces(
    scenario_ids: set[str], client: Any
) -> list[dict[str, Any]]:
    """Collect full trace records whose observations carry a selected scenario id.

    Walks every observation once, groups them by ``traceId``, and keeps the
    groups whose scenario id is in the selection. The root observation
    (``isRootObservation`` true) provides the conversation; children provide
    model and tool activity.
    """
    by_trace: dict[str, dict[str, Any]] = {}
    for observation in _iter_observations(client):
        if not isinstance(observation, dict):
            continue
        trace_id = observation.get("traceId")
        if not trace_id:
            continue
        metadata = observation.get("metadata")
        scenario_id = _attribute_scenario_id(metadata)
        group = by_trace.setdefault(
            trace_id,
            {"traceId": trace_id, "scenario_id": scenario_id, "observations": []},
        )
        if scenario_id and not group["scenario_id"]:
            group["scenario_id"] = scenario_id
        group["observations"].append(observation)

    matches: list[dict[str, Any]] = []
    for trace_id, group in by_trace.items():
        scenario_id = group["scenario_id"]
        if scenario_id not in scenario_ids:
            continue
        roots = [o for o in group["observations"] if o.get("isRootObservation")]
        record = {
            "id": trace_id,
            "traceId": trace_id,
            "timestamp": next(
                (o.get("startTime") for o in roots if o.get("startTime")),
                None,
            ),
            "name": next((o.get("traceName") for o in roots if o.get("traceName")), None),
            "observations": group["observations"],
        }
        record["cartwheel_scenario_id"] = scenario_id
        matches.append(record)
    return matches


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Cartwheel scenario traces from Langfuse.")
    parser.add_argument("scenarios", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="write a partial export instead of failing when a scenario has no trace",
    )
    args = parser.parse_args()

    records = load_jsonl(args.scenarios)
    validate_scenarios(records)
    scenario_ids = {record["id"] for record in records}
    load_env()
    from langfuse import Langfuse

    traces = export_scenario_traces(scenario_ids, Langfuse())
    exported_ids = {trace.get("cartwheel_scenario_id") for trace in traces}
    missing = sorted(scenario_ids - exported_ids)
    if missing and not args.allow_missing:
        preview = ", ".join(missing[:10])
        raise RuntimeError(
            f"{len(missing)} scenario ids have no exported trace ({preview}); "
            "finish the runs or pass --allow-missing for a diagnostic export"
        )
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(scenario_ids),
        "trace_count": len(traces),
        "missing_scenario_ids": missing,
        "traces": traces,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n"
    )
    print(
        f"Exported {len(traces)} traces for {len(exported_ids)} of "
        f"{len(scenario_ids)} scenarios to {args.output}"
    )


if __name__ == "__main__":
    main()
