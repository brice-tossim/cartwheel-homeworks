# Failure modes

Generated from `analysis/state/patterns.json`; edit that file, then run `uv run python -m analysis.helpers.failure_modes_report`.

| Mode | Fails when… | Batch 1 | Batch 2 | Batch 3 | Batch 4 | Total |
|---|---|---:|---:|---:|---:|---:|
| `misses_store_orders` | The customer names a store, and the agent doesn't find their orders from it: its lookup doesn't narrow to that store, it searches the store name as a product, or it has the store's orders but doesn't connect them. It answers or asks the customer anyway. | 10 | 6 | 10 | 3 | 29 |
| `reveals_internal_details` | The reply tells the customer a policy id, an internal threshold, how a request is processed behind the scenes, or errors in the store data. | 12 | 7 | 7 | 7 | 33 |
| `mishandles_ambiguous_request` | Several orders could match, or the agent needs more from the customer, and it either picks one without asking or asks in a way that leaves the customer unsure what to give. | 6 | 7 | 0 | 2 | 15 |
| `no_reply` | The turn ends without any reply to the customer. | 4 | 3 | 0 | 0 | 7 |
| `date_errors` | The reply uses a current date other than the platform date (world_asof), counts days from the wrong date, or misstates how old an order is compared with the platform date. "Most recent" or "latest" means the newest of the matching orders and is not a date error; "recent" on its own means placed within the last 30 days. | 2 | 2 | 4 | 1 | 9 |
| `ignores_caller_role` | The agent treats a support or merchant caller as a shopper in a way that changes what it does or shows: for example, it presents other customers' orders as the caller's, or never asks a support caller which customer or order they mean. Shopper-style wording alone ("your confirmation email"), around a request that still fits the caller's role, is not a failure. | 1 | 0 | 2 | 0 | 3 |
| `too_much_detail` | The reply includes details the customer did not ask for and does not need. | 2 | 2 | 0 | 1 | 5 |
| `escalates_without_need` | The agent opens, or offers to open, a human review that isn't needed: for a refund the tool marks as not refund eligible, for something the agent can answer itself, before it knows what the customer means, or a second time for a request already queued for human review. | 3 | 1 | 0 | 5 | 9 |
