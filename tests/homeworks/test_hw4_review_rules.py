"""Tests for the rules and policy numbers the review page keeps within reach.

analysis/review_app/rules.py reads each numbered rule of SPEC.md with its text,
and the policy numbers from facts.yaml, so the page never carries its own copy.
Each test writes a small spec or facts file to a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

from analysis.review_app.rules import load_rules


def _rules_from(spec_text: str, tmp_path: Path) -> list[dict[str, str]]:
    spec = tmp_path / "SPEC.md"
    spec.write_text(spec_text)
    facts = tmp_path / "facts.yaml"
    facts.write_text("platform_name: Cartwheel\n")
    return load_rules(spec_path=spec, facts_path=facts)["rules"]


def _policy_from(facts_text: str, tmp_path: Path) -> dict[str, str]:
    spec = tmp_path / "SPEC.md"
    spec.write_text("# Spec\n")
    facts = tmp_path / "facts.yaml"
    facts.write_text(facts_text)
    return {entry["label"]: entry["value"] for entry in load_rules(spec_path=spec, facts_path=facts)["policy"]}


def test_rules_are_read_with_their_ids_and_whole_text(tmp_path: Path) -> None:
    spec = (
        "## 5. Escalation policy\n\n"
        "**AUTH-1.** The harness enforces the matrix. The model never sees rows\n"
        "outside the caller's role.\n\n"
        "- **ESC-1.** Refunds above the threshold go to a human.\n"
        "- **ESC-3.** Disputes the agent cannot resolve from the help center and the\n"
        "  order record.\n"
    )

    assert _rules_from(spec, tmp_path) == [
        {"id": "AUTH-1", "text": "The harness enforces the matrix. The model never sees rows outside the caller's role."},
        {"id": "ESC-1", "text": "Refunds above the threshold go to a human."},
        {"id": "ESC-3", "text": "Disputes the agent cannot resolve from the help center and the order record."},
    ]


def test_a_rule_ending_with_a_colon_keeps_the_list_after_it(tmp_path: Path) -> None:
    spec = "**SCOPE-2.** The agent refuses:\n\n- Legal advice.\n- Payment-card changes.\n\n## Next\n"

    assert _rules_from(spec, tmp_path) == [
        {"id": "SCOPE-2", "text": "The agent refuses: Legal advice. Payment-card changes."}
    ]


def test_a_table_after_a_rule_is_not_part_of_it(tmp_path: Path) -> None:
    spec = "**AUTH-1.** Authorization is not a prompt.\n\n| Capability | Shopper |\n| --- | --- |\n"

    assert _rules_from(spec, tmp_path) == [{"id": "AUTH-1", "text": "Authorization is not a prompt."}]


def test_policy_numbers_come_from_the_facts_file(tmp_path: Path) -> None:
    facts = (
        "refund_auto_approve_threshold_usd: 250\n"
        "return_window_days: 14\n"
        "refund_processing_days_min: 3\n"
        "refund_processing_days_max: 7\n"
    )

    policy = _policy_from(facts, tmp_path)

    assert policy["Automatic refund limit"] == "$250"
    assert policy["Return window"] == "14 days from delivery"
    assert policy["Refund processing"] == "3–7 days"


def test_policy_numbers_missing_from_the_facts_file_are_left_out(tmp_path: Path) -> None:
    assert _policy_from("refund_auto_approve_threshold_usd: 100\n", tmp_path) == {
        "Automatic refund limit": "$100"
    }
