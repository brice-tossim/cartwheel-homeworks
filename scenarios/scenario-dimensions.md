# Cartwheel scenario dimensions (Homework 3, Part A)

The approved plan for the support-request dataset. Each scenario's `tuple` records one
value per dimension below. Sources: `SPEC.md`, `facts.yaml`, the seeded database, and
`scenarios/skill/SKILL.md`.

## Dimensions

| # | Dimension (`tuple` field) | Values | Why (one line) |
| --- | --- | --- | --- |
| 1 | `role` | `shopper`, `merchant`, `support` | AUTH-1 gives each role a different permission set, so the same request can be allowed or denied. |
| 2 | `intent` | `order_status`, `return_deadline`, `refund`, `cancellation`, `product_search`, `policy_question`, `dispute`, `account_change`, `payment_card_change`, `legal_advice`, `out_of_cartwheel` | Each intent exercises a different tool path; the three refusal intents exist because SCOPE-2 names them separately, and `payment_card_change` sits beside `account_change` (refuse one, escalate the other under ESC-2). |
| 3 | `record_state` | `order_in_window`, `order_past_window`, `order_past_dispute_window`, `order_window_last_day`, `order_window_day_after`, `order_placed`, `order_shipped`, `order_refunded`, `order_cancelled`, `order_outside_scope`, `order_not_found`, `order_missing_delivery_date`, `order_reversed_dates`, `order_store_mismatch`, `product_normal`, `product_no_match`, `product_duplicate_title`, `product_invalid_price`, `product_missing_title`, `policy_page`, `none` | The record's state determines eligibility, the expected outcome, and the extra metadata. |
| 4 | `applicable_policy` | `platform_default`, `store_override_stricter`, `store_override_looser`, `restocking_fee`, `none` | A store override takes precedence over the platform default, so the same order can be in or out of window. |
| 5 | `tools_needed` | `none`, `one_call`, `several_calls` | The number of tool calls changes the execution path; whether a write should happen is recorded separately. |
| 6 | `difficulty` | `well_specified`, `ambiguous`, `missing_information`, `boundary`, `contradictory`, `correction_across_turns` | Difficulty decides whether the agent must ask, refuse, escalate, or handle a boundary exactly. |
| 7 | `user_style` | `neutral_conversational`, `terse_fragmentary`, `typo_heavy`, `confused_rambling`, `frustrated_impatient`, `repetitive_pressuring`, `operational_shorthand`, `requests_short_plain_answer` | RESP-5 requires a direct and respectful answer regardless of how the user writes. |
| 8 | `refund_amount_band` | `below_threshold`, `at_threshold`, `above_threshold`, `null` | The band changes the expected outcome (automatic approval versus a queued refund), so it varies the scenario. |

## Grounding fields

Set each field when it applies to the scenario, otherwise `null`. Never invent a value to
fill a field. The validator itself requires only the eight tuple fields, plus `order_id`
or `product_id` on damaged-record scenarios under `--final`.

| # | Field | Values | Why (one line) |
| --- | --- | --- | --- |
| 9 | `order_id` / `product_id` / `store_id` / `user_id` | real ids from `cartwheel.db`, chosen from the record's owner or store (see the access rule below) | Grounds the scenario in a real row so the expected result is checkable and the runner can authenticate. |
| 10 | `policy_id` | a policy document identifier, e.g. `cw-returns`, `cw-refunds`, `cw-shipping`, `cw-payouts`, `cw-restocking-fees`, `cw-disputes`, `cw-cancellations`, `cw-account-security`, `cw-escalations`, `cw-roles`, `cw-store-overrides`, `cw-getting-help`, or a `store-*-policy` document | Names the document the agent must cite for a policy claim (RESP-1). |
| 11 | `refund_amount_usd` | a dollar amount, at most the order total; set only for refund scenarios | The $100 threshold applies to the requested refund amount, not the order total. |
| 12 | `item_condition` | `opened`, `unopened`, `null` | A restocking fee applies only to opened items, so the expected result depends on this when a fee is charged. |
| 13 | `side_effect` | `read_only`, `write` | Separates whether a write should happen from how many calls it takes; a past-window refund must stay `read_only`. |
| 14 | `scenario_group` | `coverage`, `challenge` | Keeps the ordinary and intentionally difficult pools separate so the enriched failure rate is not mistaken for production. |
| 15 | `turn_count` | integer 1–25 | Derived as `1 + len(followups)`; the validator rejects any mismatch, and `correction_across_turns` requires at least 2. |

## Access rule for `user_id`

Every scenario sets `user_id` from the record's owner or store. The runner's defaults
(shopper `1`, merchant `9001`, support `9501`) are only fallbacks and cannot serve most
values.

| Record | Authorized users |
| --- | --- |
| Order `8001` (damaged) | shopper `174`, merchant `9016` (store 16), support `9501` |
| Order `8002` (damaged) | shopper `392`, merchant `9020` (store 20), support `9501` |
| Order `8003` (damaged) | shopper `119`, merchant `9001` (store 1), support `9501` |
| Store-window scenarios | the order's own shopper, its store's merchant (`9002` Juniper 14d, `9007` Northwind 45d, `9010` Meridian 21d, `9013` Saltbox 7d), or support `9501` |
| Restocking-fee scenarios | the order's own shopper, its store's merchant (`9005` Cascade Audio, `9015` Second Stitch), or support `9501` |
| Any order | support `9501` |
| No order (`none`, `policy_page`, product values) | any user of the scenario's role |

**Exceptions to the owner-or-store rule:**

- `order_outside_scope` must use an authenticated user who is deliberately outside the
  order's access scope: another shopper, or another store's merchant. Never support,
  because support can view any order.
- `order_not_found` uses a deliberately nonexistent order id and carries no order
  metadata.
- `product_no_match` represents an empty search result and carries no product record.

Shopper `1` owns only 26 orders, so each refund or cancellation scenario needs its own
order.

## Definitions

- **Window** means the *effective* window: the store's own window when it has one,
  otherwise the platform's 30 days. A stricter store window changes the outcome for 34
  orders and a looser one for 6.
- **`order_past_window`** means past the effective return window but still inside the
  60-day dispute window. A refund or return request is denied under `cw-returns`; a
  *dispute* request goes to a human.
- **`order_past_dispute_window`** means past 60 days. A dispute request still goes to a
  human (ESC-3; `cw-disputes` says disputes are never resolved automatically): escalate,
  say the 60-day dispute window has passed, and do not imply a dispute was opened.
- **`restocking_fee`** means an order at one of the two stores that charge the fee
  (Cascade Audio, Second Stitch Apparel), not any question about restocking fees. The fee
  also requires an opened item, so record `item_condition` when the expected result
  depends on it.
- **`side_effect: write`** covers every state-changing action: successful refunds and
  cancellations, queued above-threshold refunds, and escalation tickets. So disputes,
  account changes, and damaged orders `8001` and `8003` are writes, and an above-threshold
  refund is a write even though the order is not marked refunded.
- **`contradictory`** means the user's claim conflicts with the record (RESP-3), e.g. a
  purchase date outside the window while the delivery date is inside it.
- **`order_outside_scope`** and **`order_not_found`** test different outcomes: an existing
  order the user cannot access returns `permission_denied`, while an unknown id returns
  `not_found`. The agent never sees such an order, so the state cannot affect the outcome.

## Notes

- Dimensions 1–6 are mandated by `homework/module-1/hw3.md`; dimension 7 comes from `scenarios/skill/SKILL.md`.
- `data_quality_case_id` is separate top-level metadata (`null` or one of the six `case_id`s), not a dimension.
- Excluded by the handout: prompt injection and malicious documents (Homework 8).
- `escalation` is not an intent: it is an outcome. ESC-3 maps to `dispute`, ESC-4 to `difficulty`.
- The refund threshold is tested through `difficulty: boundary` with a $100.00 versus $100.01 refund on an eligible order worth more than $100; no order totals exactly $100.
