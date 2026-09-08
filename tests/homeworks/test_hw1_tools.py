"""Edge-case tests for the Homework 1 tools in agent/tools.py.

tests/test_hw_holes.py holds the instructor contract test for each tool.
These tests cover the rest of each docstring: argument validation, limit
clamping, role scoping, the kill switch, and fuzzy ranking. Everything runs
offline against the seeded temp world from tests/conftest.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent import db, tools
from agent.auth import AuthContext
from agent.helpcenter import load_policy_docs

SHOPPER_1 = AuthContext(user_id=1, role="shopper")
SHOPPER_2 = AuthContext(user_id=2, role="shopper")
SHOPPER_WITHOUT_ORDERS = AuthContext(user_id=999_999, role="shopper")
MERCHANT_STORE_1 = AuthContext(user_id=9001, role="merchant", store_id=1)
MERCHANT_STORE_2 = AuthContext(user_id=9002, role="merchant", store_id=2)
SUPPORT = AuthContext(user_id=9501, role="support")

# Pinned demo data from seed.generate (dev scale).
PLACED_ORDER_STORE_1 = 6213  # owned by shopper 368
PLACED_ORDER_STORE_16 = 10  # owned by shopper 403
SHIPPED_ORDER_STORE_1 = 830
DELIVERED_ORDER_SHOPPER_1 = 4127
HEAVY_DUTY_VASE_ORDERS_NEWEST_FIRST = [4455, 4127, 3980]
MATTE_VASE_ORDER = 2485
BLUETOOTH_SPEAKER_ORDER = 301
OLDEST_ORDER_SHOPPER_1 = 7310  # "Signature Novel", beyond the 20 newest


def _status(db_path: Path, order_id: int) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT status FROM orders WHERE id = ?", (order_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _product_title(product_id: int) -> str:
    with db.connection() as conn:
        return next(p.title for p in db.list_products(conn) if p.id == product_id)


def _order_owner(order_id: int) -> int:
    with db.connection() as conn:
        return db.get_order(conn, order_id).user_id


# ---------------------------------------------------------------------------
# get_policy
# ---------------------------------------------------------------------------


def test_get_policy_returns_the_parsed_doc_fields(world: dict) -> None:
    doc = next(d for d in load_policy_docs() if d.policy_id == "cw-returns")

    result = tools.get_policy(SHOPPER_1, "cw-returns")

    assert result == {
        "ok": True,
        "policy_id": doc.policy_id,
        "title": doc.title,
        "audience": doc.audience,
        "body": doc.body,
    }


def test_get_policy_not_found_names_the_requested_id(world: dict) -> None:
    result = tools.get_policy(SUPPORT, "cw-does-not-exist")

    assert result["ok"] is False
    assert result["error"] == "not_found"
    assert "cw-does-not-exist" in result["reason"]


def test_get_policy_matching_is_case_sensitive(world: dict) -> None:
    assert tools.get_policy(SHOPPER_1, "CW-RETURNS")["error"] == "not_found"


# ---------------------------------------------------------------------------
# search_products
# ---------------------------------------------------------------------------


def test_search_products_rejects_whitespace_only_query(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "   \t ")

    assert result["ok"] is False
    assert result["error"] == "invalid_argument"


@pytest.mark.parametrize("ceiling", [0, -5.0])
def test_search_products_rejects_nonpositive_price_ceiling(
    world: dict, ceiling: float
) -> None:
    result = tools.search_products(SHOPPER_1, "vase", max_price_usd=ceiling)

    assert result["ok"] is False
    assert result["error"] == "invalid_argument"


def test_search_products_price_ceiling_is_inclusive(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "vase", max_price_usd=9.0, limit=25)

    prices = [p["price_usd"] for p in result["products"]]
    assert 9.0 in prices
    assert all(price <= 9.0 for price in prices)


def test_search_products_requires_every_token(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "heavy-duty VASE", limit=25)

    assert result["count"] >= 1
    for product in result["products"]:
        title = product["title"].lower()
        assert "heavy-duty" in title and "vase" in title


def test_search_products_matches_descriptions_too(world: dict) -> None:
    # Every seeded description contains the store name; no title does.
    result = tools.search_products(SHOPPER_1, "blue heron", limit=25)

    assert result["count"] >= 1
    assert all(p["store_id"] == 1 for p in result["products"])
    assert not any("blue heron" in p["title"].lower() for p in result["products"])


def test_search_products_clamps_limit_to_the_allowed_range(world: dict) -> None:
    # "placeholder" appears in every seeded description, so it matches all products.
    assert tools.search_products(SHOPPER_1, "placeholder", limit=0)["count"] == 1
    assert tools.search_products(SHOPPER_1, "placeholder", limit=-3)["count"] == 1
    assert tools.search_products(SHOPPER_1, "placeholder", limit=100)["count"] == 25


def test_search_products_sorts_by_price_then_product_id(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "placeholder", limit=25)

    keys = [(p["price_usd"], p["product_id"]) for p in result["products"]]
    assert keys == sorted(keys)


def test_search_products_accepts_a_store_slug(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "vase", store="blue-heron-ceramics")

    assert result["ok"] is True
    assert result["count"] >= 1
    assert all(p["store_id"] == 1 for p in result["products"])


def test_search_products_no_match_is_still_a_success(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "zzzznonexistent9999")

    assert result == {"ok": True, "products": [], "count": 0}


def test_search_products_product_shape(world: dict) -> None:
    result = tools.search_products(SHOPPER_1, "vase", limit=1)

    assert set(result["products"][0]) == {"product_id", "store_id", "title", "price_usd"}


# ---------------------------------------------------------------------------
# list_my_orders
# ---------------------------------------------------------------------------


def test_list_my_orders_caps_at_the_default_limit_newest_first(world: dict) -> None:
    result = tools.list_my_orders(SHOPPER_1)  # shopper 1 has more than 20 orders

    dates = [o["ordered_at"] for o in result["orders"]]
    assert result["count"] == tools.DEFAULT_ORDER_LIMIT
    assert dates == sorted(dates, reverse=True)


def test_list_my_orders_without_orders_is_an_empty_success(world: dict) -> None:
    assert tools.list_my_orders(SHOPPER_WITHOUT_ORDERS) == {
        "ok": True,
        "orders": [],
        "count": 0,
    }


def test_list_my_orders_points_support_to_get_order(world: dict) -> None:
    result = tools.list_my_orders(SUPPORT)

    assert result["error"] == "invalid_argument"
    assert "get_order" in result["reason"]


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


def test_cancel_order_scope_is_checked_before_status(world_copy: Path) -> None:
    # A delivered order outside the caller's scope reports the scope failure,
    # not the status failure, so the stranger learns nothing about it.
    result = tools.cancel_order(SHOPPER_2, DELIVERED_ORDER_SHOPPER_1, "not mine")

    assert result["error"] == "permission_denied"
    assert "delivered" not in result["reason"]


def test_cancel_order_merchant_is_limited_to_own_store(world_copy: Path) -> None:
    denied = tools.cancel_order(MERCHANT_STORE_2, PLACED_ORDER_STORE_1, "wrong store")
    assert denied["error"] == "permission_denied"
    assert _status(world_copy, PLACED_ORDER_STORE_1) == "placed"

    allowed = tools.cancel_order(MERCHANT_STORE_1, PLACED_ORDER_STORE_1, "out of stock")
    assert allowed == {"ok": True, "order_id": PLACED_ORDER_STORE_1, "status": "cancelled"}
    assert _status(world_copy, PLACED_ORDER_STORE_1) == "cancelled"


def test_cancel_order_support_may_cancel_any_placed_order(world_copy: Path) -> None:
    result = tools.cancel_order(SUPPORT, PLACED_ORDER_STORE_16, "customer request")

    assert result == {"ok": True, "order_id": PLACED_ORDER_STORE_16, "status": "cancelled"}
    assert _status(world_copy, PLACED_ORDER_STORE_16) == "cancelled"


def test_cancel_order_not_eligible_names_the_current_status(world_copy: Path) -> None:
    result = tools.cancel_order(SUPPORT, SHIPPED_ORDER_STORE_1, "too late")

    assert result["ok"] is False
    assert result["error"] == "not_eligible"
    assert "shipped" in result["reason"]
    assert "before shipment" in result["reason"]
    assert _status(world_copy, SHIPPED_ORDER_STORE_1) == "shipped"


def test_cancel_order_kill_switch_pauses_before_any_work(
    world_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = AuthContext(user_id=_order_owner(PLACED_ORDER_STORE_1), role="shopper")
    monkeypatch.setenv("CARTWHEEL_KILL_SWITCH", "readonly")

    result = tools.cancel_order(owner, PLACED_ORDER_STORE_1, "changed my mind")

    assert result["ok"] is False
    assert result["error"] == "paused"
    assert _status(world_copy, PLACED_ORDER_STORE_1) == "placed"


def test_cancel_order_runs_when_only_refunds_are_paused(
    world_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = AuthContext(user_id=_order_owner(PLACED_ORDER_STORE_1), role="shopper")
    monkeypatch.setenv("CARTWHEEL_KILL_SWITCH", "refunds")

    result = tools.cancel_order(owner, PLACED_ORDER_STORE_1, "changed my mind")

    assert result["ok"] is True
    assert _status(world_copy, PLACED_ORDER_STORE_1) == "cancelled"


# ---------------------------------------------------------------------------
# find_order
# ---------------------------------------------------------------------------


def test_find_order_ranks_fuller_title_matches_first(world: dict) -> None:
    result = tools.find_order(SHOPPER_1, "heavy duty vases I bought last month")

    order_ids = [o["order_id"] for o in result["orders"]]
    assert len(order_ids) <= 5
    assert order_ids[:3] == HEAVY_DUTY_VASE_ORDERS_NEWEST_FIRST
    assert MATTE_VASE_ORDER in order_ids[3:]


def test_find_order_tolerates_plurals_and_small_typos(world: dict) -> None:
    plural = tools.find_order(SHOPPER_1, "bluetooth speakers")
    typo = tools.find_order(SHOPPER_1, "bluetooth speaekr")

    assert plural["orders"][0]["order_id"] == BLUETOOTH_SPEAKER_ORDER
    assert typo["orders"][0]["order_id"] == BLUETOOTH_SPEAKER_ORDER


def test_find_order_searches_beyond_the_twenty_newest_orders(world: dict) -> None:
    result = tools.find_order(SHOPPER_1, "signature novel")

    assert result["orders"][0]["order_id"] == OLDEST_ORDER_SHOPPER_1


def test_find_order_shopper_scope_excludes_other_shoppers(world: dict) -> None:
    result = tools.find_order(SHOPPER_2, "heavy-duty vase")

    assert all(_order_owner(o["order_id"]) == 2 for o in result["orders"])


def test_find_order_merchant_scope_is_the_store(world: dict) -> None:
    result = tools.find_order(MERCHANT_STORE_2, "vase")

    assert 1 <= len(result["orders"]) <= 5
    assert all(o["store_id"] == 2 for o in result["orders"])


def test_find_order_support_searches_every_order(world: dict) -> None:
    result = tools.find_order(SUPPORT, "heavy-duty vase")

    assert len(result["orders"]) == 5
    assert {o["store_id"] for o in result["orders"]} >= {1}
    assert all(_product_title(o["product_id"]) == "Heavy-Duty Vase" for o in result["orders"])


def test_find_order_returns_public_order_dicts(world: dict) -> None:
    result = tools.find_order(SHOPPER_1, "bluetooth speaker")

    with db.connection() as conn:
        expected = db.get_order(conn, BLUETOOTH_SPEAKER_ORDER).to_public_dict()
    assert result["orders"][0] == expected
