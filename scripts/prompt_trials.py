"""Run one request N times and tally which tool the model picks.

Part C evidence: the same request, the same data, and the same prompt can
still take different paths, because the model is sampled. Running a case
several times before and after a prompt edit shows whether the edit changed
the rate, which a single conversation cannot.

Each trial re-seeds the world and sends one turn with no session history, so
the runs are independent.

Usage:
    uv run python scripts/prompt_trials.py --case esc2 --runs 5 --label before
    uv run python scripts/prompt_trials.py --case esc2 --runs 5 --label after
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from agents import RunConfig, Runner

from agent.agent import build_agent
from agent.cli import MAX_TURNS, resolve_auth
from observability.instrument import load_env

REPO_ROOT = Path(__file__).resolve().parents[1]

# One entry per requirement under test. `correct` is the tool the SPEC asks
# for; `wrong` is the tool the current prompt steers the model toward.
CASES = {
    "esc1": {
        "request": "Please refund the order 4455 in full",
        "role": "shopper",
        "user": 1,
        "correct": "issue_refund",
        "wrong": "escalate_to_human",
    },
    "esc2": {
        "request": "Can you change the email address on my Cartwheel account to new@example.com?",
        "role": "shopper",
        "user": 1,
        "correct": "escalate_to_human",
        "wrong": None,  # the observed failure calls no tool at all
    },
}


def reseed() -> None:
    subprocess.run(
        [sys.executable, "-m", "seed.generate"],
        check=True,
        capture_output=True,
    )


def tool_calls_of(new_items) -> list[dict]:
    outputs = {
        item.call_id: item.output
        for item in new_items
        if item.type == "tool_call_output_item" and item.call_id is not None
    }
    calls = []
    for item in new_items:
        if item.type != "tool_call_item":
            continue
        raw = item.raw_item
        args = (
            raw.get("arguments")
            if isinstance(raw, dict)
            else getattr(raw, "arguments", None)
        )
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                pass
        calls.append(
            {
                "name": item.tool_name,
                "arguments": args,
                "result": outputs.get(item.call_id),
            }
        )
    return calls


def classify(names: list[str], case: dict) -> str:
    """Reduce one run to a label: did it take the path the SPEC asks for?"""
    if case["correct"] in names:
        return case["correct"]
    if case["wrong"] and case["wrong"] in names:
        return case["wrong"]
    return "no_tools" if not names else "other"


async def one_run(ctx, request: str, model: str | None) -> dict:
    result = await Runner.run(
        build_agent(ctx, model=model),
        request,
        context=ctx,
        max_turns=MAX_TURNS,
        run_config=RunConfig(tracing_disabled=True),
    )
    return {
        "tool_calls": tool_calls_of(result.new_items),
        "response": result.final_output,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), default="esc2")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--label", default="before")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--out", type=Path, default=None, help="where to write the records"
    )
    args = parser.parse_args()

    load_env()
    case = CASES[args.case]
    ctx = resolve_auth(case["role"], case["user"])
    records, tally = [], Counter()

    print(f"case={args.case} label={args.label} request={case['request']!r}\n")
    for i in range(1, args.runs + 1):
        reseed()
        run = await one_run(ctx, case["request"], args.model)
        names = [c["name"] for c in run["tool_calls"]]
        picked = classify(names, case)
        tally[picked] += 1
        records.append(
            {"run": i, "case": args.case, "label": args.label, "picked": picked, **run}
        )
        print(f"run {i}: {picked:18} tools={names}")

    correct = tally[case["correct"]]
    print(f"\ntally: {dict(tally)}")
    print(f"met the requirement: {correct}/{args.runs}")
    filename = f"{args.case}_{args.label}.json"
    out = args.out or REPO_ROOT / filename
    out.write_text(json.dumps(records, indent=2))
    print("records:", filename)


if __name__ == "__main__":
    asyncio.run(main())
