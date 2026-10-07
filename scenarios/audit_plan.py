"""Independent audit of `scenarios/support_plan.jsonl`.

This is deliberately NOT built on `generate_support`'s helpers. It re-derives
every claim from the database with its own logic, so a bug in a generator
helper cannot hide itself here. It answers one question: does each record's
tuple and expected metadata actually match the seeded data?

The plan it reads is a derived artifact and is not committed. Generate it
first with `scenarios/generate_support.py`; this script stops with a message
if the file is absent.

Usage:
    uv run python -m scenarios.generate_support   # writes the plan file
    uv run python -m scenarios.audit_plan         # verifies it
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

from agent.config import db_path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "scenarios" / "support_plan.jsonl"

WORLD_ASOF = date(2026, 7, 1)
RETURN_WINDOW_DAYS = 30
DISPUTE_WINDOW_DAYS = 60
THRESHOLD_USD = 100
STORE_OVERRIDES = {2: 14, 7: 45, 10: 21, 13: 7}


def age_of(delivered_at: str | None) -> int | None:
    if not delivered_at:
        return None
    y, m, d = (int(x) for x in delivered_at.split("-"))
    return (WORLD_ASOF - date(y, m, d)).days


def window_for(store_id: int) -> int:
    return STORE_OVERRIDES.get(store_id, RETURN_WINDOW_DAYS)


def policy_for(store_id: int) -> str:
    return {
        2: "store-juniper-home-goods-policy",
        7: "store-northwind-books-policy",
        10: "store-meridian-cycles-policy",
        13: "store-saltbox-pantry-policy",
    }.get(store_id, "cw-returns")


def applicable_for(store_id: int) -> str:
    if store_id in STORE_OVERRIDES:
        return "store_override_stricter" if STORE_OVERRIDES[store_id] < RETURN_WINDOW_DAYS else "store_override_looser"
    return "platform_default"


def main() -> None:
    if not PLAN_PATH.exists():
        raise SystemExit(
            f"plan not found: {PLAN_PATH}\n"
            "It is a derived artifact and is not committed. Generate it first:\n"
            "    uv run python -m scenarios.generate_support"
        )

    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    orders = {r["id"]: r for r in conn.execute("SELECT * FROM orders")}
    products = {r["id"]: r for r in conn.execute("SELECT * FROM products")}
    title_counts = Counter(r["title"] for r in products.values())
    dq = {
        r["case_id"]: (r["entity_type"], r["entity_id"])
        for r in conn.execute("SELECT case_id, entity_type, entity_id FROM data_quality_cases")
    }

    records = [json.loads(line) for line in PLAN_PATH.read_text().splitlines() if line.strip()]
    problems: list[str] = []
    order_uses: Counter[int] = Counter()
    product_uses: Counter[int] = Counter()
    dq_counts: Counter[str] = Counter()

    def fail(rid: str, msg: str) -> None:
        problems.append(f"{rid}: {msg}")

    for rec in records:
        rid = rec["id"]
        t = rec["tuple"]
        exp = rec["expected"]
        outcome = exp.get("outcome", "")
        oid = t.get("order_id")
        pid = t.get("product_id")

        if oid is not None:
            order_uses[oid] += 1
            o = orders.get(oid)
            if o is None:
                fail(rid, f"order {oid} does not exist")
                continue
            age = age_of(o["delivered_at"])
            win = window_for(o["store_id"])

            # record_state must match the real status/age band
            if o["status"] == "delivered":
                if o["refund_eligible"]:
                    expected_state = "order_in_window"
                elif age is not None and age <= DISPUTE_WINDOW_DAYS:
                    expected_state = "order_past_window"
                else:
                    expected_state = "order_past_dispute_window"
            else:
                expected_state = f"order_{o['status']}"
            if t["record_state"] not in (expected_state, "order_outside_scope",
                                         "order_window_last_day", "order_window_day_after",
                                         "order_missing_delivery_date", "order_reversed_dates",
                                         "order_store_mismatch"):
                fail(rid, f"record_state={t['record_state']} but order is {expected_state}")

            # applicable_policy must match the store
            if t["applicable_policy"] not in ("none", applicable_for(o["store_id"])):
                fail(rid, f"applicable_policy={t['applicable_policy']} but store {o['store_id']} is {applicable_for(o['store_id'])}")

            # expected outcome must be consistent with the data
            if outcome.startswith("report the order as "):
                want = outcome.removeprefix("report the order as ")
                # correction scenarios append "and identify which order it is"
                want = want.split(" and identify which order it is")[0]
                if o["status"] != want:
                    fail(rid, f"outcome says status {want} but order is {o['status']}")
            elif outcome == "deny the refund because the return window has passed":
                if age is None or age <= win:
                    fail(rid, f"refund denied but age={age} window={win}")
            elif outcome.startswith("issue the refund"):
                if not o["refund_eligible"]:
                    fail(rid, "refund issued but order not eligible")
                amt = t.get("refund_amount_usd")
                if amt is None or amt > o["total_cents"] / 100:
                    fail(rid, f"refund amount {amt} exceeds total {o['total_cents']/100}")
                if amt is not None and amt > THRESHOLD_USD:
                    fail(rid, f"auto-issue but amount {amt} above threshold")
            elif outcome.startswith("queue the refund"):
                if not o["refund_eligible"]:
                    fail(rid, "refund queued but order not eligible")
                amt = t.get("refund_amount_usd")
                if amt is None or amt <= THRESHOLD_USD:
                    fail(rid, f"queued but amount {amt} not above threshold")
                if amt is not None and amt > o["total_cents"] / 100:
                    fail(rid, f"refund amount {amt} exceeds total {o['total_cents']/100}")
            elif outcome == "cancel the order because it has not shipped":
                if o["status"] != "placed":
                    fail(rid, f"cancel but status {o['status']}")
            elif outcome == "deny the cancellation because the order has already shipped":
                if o["status"] != "shipped":
                    fail(rid, f"cancel denied but status {o['status']}")
            elif outcome.startswith("escalate the dispute"):
                if age is None or age > DISPUTE_WINDOW_DAYS:
                    fail(rid, f"dispute in-window but age={age}")
            elif outcome.startswith("escalate to a human, say the dispute window has passed"):
                if age is None or age <= DISPUTE_WINDOW_DAYS:
                    fail(rid, f"dispute past-window but age={age}")
            elif outcome == "state that today is the last day of the return window":
                if age != win:
                    fail(rid, f"last-day but age={age} window={win}")
            elif outcome == "state that the return window has passed":
                if age != win + 1:
                    fail(rid, f"day-after but age={age} window={win}")
            elif outcome == "accept the return because the store's 45-day window still applies":
                if o["store_id"] != 7 or not (RETURN_WINDOW_DAYS < age <= 45):
                    fail(rid, f"looser but store={o['store_id']} age={age}")
            elif outcome == "deny access without revealing order details or whether the order exists":
                if o["user_id"] == t["user_id"]:
                    fail(rid, "authz scenario but caller owns the order")

            # policy_id must match the store when it names a store policy
            if t.get("policy_id") and t["policy_id"].startswith("store-"):
                if t["policy_id"] != policy_for(o["store_id"]):
                    fail(rid, f"policy_id={t['policy_id']} but store {o['store_id']} -> {policy_for(o['store_id'])}")

        if pid is not None:
            product_uses[pid] += 1
            prod = products.get(pid)
            if prod is None:
                fail(rid, f"product {pid} does not exist")
                continue
            if outcome == "report the matching product with its store and price":
                if not prod["title"].strip():
                    fail(rid, "product search but title is empty")
                if title_counts[prod["title"]] > 1:
                    fail(rid, f"product search but title {prod['title']!r} is duplicated ({title_counts[prod['title']]}x)")
                if prod["price_cents"] <= 0:
                    fail(rid, f"product search but price {prod['price_cents']} is not positive")

        dq_id = rec.get("data_quality_case_id")
        if dq_id:
            dq_counts[dq_id] += 1
            entity_type, entity_id = dq[dq_id]
            key = f"{entity_type}_id"
            if t.get(key) != entity_id:
                fail(rid, f"{key}={t.get(key)} but {dq_id} expects {entity_id}")

    # global invariants
    # The three damaged orders are each referenced by their five data-quality
    # scenarios, so they are the only orders allowed to repeat.
    damaged_orders = {eid for etype, eid in dq.values() if etype == "order"}
    damaged_products = {eid for etype, eid in dq.values() if etype == "product"}
    for oid, n in order_uses.items():
        if n > 1 and oid not in damaged_orders:
            problems.append(f"order {oid} referenced {n} times (must be unique)")
    for pid, n in product_uses.items():
        if n > 1 and pid not in damaged_products:
            problems.append(f"product {pid} referenced {n} times (must be unique)")
    for case_id in dq:
        if dq_counts[case_id] != 5:
            problems.append(f"{case_id}: {dq_counts[case_id]} scenarios, expected 5")

    coverage = sum(1 for r in records if r["scenario_group"] == "coverage")
    challenge = sum(1 for r in records if r["scenario_group"] == "challenge")
    print(f"records={len(records)} coverage={coverage} challenge={challenge}")
    print(f"distinct orders={len(order_uses)} distinct products={len(product_uses)}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("\nOK: every record's tuple and expected metadata match the database.")


if __name__ == "__main__":
    main()
