"""The rules and policy numbers the review page keeps within reach.

Rules are the numbered requirements of SPEC.md (``**RESP-2.** ...``) with their
whole text; policy numbers come from facts.yaml. Both are read from the files
on every request, so the page never carries a copy that can drift.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = _REPO_ROOT / "SPEC.md"
FACTS_PATH = _REPO_ROOT / "facts.yaml"

_RULE_START = re.compile(r"^\s*(?:- )?\*\*([A-Z]+-\d+)\.\*\*\s*(.*)$")

type Facts = dict[str, object]

# What the page shows of facts.yaml: a label, the keys it needs, how it reads.
_POLICY: tuple[tuple[str, tuple[str, ...], Callable[[Facts], str]], ...] = (
    (
        "Automatic refund limit",
        ("refund_auto_approve_threshold_usd",),
        lambda facts: f"${facts['refund_auto_approve_threshold_usd']}",
    ),
    (
        "Return window",
        ("return_window_days",),
        lambda facts: f"{facts['return_window_days']} days from delivery",
    ),
    (
        "Refund processing",
        ("refund_processing_days_min", "refund_processing_days_max"),
        lambda facts: (
            f"{facts['refund_processing_days_min']}–{facts['refund_processing_days_max']} days"
        ),
    ),
    ("Cancellation", ("cancel_cutoff",), lambda facts: str(facts["cancel_cutoff"]).replace("_", " ")),
    ("Dispute window", ("dispute_window_days",), lambda facts: f"{facts['dispute_window_days']} days"),
    (
        "Human follow-up",
        ("support_escalation_sla_hours",),
        lambda facts: f"within {facts['support_escalation_sla_hours']} hours",
    ),
    (
        "Restocking fee",
        ("restocking_fee_max_percent",),
        lambda facts: f"up to {facts['restocking_fee_max_percent']}%",
    ),
)


class Rule(TypedDict):
    id: str
    text: str


class PolicyNumber(TypedDict):
    label: str
    value: str


class RulesPanel(TypedDict):
    rules: list[Rule]
    policy: list[PolicyNumber]


def load_rules(spec_path: Path = SPEC_PATH, facts_path: Path = FACTS_PATH) -> RulesPanel:
    """Return the numbered rules of the spec and the policy numbers of the facts file."""
    rules = _spec_rules(spec_path.read_text(encoding="utf-8").splitlines())
    policy = _policy_numbers(_facts(facts_path))
    return {"rules": rules, "policy": policy}


# -- spec rules ---------------------------------------------------------------


def _spec_rules(lines: list[str]) -> list[Rule]:
    rules: list[Rule] = []
    position = 0
    while position < len(lines):
        start = _RULE_START.match(lines[position])
        if start is None:
            position += 1
            continue
        text, position = _rule_text(start.group(2), lines, position + 1)
        rules.append({"id": start.group(1), "text": text})
    return rules


def _rule_text(first_line: str, lines: list[str], position: int) -> tuple[str, int]:
    """Join a rule's lines; a rule ending with a colon also takes the list below it."""
    parts = [first_line.strip()]
    position = _take_continuation(parts, lines, position)
    if parts[-1].endswith(":"):
        position = _take_list(parts, lines, position)
    return " ".join(part for part in parts if part), position


def _is_boundary(line: str) -> bool:
    stripped = line.strip()
    return not stripped or bool(_RULE_START.match(line)) or stripped.startswith(("#", "|", "- "))


def _take_continuation(parts: list[str], lines: list[str], position: int) -> int:
    while position < len(lines) and not _is_boundary(lines[position]):
        parts.append(lines[position].strip())
        position += 1
    return position


def _is_list_item(line: str) -> bool:
    return line.strip().startswith("- ") and not _RULE_START.match(line)


def _take_list(parts: list[str], lines: list[str], position: int) -> int:
    while position < len(lines) and not lines[position].strip():
        position += 1
    while position < len(lines) and _is_list_item(lines[position]):
        parts.append(lines[position].strip()[2:].strip())
        position += 1
    return position


# -- policy numbers -----------------------------------------------------------


def _facts(facts_path: Path) -> Facts:
    loaded = yaml.safe_load(facts_path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _policy_numbers(facts: Facts) -> list[PolicyNumber]:
    return [
        {"label": label, "value": render(facts)}
        for label, keys, render in _POLICY
        if all(key in facts for key in keys)
    ]
