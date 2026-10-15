"""Tests for what the review page shows of a conversation.

analysis/review_app/view.py turns the grouped traces into what the Read view
draws: who is asking, and for each turn the customer message, the agent's
steps (its reason, the tool call, the answer) and the reply. Everything runs
offline on hand-written traces.
"""

from __future__ import annotations

import json

from analysis.helpers.normalization import group_by_session, normalize_trace
from analysis.review_app.view import conversation_views
from tests.homeworks.hw4_observations import ToolStep, conversation_trace

SHOPPER_PROMPT = (
    "You are Cartwheel's support assistant.\n\n"
    "## Session context (injected by the server; never taken from chat)\n"
    "- User role: shopper\n- User id: 155\n- Store id: none\n"
)

ORDER_LOOKUP: ToolStep = (
    "I will look up order 12.",
    "get_order",
    {"order_id": 12},
    {"ok": True, "order": {"order_id": 12, "status": "shipped"}},
)


def _view(*traces: dict[str, object]) -> dict[str, object]:
    sessions = group_by_session([normalize_trace(trace) for trace in traces])
    (conversation,) = conversation_views(sessions)
    return conversation


def _turn(conversation: dict[str, object], number: int = 0) -> dict[str, object]:
    turns = conversation["turns"]
    assert isinstance(turns, list)
    return turns[number]


def _only_step(answer: object, tool: str = "get_order") -> dict[str, object]:
    step: ToolStep = ("I will check.", tool, {"order_id": 12}, answer)
    steps = _turn(_view(conversation_trace(steps=(step,))))["steps"]
    assert isinstance(steps, list)
    return steps[0]


def test_who_is_asking_comes_from_the_session_context_of_the_prompt() -> None:
    conversation = _view(conversation_trace(steps=(ORDER_LOOKUP,)))

    assert (conversation["role"], conversation["user_id"], conversation["store_id"]) == (
        "merchant",
        "9001",
        "16",
    )
    assert (conversation["scenario_id"], conversation["prompt_version"]) == ("support-0001", "abc123")


def test_a_caller_without_a_store_has_no_store_id() -> None:
    conversation = _view(conversation_trace(system_prompt=SHOPPER_PROMPT))

    assert (conversation["role"], conversation["user_id"], conversation["store_id"]) == (
        "shopper",
        "155",
        None,
    )


def test_a_turn_holds_the_customer_message_the_steps_and_the_reply() -> None:
    turn = _turn(_view(conversation_trace(steps=(ORDER_LOOKUP,))))

    assert turn["customer"] == "Where is order 12?"
    assert [(step["reason"], step["tool"], step["arguments"], step["ok"]) for step in turn["steps"]] == [
        ("I will look up order 12.", "get_order", {"order_id": 12}, True)
    ]
    assert turn["reply"] == "Order 12 has shipped."


def test_the_system_prompt_stays_with_its_turn() -> None:
    turn = _turn(_view(conversation_trace(system_prompt=SHOPPER_PROMPT)))

    assert turn["system_prompt"] == SHOPPER_PROMPT


def test_a_turn_with_no_recorded_reply_has_none() -> None:
    turn = _turn(_view(conversation_trace(steps=(ORDER_LOOKUP,), reply=None)))

    assert turn["reply"] is None


def test_a_failed_step_carries_its_error_code_and_reason() -> None:
    step = _only_step({"ok": False, "error": "not_found", "reason": "no store named '18'"})

    assert (step["ok"], step["error"], step["error_reason"]) == (False, "not_found", "no store named '18'")


def test_a_list_answer_is_summed_up_by_count_and_stores() -> None:
    many_stores = _only_step({"ok": True, "orders": [{"store_id": 18}, {"store_id": 6}]})
    one_store = _only_step({"ok": True, "products": [{"store_id": 18}, {"store_id": 18}]})

    assert many_stores["summary"] == "2 orders across 2 stores"
    assert one_store["summary"] == "2 products, all from store 18"


def test_a_status_answer_is_summed_up_by_its_status_first() -> None:
    step = _only_step({"ok": True, "order_id": 2053, "status": "cancelled"}, tool="cancel_order")

    assert step["summary"] == "cancelled · order_id 2053"


def test_a_long_answer_is_folded_and_a_short_one_is_not() -> None:
    long_answer = {"ok": True, "orders": [{"order_id": n, "store_id": 1} for n in range(40)]}
    short_answer = {"ok": True, "order": {"order_id": 12, "status": "shipped"}}

    assert _only_step(long_answer)["folded"] is True
    assert _only_step(short_answer)["folded"] is False
    assert _only_step(long_answer)["result_chars"] == len(json.dumps(long_answer))


def test_a_step_that_changes_data_is_never_folded() -> None:
    long_refund = {"ok": True, "status": "queued_for_approval", "note": "x" * 600}

    step = _only_step(long_refund, tool="issue_refund")

    assert (step["changes_data"], step["folded"]) == (True, False)


def test_the_conversation_lists_its_tools_and_data_changing_actions() -> None:
    steps: tuple[ToolStep, ...] = (
        ORDER_LOOKUP,
        ("I will refund it.", "issue_refund", {"order_id": 12}, {"ok": True, "status": "auto_approved"}),
        ("I will hand it off.", "escalate_to_human", {"summary": "s"}, {"ok": True, "ticket_id": 1}),
    )

    conversation = _view(conversation_trace(steps=steps))

    assert conversation["tools"] == ["get_order", "issue_refund", "escalate_to_human"]
    assert conversation["actions"] == ["refund", "hand-off"]
