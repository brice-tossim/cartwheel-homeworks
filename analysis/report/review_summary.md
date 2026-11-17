# Review summary

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
