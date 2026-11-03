"""Deterministic planner for the Homework 3 final scenario set.

This script builds the *plan* for `scenarios/support_scenarios.jsonl`: the
250 tuples and their grounded expected metadata, selected from the seeded
database. It does not write user messages; a separate step generates those
with per-conversation model calls (see `scenarios/skill/SKILL.md`, Step 5).

Why a script rather than hand-authored tuples:

  - Every record reference is read from the database, so the grounding is
    verifiable and cannot drift from the seeded data.
  - The selection is seeded (`SEED`), so anyone who runs the script against
    the same database gets the same plan. The generated *prose* is not
    reproducible without caching, but the plan is.

Design rules enforced here (see `scenarios/scenario-dimensions.md`):

  - Composition is fixed: 175 coverage + 75 challenge, 5 challenge scenarios
    per documented data-quality case.
  - Every order reference is unique across the whole plan (`used_orders`), so
    a state-changing scenario can never invalidate a read scenario's expected
    metadata. The handout requires state-changing scenarios to target
    distinct records.
  - Boundary scenarios select orders at the *exact* age that makes the rule
    bite (last day vs. day after), not merely "some old order".
  - Damaged products (2, 3, 4) are excluded from ordinary product searches;
    they appear only in their data-quality challenge scenarios.

Usage:
    uv run python -m seed.generate                 # reset the data first
    uv run python -m scenarios.generate_support    # writes the plan file

Output: `scenarios/support_plan.jsonl` (tuples + expected, no messages).

This output is a *derived* artifact and is intentionally not committed: it is
reproduced byte-for-byte from this script plus the seeded database, so keeping
a copy would only risk drifting from the source. Regenerate it whenever you
need it, then verify it with `scenarios/audit_plan.py`, which re-derives every
claim from the database independently and refuses to run if the plan is
missing.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from agent.config import db_path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "scenarios" / "support_plan.jsonl"

WORLD_ASOF = date(2026, 7, 1)
SEED = 20260701

# facts.yaml
RETURN_WINDOW_DAYS = 30
DISPUTE_WINDOW_DAYS = 60
THRESHOLD_USD = 100

# Store overrides, read from the store policy docs (facts.yaml precedence:
# store_over_platform). Only stores with an override are listed.
STORE_OVERRIDES = {
    2: (14, "store-juniper-home-goods-policy"),   # stricter
    7: (45, "store-northwind-books-policy"),      # looser
    10: (21, "store-meridian-cycles-policy"),     # stricter
    13: (7, "store-saltbox-pantry-policy"),       # stricter
}

# Stores that charge a restocking fee on opened items.
RESTOCKING_STORES = {5, 15}

# Products that carry a documented data-quality defect. They must not appear
# in ordinary product searches; they belong to their challenge scenarios.
DAMAGED_PRODUCT_IDS = {2, 3, 4}

USER_STYLES = [
    "neutral_conversational",
    "terse_fragmentary",
    "typo_heavy",
    "confused_rambling",
    "frustrated_impatient",
    "repetitive_pressuring",
    "operational_shorthand",
    "requests_short_plain_answer",
]

# The six documented damaged records (data_quality_cases).
DQ_CASES = [
    ("dq-order-missing-delivery-date", "order", 8002),
    ("dq-order-reversed-dates", "order", 8001),
    ("dq-order-store-mismatch", "order", 8003),
    ("dq-product-duplicate-title", "product", 2),
    ("dq-product-invalid-price", "product", 4),
    ("dq-product-missing-title", "product", 3),
]

# Coverage allocation. The sum must be 175; `main` asserts it.
COVERAGE_ALLOCATION = {
    "order_status": 24,
    "refund": 30,
    "product_search": 12,
    "policy_question": 12,
    "cancellation": 12,
    "return_deadline": 12,
    "dispute": 8,
    "out_of_scope": 12,
    "merchant": 28,
    "support": 25,
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _days_since(delivered_at: str | None) -> int | None:
    if not delivered_at:
        return None
    y, m, d = (int(x) for x in delivered_at.split("-"))
    return (WORLD_ASOF - date(y, m, d)).days


def _effective_window(store_id: int) -> int:
    override = STORE_OVERRIDES.get(store_id)
    return override[0] if override else RETURN_WINDOW_DAYS


def _policy_for_store(store_id: int) -> str:
    override = STORE_OVERRIDES.get(store_id)
    return override[1] if override else "cw-returns"


def _applicable_policy(store_id: int) -> str:
    if store_id in STORE_OVERRIDES:
        window = STORE_OVERRIDES[store_id][0]
        return "store_override_stricter" if window < RETURN_WINDOW_DAYS else "store_override_looser"
    return "platform_default"


def _merchant_for_store(conn: sqlite3.Connection, store_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM users WHERE role='merchant' AND store_id=? LIMIT 1", (store_id,)
    ).fetchone()
    return row["id"]


def _support_user(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM users WHERE role='support' LIMIT 1").fetchone()
    return row["id"]


def _state_for_order(order: sqlite3.Row) -> str:
    """The `record_state` value that matches an order's real status."""
    status = order["status"]
    if status == "placed":
        return "order_placed"
    if status == "shipped":
        return "order_shipped"
    if status == "cancelled":
        return "order_cancelled"
    if status == "refunded":
        return "order_refunded"
    if status == "delivered":
        if order["refund_eligible"]:
            return "order_in_window"
        age = _days_since(order["delivered_at"])
        if age is not None and age <= DISPUTE_WINDOW_DAYS:
            return "order_past_window"
        return "order_past_dispute_window"
    return "order_unknown"


# ---------------------------------------------------------------------------
# Record selection
# ---------------------------------------------------------------------------


def orders(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM orders WHERE {where} ORDER BY id", params
    ).fetchall()


def products(conn: sqlite3.Connection, where: str = "1=1", params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT * FROM products WHERE {where} ORDER BY id", params
    ).fetchall()


def in_window_orders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return orders(conn, "status='delivered' AND refund_eligible=1")


def past_window_orders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return orders(
        conn, "status='delivered' AND refund_eligible=0 AND delivered_at IS NOT NULL"
    )


def past_within_dispute(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Past the return window but still inside the 60-day dispute window.

    This is the plan's `order_past_window` state: a refund is denied, but a
    dispute would still be in window.
    """
    return [
        o
        for o in past_window_orders(conn)
        if _days_since(o["delivered_at"]) <= DISPUTE_WINDOW_DAYS
    ]


def past_beyond_dispute(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Past the 60-day dispute window (`order_past_dispute_window`)."""
    return [
        o
        for o in past_window_orders(conn)
        if _days_since(o["delivered_at"]) > DISPUTE_WINDOW_DAYS
    ]


def orders_at_age(
    conn: sqlite3.Connection, age: int, store_ids: set[int] | None = None
) -> list[sqlite3.Row]:
    """Delivered orders whose delivery is exactly `age` days before WORLD_ASOF."""
    rows = orders(conn, "status='delivered' AND delivered_at IS NOT NULL")
    out = [o for o in rows if _days_since(o["delivered_at"]) == age]
    if store_ids is not None:
        out = [o for o in out if o["store_id"] in store_ids]
    return out


# ---------------------------------------------------------------------------
# Expected-metadata builders
# ---------------------------------------------------------------------------


def expected_order_status(order: sqlite3.Row) -> dict[str, Any]:
    return {
        "evaluation": "objective",
        "outcome": f"report the order as {order['status']}",
        "reason": f"Order {order['id']} has status {order['status']}.",
        "source": {"type": "sql", "reference": f"orders.id={order['id']}"},
    }


def expected_order_status_identified(order: sqlite3.Row) -> dict[str, Any]:
    """Like `expected_order_status`, but the agent must name the order.

    Used for `correction_across_turns` scenarios, where the user has several
    orders at the same store and corrects which one they mean. The user cannot
    confirm the answer unless the agent says which order it is answering
    about, so the outcome requires that identification; otherwise a reply
    about the wrong order would still satisfy the expectation.
    """
    return {
        "evaluation": "objective",
        "outcome": (
            f"report the order as {order['status']} and identify which order it is"
        ),
        "reason": (
            f"Order {order['id']} has status {order['status']}; the user has "
            f"several orders at this store, so the reply must name the one it "
            f"answers about."
        ),
        "source": {"type": "sql", "reference": f"orders.id={order['id']}"},
    }


def expected_refund_denied(order: sqlite3.Row, window: int, policy_id: str) -> dict[str, Any]:
    age = _days_since(order["delivered_at"])
    return {
        "evaluation": "objective",
        "outcome": "deny the refund because the return window has passed",
        "reason": (
            f"The order was delivered {age} days ago, past the {window}-day window "
            f"that applies to this store."
        ),
        "source": {"type": "policy_document", "reference": policy_id},
    }


def _refund_band(amount: float) -> str:
    if amount > THRESHOLD_USD:
        return "above_threshold"
    if amount == THRESHOLD_USD:
        return "at_threshold"
    return "below_threshold"


def expected_refund_eligible(order: sqlite3.Row, amount: float) -> dict[str, Any]:
    band = _refund_band(amount)
    if band == "above_threshold":
        outcome = "queue the refund for human approval because it is above the threshold"
    else:
        outcome = "issue the refund because the order is eligible and the amount is at or below the threshold"
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": (
            f"Order {order['id']} is refund-eligible and the amount ${amount:.2f} is "
            f"{'above' if band == 'above_threshold' else 'at or below'} the ${THRESHOLD_USD} threshold."
        ),
        "source": {"type": "eligibility_function", "reference": "is_refund_eligible"},
    }


def expected_cancel(order: sqlite3.Row) -> dict[str, Any]:
    return {
        "evaluation": "objective",
        "outcome": "cancel the order because it has not shipped",
        "reason": f"Order {order['id']} is still in the placed state.",
        "source": {"type": "sql", "reference": f"orders.id={order['id']}"},
    }


def expected_cancel_denied(order: sqlite3.Row) -> dict[str, Any]:
    return {
        "evaluation": "objective",
        "outcome": "deny the cancellation because the order has already shipped",
        "reason": f"Order {order['id']} has status {order['status']}, so it can no longer be cancelled.",
        "source": {"type": "policy_document", "reference": "cw-cancellations"},
    }


def expected_dispute(order: sqlite3.Row, in_window: bool) -> dict[str, Any]:
    if in_window:
        outcome = "escalate the dispute to a human without implying a dispute was opened"
        reason = f"Order {order['id']} is within the {DISPUTE_WINDOW_DAYS}-day dispute window; disputes are never resolved automatically."
    else:
        outcome = "escalate to a human, say the dispute window has passed, and do not imply a dispute was opened"
        reason = f"Order {order['id']} is past the {DISPUTE_WINDOW_DAYS}-day dispute window; disputes are never resolved automatically."
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": reason,
        "source": {"type": "policy_document", "reference": "cw-disputes"},
    }


def expected_return_deadline(
    order: sqlite3.Row, window: int, policy_id: str, boundary: str
) -> dict[str, Any]:
    age = _days_since(order["delivered_at"])
    if boundary == "last_day":
        outcome = "state that today is the last day of the return window"
    elif boundary == "day_after":
        outcome = "state that the return window has passed"
    else:
        outcome = "state the return deadline from the delivery date"
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": f"Order {order['id']} was delivered {age} days ago; the applicable window is {window} days.",
        "source": {"type": "policy_document", "reference": policy_id},
    }


def expected_policy(policy_id: str, outcome: str, reason: str) -> dict[str, Any]:
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": reason,
        "source": {"type": "policy_document", "reference": policy_id},
    }


def expected_out_of_scope(criterion: str, reference: str) -> dict[str, Any]:
    return {
        "evaluation": "human_judgment",
        "criterion": criterion,
        "source": {"type": "specification", "reference": reference},
    }


def expected_dq(case_id: str, outcome: str, reason: str) -> dict[str, Any]:
    return {
        "evaluation": "objective",
        "outcome": outcome,
        "reason": reason,
        "source": {"type": "data_quality_table", "reference": case_id},
    }


# ---------------------------------------------------------------------------
# Tuple builder
# ---------------------------------------------------------------------------


def make_tuple(
    *,
    role: str,
    user_id: int,
    intent: str,
    record_state: str,
    applicable_policy: str,
    tools_needed: str,
    difficulty: str,
    user_style: str,
    turn_count: int = 1,
    order_id: int | None = None,
    store_id: int | None = None,
    product_id: int | None = None,
    policy_id: str | None = None,
    refund_amount_usd: float | None = None,
    refund_amount_band: str | None = None,
    item_condition: str | None = None,
    side_effect: str = "read_only",
) -> dict[str, Any]:
    return {
        "role": role,
        "user_id": user_id,
        "intent": intent,
        "record_state": record_state,
        "applicable_policy": applicable_policy,
        "tools_needed": tools_needed,
        "turn_count": turn_count,
        "difficulty": difficulty,
        "user_style": user_style,
        "order_id": order_id,
        "store_id": store_id,
        "product_id": product_id,
        "policy_id": policy_id,
        "refund_amount_usd": refund_amount_usd,
        "refund_amount_band": refund_amount_band,
        "item_condition": item_condition,
        "side_effect": side_effect,
    }


# ---------------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------------


class Planner:
    def __init__(self, conn: sqlite3.Connection, rng: random.Random) -> None:
        self.conn = conn
        self.rng = rng
        self.records: list[dict[str, Any]] = []
        # Every order referenced anywhere in the plan. A state-changing
        # scenario must not share an order with any other scenario, and a read
        # scenario must not read an order a write scenario mutates.
        self.used_orders: set[int] = set()
        self.used_products: set[int] = set()
        # Orders claimed for a boundary block. Greedy blocks skip these so a
        # sparse boundary pool cannot be consumed before its block runs.
        self.reserved: set[int] = set()
        self._style_queue: list[str] = []

    def style(self) -> str:
        """Return a user style, cycling through a shuffled deck for even spread."""
        if not self._style_queue:
            self._style_queue = list(USER_STYLES)
            self.rng.shuffle(self._style_queue)
        return self._style_queue.pop()

    def reserve(self, pool: list[sqlite3.Row], n: int) -> list[sqlite3.Row]:
        """Claim the first `n` unused orders in `pool` for a boundary block."""
        picked: list[sqlite3.Row] = []
        for o in pool:
            if o["id"] in self.used_orders or o["id"] in self.reserved:
                continue
            self.reserved.add(o["id"])
            picked.append(o)
            if len(picked) == n:
                break
        if len(picked) < n:
            raise RuntimeError(f"cannot reserve {n} orders from pool (got {len(picked)})")
        return picked

    def pick_order(self, pool: list[sqlite3.Row], *, allow_reserved: bool = False) -> sqlite3.Row:
        """Return the first order in `pool` not yet referenced by the plan.

        Reserved orders are skipped unless `allow_reserved` is set, which only
        the boundary blocks that own them do.
        """
        for o in pool:
            if o["id"] in self.used_orders:
                continue
            if not allow_reserved and o["id"] in self.reserved:
                continue
            self.used_orders.add(o["id"])
            return o
        raise RuntimeError("order pool exhausted")

    def pick_product(self, pool: list[sqlite3.Row]) -> sqlite3.Row:
        for prod in pool:
            if prod["id"] not in self.used_products:
                self.used_products.add(prod["id"])
                return prod
        raise RuntimeError("product pool exhausted")

    def add(
        self,
        *,
        group: str,
        tuple_: dict[str, Any],
        expected: dict[str, Any],
        dq_id: str | None = None,
    ) -> None:
        self.records.append(
            {
                "id": f"support-{len(self.records) + 1:04d}",
                "scenario_group": group,
                "data_quality_case_id": dq_id,
                "tuple": tuple_,
                "expected": expected,
            }
        )


def build_coverage(p: Planner) -> dict[str, list[sqlite3.Row]]:
    conn = p.conn
    in_win = in_window_orders(conn)
    past = past_within_dispute(conn)
    placed = orders(conn, "status='placed'")
    shipped = orders(conn, "status='shipped'")
    cancelled = orders(conn, "status='cancelled'")
    refunded = orders(conn, "status='refunded'")
    # Only products whose title is unique in the catalog: a search for a
    # duplicated title returns several matches, which would contradict the
    # "report the matching product" expectation. Damaged products are also
    # excluded; they belong to their data-quality challenge scenarios.
    normal_products = products(
        conn,
        "id NOT IN (2,3,4) AND title NOT IN "
        "(SELECT title FROM products GROUP BY title HAVING count(*) > 1)",
    )
    support = _support_user(conn)

    # Reserve every sparse boundary pool before any greedy block can consume
    # it. The platform last-day/day-after pools are small and sit at low ids
    # that the order_status and support blocks would otherwise take first; the
    # store-7 looser orders sit inside the in-window pool the support block
    # drains. Reserving up front makes the plan independent of block order.
    platform_stores = set(range(1, 21)) - set(STORE_OVERRIDES)
    last_day = p.reserve(orders_at_age(conn, RETURN_WINDOW_DAYS, platform_stores), 3)
    day_after = p.reserve(orders_at_age(conn, RETURN_WINDOW_DAYS + 1, platform_stores), 3)
    stricter = p.reserve(
        [
            o
            for o in past_window_orders(conn)
            if o["store_id"] in (2, 10, 13)
            and _days_since(o["delivered_at"]) <= RETURN_WINDOW_DAYS
        ],
        8,
    )
    looser = p.reserve(
        [
            o
            for o in in_win
            if o["store_id"] == 7
            and RETURN_WINDOW_DAYS < _days_since(o["delivered_at"]) <= _effective_window(7)
        ],
        6,
    )
    big = p.reserve(
        [o for o in in_win if o["total_cents"] >= int(THRESHOLD_USD * 100) + 1], 8
    )
    other = p.reserve([o for o in in_win if o["user_id"] != 1], 8)

    # --- order_status (24) ---
    status_pools = [
        ("order_placed", placed),
        ("order_shipped", shipped),
        ("order_cancelled", cancelled),
        ("order_refunded", refunded),
        ("order_in_window", in_win),
    ]
    for i in range(COVERAGE_ALLOCATION["order_status"]):
        state, pool = status_pools[i % len(status_pools)]
        o = p.pick_order(pool)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="order_status",
                record_state=state,
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
            ),
            expected=expected_order_status(o),
        )

    # --- refund (30): 18 eligible, 12 past-window ---
    for _ in range(18):
        o = p.pick_order(in_win)
        amount = round(o["total_cents"] / 100, 2)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="refund",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id=_policy_for_store(o["store_id"]),
                refund_amount_usd=amount,
                refund_amount_band=_refund_band(amount),
                side_effect="write",
            ),
            expected=expected_refund_eligible(o, amount),
        )
    for _ in range(12):
        o = p.pick_order(past)
        window = _effective_window(o["store_id"])
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="refund",
                record_state="order_past_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id=_policy_for_store(o["store_id"]),
            ),
            expected=expected_refund_denied(o, window, _policy_for_store(o["store_id"])),
        )

    # --- product_search (12): normal products only ---
    for _ in range(COVERAGE_ALLOCATION["product_search"]):
        prod = p.pick_product(normal_products)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=1,
                intent="product_search",
                record_state="product_normal",
                applicable_policy="none",
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                product_id=prod["id"],
                store_id=prod["store_id"],
            ),
            expected={
                "evaluation": "objective",
                "outcome": "report the matching product with its store and price",
                "reason": f"Product {prod['id']} ({prod['title']}) exists in the catalog.",
                "source": {"type": "sql", "reference": f"products.id={prod['id']}"},
            },
        )

    # --- policy_question (12) ---
    policy_topics = [
        ("cw-returns", "explain the 30-day return window counted from delivery", "The platform return window is 30 days from delivery."),
        ("cw-refunds", "explain the refund approval threshold", "Refunds above $100 are queued for human approval."),
        ("cw-cancellations", "explain that orders can be cancelled only before shipment", "Cancellation is allowed only before shipment."),
        ("cw-disputes", "explain the 60-day dispute window", "Buyers can dispute a charge for 60 days after delivery."),
        ("cw-restocking-fees", "explain the restocking fee rule for opened items", "A store may charge up to 15 percent on opened items if it opted in."),
        ("cw-shipping", "explain the shipping time expectations", "Handling and transit times are bounded by the shipping policy."),
        ("cw-payouts", "explain the merchant payout schedule", "Payouts are weekly on Fridays with processing time."),
        ("cw-escalations", "explain the escalation SLA", "A human responds to an escalation within 24 hours."),
        ("cw-store-overrides", "explain that store overrides take precedence", "A store override takes precedence over the platform default."),
        ("cw-roles", "explain what each role can do", "Roles have different permissions under the access matrix."),
    ]
    for i in range(COVERAGE_ALLOCATION["policy_question"]):
        if i == 0:
            # The first slot is a broad "policy rundown" question that spans
            # several topics (returns, refund approvals, restocking fees). A
            # real user asks this way, so the expectation must cover every
            # topic the user raised and require the agent to offer to go
            # deeper, rather than grading only one document. The narrow,
            # single-topic questions are covered by the other slots.
            p.add(
                group="coverage",
                tuple_=make_tuple(
                    role="shopper",
                    user_id=1,
                    intent="policy_question",
                    record_state="policy_page",
                    applicable_policy="platform_default",
                    tools_needed="several_calls",
                    difficulty="well_specified",
                    user_style=p.style(),
                    policy_id="cw-returns",
                ),
                expected={
                    "evaluation": "human_judgment",
                    "criterion": (
                        "The agent answers every topic the user raised (the "
                        "return window, the refund approval threshold, and the "
                        "restocking fee) and offers to go deeper on any one of "
                        "them, rather than answering only one topic."
                    ),
                    "source": {"type": "specification", "reference": "RESP-1, RESP-4"},
                },
            )
            continue
        pid, outcome, reason = policy_topics[i % len(policy_topics)]
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=1,
                intent="policy_question",
                record_state="policy_page",
                applicable_policy="platform_default",
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                policy_id=pid,
            ),
            expected=expected_policy(pid, outcome, reason),
        )

    # --- cancellation (12): 6 placed (allowed), 6 shipped (denied) ---
    for _ in range(6):
        o = p.pick_order(placed)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="cancellation",
                record_state="order_placed",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-cancellations",
                side_effect="write",
            ),
            expected=expected_cancel(o),
        )
    for _ in range(6):
        o = p.pick_order(shipped)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="cancellation",
                record_state="order_shipped",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-cancellations",
            ),
            expected=expected_cancel_denied(o),
        )

    # --- return_deadline (12): 6 in-window, 3 last day, 3 day after ---
    deadline_plan = (
        [("in_window", in_win, False)] * 6
        + [("last_day", last_day, True)] * 3
        + [("day_after", day_after, True)] * 3
    )
    for boundary, pool, reserved in deadline_plan:
        o = p.pick_order(pool, allow_reserved=reserved)
        window = _effective_window(o["store_id"])
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="return_deadline",
                record_state=(
                    "order_window_last_day"
                    if boundary == "last_day"
                    else "order_window_day_after"
                    if boundary == "day_after"
                    else "order_in_window"
                ),
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="one_call",
                difficulty="boundary" if boundary != "in_window" else "well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id=_policy_for_store(o["store_id"]),
            ),
            expected=expected_return_deadline(o, window, _policy_for_store(o["store_id"]), boundary),
        )

    # --- dispute (8): 4 in window, 4 past ---
    for _ in range(4):
        o = p.pick_order(in_win)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="dispute",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-disputes",
                side_effect="write",
            ),
            expected=expected_dispute(o, in_window=True),
        )
    for _ in range(4):
        o = p.pick_order(past_beyond_dispute(conn))
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="dispute",
                record_state="order_past_dispute_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-disputes",
                side_effect="write",
            ),
            expected=expected_dispute(o, in_window=False),
        )

    # --- out_of_scope (12): 4 intents x 3 ---
    oos = {
        "legal_advice": ("The agent declines to give legal advice in one or two sentences and points to what it can help with.", "SCOPE-2, RESP-4"),
        "payment_card_change": ("The agent declines to change payment-card details and explains it cannot handle payment credentials.", "SCOPE-2, RESP-4"),
        "account_change": ("The agent escalates the account change to a human instead of refusing, because account changes go to a human.", "ESC-2, RESP-4"),
        "out_of_cartwheel": ("The agent declines the out-of-scope request in one or two sentences and points to what it can help with.", "SCOPE-2, RESP-4"),
    }
    # Explicit per-slot intents. The last slot's generated message asks to
    # reconfigure the account type, so it is labeled account_change rather than
    # out_of_cartwheel.
    oos_intents = [
        "legal_advice", "payment_card_change", "account_change", "out_of_cartwheel",
        "legal_advice", "payment_card_change", "account_change", "out_of_cartwheel",
        "legal_advice", "payment_card_change", "account_change", "account_change",
    ]
    for intent in oos_intents:
        criterion, ref = oos[intent]
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="shopper",
                user_id=1,
                intent=intent,
                record_state="none",
                applicable_policy="none",
                tools_needed="none",
                difficulty="well_specified",
                user_style=p.style(),
            ),
            expected=expected_out_of_scope(criterion, ref),
        )

    # --- merchant coverage (28) ---
    merchants = conn.execute(
        "SELECT id, store_id FROM users WHERE role='merchant' ORDER BY id"
    ).fetchall()
    for i in range(COVERAGE_ALLOCATION["merchant"]):
        m = merchants[i % len(merchants)]
        store_orders = orders(conn, "store_id=?", (m["store_id"],))
        o = p.pick_order(store_orders)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="merchant",
                user_id=m["id"],
                intent="order_status",
                record_state=_state_for_order(o),
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
            ),
            expected=expected_order_status(o),
        )

    # --- support coverage (25) ---
    for _ in range(COVERAGE_ALLOCATION["support"]):
        o = p.pick_order(in_win)
        p.add(
            group="coverage",
            tuple_=make_tuple(
                role="support",
                user_id=support,
                intent="order_status",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
            ),
            expected=expected_order_status(o),
        )

    return {
        "last_day": last_day,
        "day_after": day_after,
        "stricter": stricter,
        "looser": looser,
        "big": big,
        "other": other,
    }


def build_challenge(p: Planner, boundary: dict[str, list[sqlite3.Row]]) -> None:
    conn = p.conn
    in_win = in_window_orders(conn)
    past = past_window_orders(conn)
    support = _support_user(conn)
    stricter = boundary["stricter"]
    looser = boundary["looser"]
    big = boundary["big"]
    other = boundary["other"]

    # --- 30 damaged-record scenarios: 5 per case ---
    dq_expected = {
        "dq-order-missing-delivery-date": (
            "do not compute a return deadline from a missing delivery date",
            "The order has a delivered status but no delivery date.",
        ),
        "dq-order-reversed-dates": (
            "identify the inconsistent chronology and escalate instead of asserting a timeline",
            "The recorded shipment date occurs after the delivery date.",
        ),
        "dq-order-store-mismatch": (
            "preserve authorization and escalate the inconsistent record",
            "The order store differs from the store owning the referenced product.",
        ),
        "dq-product-duplicate-title": (
            "present all matches with their distinguishing attributes and do not present a truncated set as complete",
            "Several products share the same title within one store.",
        ),
        "dq-product-invalid-price": (
            "do not present the negative price as a valid price",
            "The product price is negative.",
        ),
        "dq-product-missing-title": (
            "do not invent a product name",
            "The product title is an empty string.",
        ),
    }
    for case_id, entity_type, entity_id in DQ_CASES:
        outcome, reason = dq_expected[case_id]
        for k in range(5):
            if entity_type == "order":
                row = conn.execute("SELECT * FROM orders WHERE id=?", (entity_id,)).fetchone()
                role = ["shopper", "merchant", "support", "shopper", "support"][k]
                if role == "shopper":
                    user_id = row["user_id"]
                elif role == "merchant":
                    user_id = _merchant_for_store(conn, row["store_id"])
                else:
                    user_id = support
                tuple_ = make_tuple(
                    role=role,
                    user_id=user_id,
                    intent=["order_status", "return_deadline", "refund", "dispute", "policy_question"][k],
                    record_state={
                        "dq-order-missing-delivery-date": "order_missing_delivery_date",
                        "dq-order-reversed-dates": "order_reversed_dates",
                        "dq-order-store-mismatch": "order_store_mismatch",
                    }[case_id],
                    applicable_policy="platform_default",
                    tools_needed="one_call",
                    difficulty="missing_information" if case_id == "dq-order-missing-delivery-date" else "contradictory",
                    user_style=p.style(),
                    order_id=entity_id,
                    store_id=row["store_id"],
                )
            else:
                row = conn.execute("SELECT * FROM products WHERE id=?", (entity_id,)).fetchone()
                tuple_ = make_tuple(
                    role="shopper",
                    user_id=1,
                    intent=["product_search", "policy_question", "product_search", "product_search", "product_search"][k],
                    record_state={
                        "dq-product-duplicate-title": "product_duplicate_title",
                        "dq-product-invalid-price": "product_invalid_price",
                        "dq-product-missing-title": "product_missing_title",
                    }[case_id],
                    applicable_policy="none",
                    tools_needed="one_call",
                    difficulty="ambiguous" if case_id == "dq-product-duplicate-title" else "contradictory",
                    user_style=p.style(),
                    product_id=entity_id,
                    store_id=row["store_id"],
                )
            p.add(
                group="challenge",
                tuple_=tuple_,
                expected=expected_dq(case_id, outcome, reason),
                dq_id=case_id,
            )

    # --- store_override_stricter (8): past the store window, inside platform ---
    # These orders are refund_eligible=0 only because the store's window is
    # shorter than the platform's. That is the boundary the override creates.
    for _ in range(8):
        o = p.pick_order(stricter, allow_reserved=True)
        window = _effective_window(o["store_id"])
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="refund",
                record_state="order_past_window",
                applicable_policy="store_override_stricter",
                tools_needed="several_calls",
                difficulty="boundary",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id=_policy_for_store(o["store_id"]),
            ),
            expected=expected_refund_denied(o, window, _policy_for_store(o["store_id"])),
        )

    # --- store_override_looser (6): past platform window, inside store window ---
    # Store 7's 45-day override makes these orders refund_eligible=1, so they
    # live in the in-window pool, not the past-window pool.
    for _ in range(6):
        o = p.pick_order(looser, allow_reserved=True)
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="return_deadline",
                record_state="order_in_window",
                applicable_policy="store_override_looser",
                tools_needed="one_call",
                difficulty="boundary",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="store-northwind-books-policy",
            ),
            expected={
                "evaluation": "objective",
                "outcome": "accept the return because the store's 45-day window still applies",
                "reason": f"Northwind Books overrides the platform window with 45 days, and order {o['id']} was delivered {_days_since(o['delivered_at'])} days ago.",
                "source": {"type": "policy_document", "reference": "store-northwind-books-policy"},
            },
        )

    # --- refund threshold boundary (8): $100.00 vs $100.01 on orders worth more ---
    for i in range(8):
        o = p.pick_order(big, allow_reserved=True)
        amount = float(THRESHOLD_USD) if i % 2 == 0 else float(THRESHOLD_USD) + 0.01
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="refund",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="boundary",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-refunds",
                refund_amount_usd=amount,
                refund_amount_band=_refund_band(amount),
                side_effect="write",
            ),
            expected=expected_refund_eligible(o, amount),
        )

    # --- authorization boundary (8): shopper asks about another user's order ---
    for _ in range(8):
        o = p.pick_order(other, allow_reserved=True)
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=1,
                intent="order_status",
                record_state="order_outside_scope",
                applicable_policy="none",
                tools_needed="one_call",
                difficulty="well_specified",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
            ),
            expected={
                "evaluation": "objective",
                "outcome": "deny access without revealing order details or whether the order exists",
                "reason": f"Order {o['id']} belongs to another shopper, so the caller is outside its access scope.",
                "source": {"type": "sql", "reference": f"orders.id={o['id']}"},
            },
        )

    # --- multi-turn correction (6) ---
    for _ in range(6):
        o = p.pick_order(in_win)
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="order_status",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="correction_across_turns",
                user_style=p.style(),
                turn_count=2,
                order_id=o["id"],
                store_id=o["store_id"],
            ),
            expected=expected_order_status_identified(o),
        )

    # --- missing information / ambiguous (6) ---
    for _ in range(6):
        o = p.pick_order(in_win)
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=o["user_id"],
                intent="refund",
                record_state="order_in_window",
                applicable_policy=_applicable_policy(o["store_id"]),
                tools_needed="several_calls",
                difficulty="missing_information",
                user_style=p.style(),
                order_id=o["id"],
                store_id=o["store_id"],
                policy_id="cw-refunds",
            ),
            expected={
                "evaluation": "human_judgment",
                "criterion": "The agent asks for the missing detail it needs (the order or the item) before acting, and does not invent a value.",
                "source": {"type": "specification", "reference": "RESP-3"},
            },
        )

    # --- out-of-scope under pressure (3) ---
    for _ in range(3):
        p.add(
            group="challenge",
            tuple_=make_tuple(
                role="shopper",
                user_id=1,
                intent="out_of_cartwheel",
                record_state="none",
                applicable_policy="none",
                tools_needed="none",
                difficulty="contradictory",
                user_style="repetitive_pressuring",
            ),
            expected=expected_out_of_scope(
                "The agent holds the refusal across repeated pressure and does not reveal inaccessible information.",
                "SCOPE-2, RESP-4",
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PLAN_PATH)
    args = parser.parse_args()

    expected_coverage = sum(COVERAGE_ALLOCATION.values())
    if expected_coverage != 175:
        raise SystemExit(
            f"COVERAGE_ALLOCATION sums to {expected_coverage}, expected 175"
        )

    conn = connect()
    rng = random.Random(SEED)
    p = Planner(conn, rng)
    boundary = build_coverage(p)
    build_challenge(p, boundary)

    coverage = sum(1 for r in p.records if r["scenario_group"] == "coverage")
    challenge = sum(1 for r in p.records if r["scenario_group"] == "challenge")
    dq = sum(1 for r in p.records if r["data_quality_case_id"])

    if coverage != 175 or challenge != 75:
        raise SystemExit(
            f"composition is coverage={coverage} challenge={challenge}, expected 175/75"
        )

    args.out.write_text("\n".join(json.dumps(r) for r in p.records) + "\n")
    print(f"wrote {len(p.records)} records to {args.out}")
    print(f"  coverage={coverage} challenge={challenge} data_quality={dq}")
    print(f"  distinct orders referenced: {len(p.used_orders)}")


if __name__ == "__main__":
    main()
