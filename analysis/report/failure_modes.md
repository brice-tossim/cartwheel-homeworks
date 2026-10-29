# Failure modes

Generated from `analysis/state/patterns.json`; edit that file, then run `uv run python -m analysis.helpers.failure_modes_report`.

| Mode | Fails when… | Batch 1 | Batch 2 | Batch 3 | Total |
|---|---|---:|---:|---:|---:|
| `ignores_known_store` | The customer named a store, or an earlier turn found it, and the agent's first order lookup does not narrow to that store. | 9 | 4 | 0 | 13 |
| `reveals_internal_policy` | The reply tells the customer a policy id (such as cw-refunds), an internal threshold (such as the $100 auto-approval limit), or how a request is processed behind the scenes. | 8 | 4 | 7 | 19 |
| `reveals_data_problems` | The reply tells the customer about errors in the store data, such as duplicate listings or a negative price. | 2 | 1 | 0 | 3 |
| `no_reply` | The turn ends without any reply to the customer. | 4 | 3 | 0 | 7 |
| `escalates_ineligible_refund` | The agent opens a human review for a refund on an order that the tool result marks as not refund eligible. | 2 | 1 | 0 | 3 |
| `contradicts_tool_data` | The reply says something that a tool result, or another part of the same reply, contradicts. | 2 | 0 | 0 | 2 |
| `guesses_order` | Several orders could match, and the agent picks one to report on or act on without asking which one the customer means. | 3 | 3 | 0 | 6 |
| `too_much_detail` | The reply includes details the customer did not ask for and does not need. | 2 | 2 | 0 | 4 |
| `shows_others_orders` | For a shopper or merchant caller, the reply presents orders that are not the caller's as theirs. | 0 | 0 | 0 | 0 |
| `asks_for_lookup_info` | The agent asks the customer for information it could have found with its tools from what it already knows. | 1 | 0 | 3 | 4 |
| `unclear_next_step` | The agent asks the customer for information but leaves them unsure what to give: it names it vaguely, or gives no hint where to find it. | 0 | 2 | 0 | 2 |
| `date_errors` | The reply uses a current date other than the platform's current date (world_asof), or counts dates or days from the wrong current date. | 0 | 1 | 4 | 5 |
| `searches_store_as_product` | The agent passes a store name to find_order, which matches product names, and answers from those results: either presenting the matches as that store's orders, or saying the customer has no order there. | 1 | 1 | 8 | 10 |
| `ignores_caller_role` | The agent handles the request as if the caller were a shopper, when the caller's role calls for something else (for example, asking a support caller which customer they mean). | 1 | 0 | 3 | 4 |
