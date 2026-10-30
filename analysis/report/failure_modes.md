# Failure modes

Generated from `analysis/state/patterns.json`; edit that file, then run `uv run python -m analysis.helpers.failure_modes_report`.

| Mode | Fails when… | Batch 1 | Batch 2 | Batch 3 | Total |
|---|---|---:|---:|---:|---:|
| `misses_store_orders` | The customer names a store, and the agent doesn't find their orders from it: its lookup doesn't narrow to that store, it searches the store name as a product, or it has the store's orders but doesn't connect them. It answers or asks the customer anyway. | 12 | 5 | 9 | 26 |
| `reveals_internal_details` | The reply tells the customer a policy id, an internal threshold, how a request is processed behind the scenes, or errors in the store data. | 10 | 5 | 7 | 22 |
| `mishandles_ambiguous_request` | Several orders could match, or the agent needs more from the customer, and it either picks one without asking or asks in a way that leaves the customer unsure what to give. | 3 | 5 | 0 | 8 |
| `no_reply` | The turn ends without any reply to the customer. | 4 | 3 | 0 | 7 |
| `date_errors` | The reply uses a current date other than the platform's current date (world_asof), or counts dates or days from the wrong current date. | 1 | 1 | 4 | 6 |
| `ignores_caller_role` | The agent handles the request as if the caller were a shopper, when the caller's role calls for something else (for example, asking a support caller which customer they mean). | 1 | 0 | 3 | 4 |
| `too_much_detail` | The reply includes details the customer did not ask for and does not need. | 2 | 2 | 0 | 4 |
| `escalates_ineligible_refund` | The agent opens a human review for a refund on an order that the tool result marks as not refund eligible. | 2 | 1 | 0 | 3 |
