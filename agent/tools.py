"""Homework 1: the remaining commerce-agent tools.

The three lecture tools (`search_help_center`, `get_order`, `issue_refund`)
are implemented in agent/agent.py and are worked examples of the pattern:
check permissions first, go through agent/db.py for data, and return a
structured dict, never a prose error. The homework tools follow the same
pattern. agent/agent.py already wraps each function below as an SDK tool, so
once a function works here it works in chat with no further wiring.

Result convention (see agent/auth.py):
  - Success: a dict with "ok": True plus the payload fields named in each
    docstring.
  - Failure: {"ok": False, "error": <code>, "reason": <human-readable str>}.

Run the contract tests with: uv run pytest tests/test_hw_holes.py -k hw1
They are marked xfail and flip to passing as you implement each function.

Layout: each public tool is a plain list of named private steps and holds no
logic of its own. A step that hits a contract failure raises `_ToolFailure`,
and the `_structured_result` decorator turns it into the failure dict above.
Unexpected exceptions propagate unchanged, as SPEC.md section 4 requires.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable
from difflib import SequenceMatcher
from functools import wraps

from agent import db
from agent.auth import AuthContext, can_cancel_order, permission_denied
from agent.helpcenter import PolicyDoc, load_policy_docs
from agent.killswitch import kill_switch

MAX_SEARCH_LIMIT = 25
DEFAULT_ORDER_LIMIT = 20
FIND_ORDER_LIMIT = 5
# Minimum difflib ratio for a query word to count as matching a title word.
# 0.8 accepts plurals and one-letter slips ("speakers", "vasse") and rejects
# different words that merely look alike ("vase" vs "base" scores 0.75).
FUZZY_MATCH_THRESHOLD = 0.8

# What every tool returns: {"ok": True, ...payload} or {"ok": False, "error", "reason"}.
ToolResult = dict[str, object]

_ALL_ROWS = -1  # SQLite treats a negative LIMIT as "no upper bound".
_WORD_RE = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Structured failures
# ---------------------------------------------------------------------------


class _ToolFailure(Exception):
    """Raised by a private step to stop the tool with a structured failure."""

    def __init__(self, result: ToolResult) -> None:
        super().__init__(result["reason"])
        self.result = result


def _failure(error: str, reason: str) -> _ToolFailure:
    """Build the failure for an expected error code, ready to raise."""
    return _ToolFailure({"ok": False, "error": error, "reason": reason})


def _structured_result[**P](tool: Callable[P, ToolResult]) -> Callable[P, ToolResult]:
    """Return a `_ToolFailure` raised inside `tool` as the tool's result dict.

    The private steps raise `_ToolFailure` when they hit an expected error
    (an unknown order, a permission denial, ...). Decorating a public tool
    with `@_structured_result` is the same as wrapping its whole body in

        ```
        try:
            ...the steps...
        except _ToolFailure as failure:
            return failure.result
        ```

    so the public body stays a plain list of steps. Example:

        ```
        @_structured_result
        def get_policy(ctx, policy_id):
            doc = _policy_doc(policy_id)  # raises _ToolFailure when unknown
            return _policy_payload(doc)

        get_policy(ctx, "cw-returns")  # {"ok": True, "policy_id": "cw-returns", ...}
        get_policy(ctx, "cw-nope")     # {"ok": False, "error": "not_found", ...}
        ```

    Other exceptions propagate unchanged, as SPEC.md section 4 requires.

    How it works: `@_structured_result` above `def get_policy` means
    `get_policy = _structured_result(get_policy)`. The `run` function built
    below takes the name `get_policy` and calls the original inside the
    try/except. `@wraps(tool)` copies the original name and docstring onto
    `run`, and `[**P]` tells type checkers that `run` accepts exactly the
    original's arguments.
    """

    @wraps(tool)
    def run(*args: P.args, **kwargs: P.kwargs) -> ToolResult:
        try:
            return tool(*args, **kwargs)
        except _ToolFailure as failure:
            return failure.result

    return run


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


@_structured_result
def get_policy(ctx: AuthContext, policy_id: str) -> ToolResult:
    """Fetch one policy doc by its exact id. Risk tier: read.

    Every role may read every policy doc (the corpus is public help-center
    content), so this tool needs no permission check.

    Args:
        ctx: The caller's auth context. Unused here, but every tool takes it.
        policy_id: An exact policy id, e.g. "cw-returns" or
            "store-juniper-home-goods-policy". Matching is exact and
            case-sensitive; ids are the `policy_id` front-matter field of the
            files in data/policies/.

    Returns:
        On success: {"ok": True, "policy_id": str, "title": str,
        "audience": str, "body": str} where body is the markdown body of the
        doc without the front matter.
        If no doc has that id: {"ok": False, "error": "not_found",
        "reason": ...} naming the id that was requested.

    Implementation notes:
        agent.helpcenter.load_policy_docs() returns every parsed doc.
    """
    doc = _policy_doc(policy_id)
    return _policy_payload(doc)


@_structured_result
def search_products(
    ctx: AuthContext,
    query: str,
    store: str | None = None,
    max_price_usd: float | None = None,
    limit: int = 5,
) -> ToolResult:
    """Search the product catalog. Risk tier: read.

    Every role may search products. Matching is deterministic keyword
    matching, not semantic search: a product matches when every whitespace
    token of `query` appears case-insensitively as a substring of the
    product's title or description.

    Args:
        ctx: The caller's auth context.
        query: Free-text query. Must be non-empty after stripping whitespace;
            otherwise return {"ok": False, "error": "invalid_argument",
            "reason": ...}.
        store: Optional store filter. Matched with
            agent.db.get_store_by_name (case-insensitive name or slug). If
            given and no store matches, return {"ok": False, "error":
            "not_found", "reason": ...} naming the store string.
        max_price_usd: Optional inclusive price ceiling. If given and not
            strictly positive, return an "invalid_argument" error.
        limit: Maximum products to return. Clamp to the range
            [1, MAX_SEARCH_LIMIT]; do not error on out-of-range values.

    Returns:
        {"ok": True, "products": [...], "count": <len(products)>} where each
        product is {"product_id": int, "store_id": int, "title": str,
        "price_usd": float}. Sort matches by price_usd ascending, then by
        product_id ascending, and truncate to `limit`. No matches is still a
        success: {"ok": True, "products": [], "count": 0}.

    Implementation notes:
        agent.db.list_products(conn, store_id) gives the candidate set.
        Use `with db.connection() as conn:` to close the database automatically.
    """
    tokens = _query_tokens(query)
    _ensure_positive_price_ceiling(max_price_usd)
    store_id = _store_id_for(store)
    products = _products_mentioning(tokens, store_id, max_price_usd)
    products = _cheapest_first(products, _clamped_limit(limit))
    return _products_payload(products)


@_structured_result
def list_my_orders(ctx: AuthContext) -> ToolResult:
    """List recent orders in the caller's own scope. Risk tier: read.

    Role behavior, straight from the access matrix in SPEC.md:
        - shopper: the caller's own orders.
        - merchant: the caller's store's orders (ctx.store_id).
        - support: support staff have no orders of their own and look up
          specific orders with get_order instead, so return {"ok": False,
          "error": "invalid_argument", "reason": ...} saying exactly that.

    Returns:
        For shopper and merchant: {"ok": True, "orders": [...],
        "count": <len(orders)>} where each order is
        agent.db.Order.to_public_dict() and the list holds at most
        DEFAULT_ORDER_LIMIT orders, newest first (agent.db.list_orders_for_user
        and list_orders_for_store already sort and limit this way).

    Implementation notes:
        No permission check is needed beyond the role dispatch, because the
        scope is baked into which query you run. That is the point of the
        tool: the model cannot ask for someone else's orders through it.
    """
    orders = _own_orders(ctx)
    return _counted_orders_payload(orders)


@_structured_result
def cancel_order(ctx: AuthContext, order_id: int, reason: str) -> ToolResult:
    """Cancel an order. Risk tier: write.

    This is the homework's write tool, and it must enforce two independent
    rules in this order:

    1. The access matrix (scope): use agent.auth.can_cancel_order. Shoppers
       may cancel only their own orders, merchants only their own store's
       orders, support any order. On failure return
       agent.auth.permission_denied(...) with a reason naming the role and
       the order id. Scope is checked before the status rule so that an
       out-of-scope caller learns nothing about the order's state.
    2. The pre-shipment rule (facts.yaml `cancel_cutoff`): only orders whose
       status is exactly "placed" can be cancelled, for every role. If the
       order is in scope but its status is not "placed", return
       {"ok": False, "error": "not_eligible", "reason": ...} that names the
       current status and states that orders can be cancelled only before
       shipment.

    Args:
        ctx: The caller's auth context.
        order_id: The order to cancel.
        reason: Free-text reason from the user; not validated.

    Returns:
        If no order has this id: {"ok": False, "error": "not_found",
        "reason": ...}.
        On success: {"ok": True, "order_id": order_id, "status": "cancelled"}
        after persisting the new status with agent.db.set_order_status.

    Implementation notes:
        Fetch with agent.db.get_order. Note the argument order of
        can_cancel_order(ctx, order_user_id, order_store_id).

    The Module 4 kill switch is checked first (before the scope and
    status rules and before your code), so that a paused write tool touches
    nothing. It is provided; the default ("off") returns None and falls
    through to your implementation.
    """
    # `reason` is neither validated nor stored: there is no cancellation record.
    _ensure_not_paused("cancel_order")
    order = _existing_order(order_id)
    _ensure_may_cancel(ctx, order)
    _ensure_before_shipment(order)
    _persist_cancellation(order.id)
    return _cancellation_payload(order.id)


@_structured_result
def find_order(ctx: AuthContext, query: str) -> ToolResult:
    """Search the caller's orders by product name. Risk tier: read.

    Takes a natural-language query (e.g., "earmuffs I bought last week")
    and searches the authenticated user's orders for products whose name
    matches. Use fuzzy string matching (e.g., thefuzz.fuzz.partial_ratio
    or case-insensitive substring matching) to find orders whose product name is close to the
    query.

    Access rules: a shopper searches only the shopper's own orders, a
    merchant searches orders from the merchant's store, and support staff
    can search any orders. Use agent.db.list_order_search_candidates with
    user_id=ctx.user_id for shoppers, store_id=ctx.store_id for merchants,
    or all_orders=True only for support. Derive the scope from ctx, never
    from the query; reject unsupported roles or missing required identity.
    Use agent.db.list_products to map product IDs to product titles.

    The helper returns the complete authorised scope, newest first with
    order ID descending as the tie-breaker. Match product names first,
    preserve that order, then return at most five matches. Do not search
    only the 20 most recent orders. Convert matches with to_public_dict().

    Args:
        ctx: The caller's auth context.
        query: A natural-language description of the product.

    Returns:
        {"ok": True, "orders": [...]} with a list of matching orders
        (at most 5), each as the dict returned by agent.db. If no orders
        match, return {"ok": True, "orders": []}.
    """
    scores = _product_scores(query)
    orders = _orders_in_scope(ctx, scores)
    orders = _best_matches(orders, scores)
    return _orders_payload(orders)


# ---------------------------------------------------------------------------
# get_policy steps
# ---------------------------------------------------------------------------


def _policy_doc(policy_id: str) -> PolicyDoc:
    """The doc whose id matches exactly, or a not_found failure naming the id."""
    for doc in load_policy_docs():
        if doc.policy_id == policy_id:
            return doc
    raise _failure("not_found", f"no policy doc with id {policy_id!r}")


def _policy_payload(doc: PolicyDoc) -> ToolResult:
    return {
        "ok": True,
        "policy_id": doc.policy_id,
        "title": doc.title,
        "audience": doc.audience,
        "body": doc.body,
    }


# ---------------------------------------------------------------------------
# search_products steps
# ---------------------------------------------------------------------------


def _query_tokens(query: str) -> list[str]:
    """Lowercased whitespace tokens, or an invalid_argument failure if empty."""
    tokens = query.lower().split()
    if not tokens:
        raise _failure("invalid_argument", "query must not be empty")
    return tokens


def _ensure_positive_price_ceiling(max_price_usd: float | None) -> None:
    if max_price_usd is not None and max_price_usd <= 0:
        raise _failure(
            "invalid_argument",
            f"max_price_usd must be positive, got {max_price_usd}",
        )


def _store_id_for(store: str | None) -> int | None:
    """Resolve a store name or slug; a blank filter means every store."""
    if store is None or not store.strip():
        return None
    with db.connection() as conn:
        match = db.get_store_by_name(conn, store.strip())
    if match is None:
        raise _failure("not_found", f"no store named {store!r}")
    return match.id


def _products_mentioning(
    tokens: list[str], store_id: int | None, max_price_usd: float | None
) -> list[db.Product]:
    with db.connection() as conn:
        candidates = db.list_products(conn, store_id)
    return [
        product
        for product in candidates
        if _mentions_every(product, tokens) and _within_ceiling(product, max_price_usd)
    ]


def _mentions_every(product: db.Product, tokens: list[str]) -> bool:
    title = product.title.lower()
    description = product.description.lower()
    return all(token in title or token in description for token in tokens)


def _within_ceiling(product: db.Product, max_price_usd: float | None) -> bool:
    return max_price_usd is None or product.price_usd <= max_price_usd


def _clamped_limit(limit: int) -> int:
    return max(1, min(limit, MAX_SEARCH_LIMIT))


def _cheapest_first(products: list[db.Product], limit: int) -> list[db.Product]:
    return sorted(products, key=lambda product: (product.price_usd, product.id))[:limit]


def _products_payload(products: list[db.Product]) -> ToolResult:
    listed = [
        {
            "product_id": product.id,
            "store_id": product.store_id,
            "title": product.title,
            "price_usd": product.price_usd,
        }
        for product in products
    ]
    return {"ok": True, "products": listed, "count": len(listed)}


# ---------------------------------------------------------------------------
# list_my_orders steps
# ---------------------------------------------------------------------------


def _own_orders(ctx: AuthContext) -> list[db.Order]:
    """The newest orders in the caller's own scope; support has none."""
    if ctx.role == "support":
        raise _failure(
            "invalid_argument",
            "support staff have no orders of their own; "
            "look up a specific order with get_order",
        )
    with db.connection() as conn:
        return _scoped_orders(conn, ctx, limit=DEFAULT_ORDER_LIMIT)


def _scoped_orders(
    conn: sqlite3.Connection, ctx: AuthContext, limit: int
) -> list[db.Order]:
    """The caller's row of the access matrix. Callers rule out support first."""
    if ctx.role == "merchant":
        return db.list_orders_for_store(conn, ctx.store_id, limit=limit)
    return db.list_orders_for_user(conn, ctx.user_id, limit=limit)


def _public_orders(orders: Iterable[db.Order]) -> list[dict[str, object]]:
    return [order.to_public_dict() for order in orders]


def _counted_orders_payload(orders: list[db.Order]) -> ToolResult:
    listed = _public_orders(orders)
    return {"ok": True, "orders": listed, "count": len(listed)}


# ---------------------------------------------------------------------------
# cancel_order steps
# ---------------------------------------------------------------------------


def _ensure_not_paused(tool_name: str) -> None:
    """The Module 4 kill switch, checked before any other work."""
    paused = kill_switch(tool_name)
    if paused is not None:
        raise _failure("paused", paused)


def _existing_order(order_id: int) -> db.Order:
    with db.connection() as conn:
        order = db.get_order(conn, order_id)
    if order is None:
        raise _failure("not_found", f"no order #{order_id}")
    return order


def _ensure_may_cancel(ctx: AuthContext, order: db.Order) -> None:
    """The access matrix, checked before anything about the order is revealed."""
    if not can_cancel_order(ctx, order.user_id, order.store_id):
        raise _ToolFailure(
            permission_denied(
                f"role '{ctx.role}' (user {ctx.user_id}) may not cancel order #{order.id}"
            )
        )


def _ensure_before_shipment(order: db.Order) -> None:
    """facts.yaml `cancel_cutoff`: only a 'placed' order can be cancelled."""
    if order.status != "placed":
        raise _failure(
            "not_eligible",
            f"order #{order.id} has status '{order.status}'; "
            "orders can be cancelled only before shipment",
        )


def _persist_cancellation(order_id: int) -> None:
    with db.connection() as conn:
        db.set_order_status(conn, order_id, "cancelled")


def _cancellation_payload(order_id: int) -> ToolResult:
    return {"ok": True, "order_id": order_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# find_order steps
# ---------------------------------------------------------------------------


def _product_scores(query: str) -> dict[int, float]:
    """Fuzzy match score of every product title against the query.

    Products whose title matches no query word are left out, so the keys are
    exactly the products worth looking for in the caller's orders.
    """
    query_words = _words(query)
    with db.connection() as conn:
        products = db.list_products(conn)
    title_scores = {
        title: _title_score(query_words, _words(title))
        for title in {product.title for product in products}
    }
    return {
        product.id: title_scores[product.title]
        for product in products
        if title_scores[product.title] > 0
    }


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _title_score(query_words: list[str], title_words: list[str]) -> float:
    """Sum of each query word's best similarity to a title word, above the threshold.

    Summing rewards titles that match several query words ("heavy duty vase")
    over titles that match one, while filler words in a natural-language
    query ("I bought last week") score nothing.
    """
    best_scores = (
        max(
            (_similarity(query_word, title_word) for title_word in title_words),
            default=0.0,
        )
        for query_word in query_words
    )
    return sum(score for score in best_scores if score >= FUZZY_MATCH_THRESHOLD)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _orders_in_scope(ctx: AuthContext, product_ids: Iterable[int]) -> list[db.Order]:
    """Every order the caller may search, newest first."""
    with db.connection() as conn:
        if ctx.role == "support":
            return _orders_for_products(conn, product_ids)
        return _scoped_orders(conn, ctx, limit=_ALL_ROWS)


def _orders_for_products(
    conn: sqlite3.Connection, product_ids: Iterable[int]
) -> list[db.Order]:
    """Every order for the given products, across all users, newest first.

    Support staff search all orders, and agent/db.py lists orders only per
    user or per store, so this is the one query the tools run themselves.
    Rows go through agent.db's own row parser to keep a single Order shape.
    """
    ids = tuple(product_ids)
    if not ids:
        return []
    placeholders = ", ".join("?" * len(ids))
    rows = conn.execute(
        "SELECT * FROM orders "
        f"WHERE product_id IN ({placeholders}) "
        "ORDER BY ordered_at DESC, id DESC",
        ids,
    ).fetchall()
    return [db._order_from_row(row) for row in rows]


def _best_matches(orders: list[db.Order], scores: dict[int, float]) -> list[db.Order]:
    """The top matches: best score first, then newest, capped at FIND_ORDER_LIMIT."""
    matched = [order for order in orders if order.product_id in scores]
    ranked = sorted(
        matched,
        key=lambda order: (scores[order.product_id], order.ordered_at, order.id),
        reverse=True,
    )
    return ranked[:FIND_ORDER_LIMIT]


def _orders_payload(orders: list[db.Order]) -> ToolResult:
    return {"ok": True, "orders": _public_orders(orders)}
