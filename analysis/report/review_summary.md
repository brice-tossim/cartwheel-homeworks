# Review summary

## Reviewed sample

117 traces, each labelled present or absent for all 8 modes (scores in Langfuse and `analysis/state/labels/`).

| Source | Traces | How picked |
|---|---|---|
| `batch_1_clusters` | 16 | one representative per cluster |
| `batch_1_random` | 15 | random |
| `batch_2_roles` | 30 | by caller role |
| `batch_3_search` | 27 | depth search for candidate modes |
| `batch_4_random` | 15 | random |
| `batch_5_workshop` | 11 | Part C CLI runs |
| Close-negative search | 3 | look like a mode, without the failure |

The batch files in `analysis/state/batches/` replace `sample_manifest.json`: they record which traces were picked, how and why.

Only 30 of the 117 traces are random picks. The rest were chosen to find or test failures.

## Sample fractions

Share of the 117 reviewed traces where each mode is present. These describe the sample (how often each failure happens across the 117 traces chosen for review), not prevalence (how often each failure happens across all of the agent's traces): the searches and close negatives were picked on purpose.

| Mode | Present | Fraction |
|---|---|---|
| `reveals_internal_details` | 37 | 31.6% |
| `misses_store_orders` | 32 | 27.4% |
| `mishandles_ambiguous_request` | 15 | 12.8% |
| `date_errors` | 9 | 7.7% |
| `escalates_without_need` | 9 | 7.7% |
| `no_reply` | 7 | 6.0% |
| `too_much_detail` | 5 | 4.3% |
| `ignores_caller_role` | 3 | 2.6% |

A trace can have several modes: 38 traces have none, 79 have at least one.

## Stability

**0 new modes in the final 15 traces.**

Two single failures showed up in the Part C runs. No other trace looked like them, so they stay open as observations, not modes:

- `b903d584`: gives 30 days as the return rule without saying stores can set their own window.
- `c4ff39f0`: rightly refuses to show a friend's order, then asks for the order number the customer already gave.

## Taxonomy revisions

Rule: merge when one product change fixes both, split when they need different fixes.

| Final mode | Came from | Why |
|---|---|---|
| `misses_store_orders` | merged `ignores_known_store`, `searches_store_as_product`, `asks_for_lookup_info` | One fix: when the customer names a store, look up that store's orders first (ORD-1). |
| `reveals_internal_details` | merged `reveals_internal_policy`, `reveals_data_problems` | One fix: keep internal information (policy IDs, thresholds, data errors) out of replies. |
| `mishandles_ambiguous_request` | merged `guesses_order`, `unclear_next_step` | One fix: when the request is unclear, ask a clear question before acting. |
| `ignores_caller_role` | merged `shows_others_orders` | One fix: handle the request for the caller's actual role. |
| `escalates_without_need` | merged `escalates_ineligible_refund`, widened to other needless escalations | One fix: escalate only when a human is actually needed. |
| `misses_store_orders` + `date_errors` | split `contradicts_tool_data` | Its traces needed different fixes: one was a missed store lookup, the other a wrong date. |

## Close negatives

A close negative must look like what a mode's positives share, yet not contain the failure. Each candidate was checked against the trait the positives share and against the mode's boundary. Two modes have none, because the data offers no trace that fits.

| Mode | Close negatives |
|---|---|
| `misses_store_orders` | 15 |
| `mishandles_ambiguous_request` | 10 |
| `date_errors` | 3 |
| `ignores_caller_role` | 3 |
| `too_much_detail` | 3 |
| `escalates_without_need` | 3 |
| `no_reply` | 0 |
| `reveals_internal_details` | 0 |

### `no_reply`: none

The seven positives share nothing except the missing reply, which is the failure itself:

- two end right after a lookup that returned nothing,
- three end after a lookup that returned results,
- two end before any tool call.

With no common trait, a trace that "looks like a `no_reply` but replies" mirrors one positive at best. The three candidates first proposed (`3994621e`, `c25a826c`, `f08d7974`) each matched only the empty-lookup pair, so they were rejected. The mode is also a code check ("does the turn end with assistant text?"), which leaves no grey zone for a close negative to test.

### `reveals_internal_details`: none

31 of the 36 positives looked up a policy, so a close negative would be a policy answer that leaves out the policy ID. None of the 274 traces has one. Every reply that uses a policy cites its ID (`cw-…` or `store-…-policy`), because the agent's system prompt requires it: "Cite the policy id (for example cw-returns) for every policy claim."

The gap is a finding, not a missing search. The prompt instruction causes the failure, which supports the product change behind RESP-1 (cite the policy's link, not its identifier). The three escalation replies first proposed (`de289e8a`, `b3845e2f`, `7d62c381`) contain nothing internal, but none looked up a policy, so they were rejected.

Every proposed close negative, accepted or rejected, is in `analysis/state/suggestions.json` with source `close_negative_search`. Each rejected one gives its reason in `decision_reason`.
