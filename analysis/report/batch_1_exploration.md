# Batch 1: 15 random + 15 cluster

## Groups and their notes

| Group | Notes |
|---|---|
| **1. Doesn't narrow the search to a known store** · 9 traces | • `7d614db0` "agent use list_my_orders first but the customer specify… Pocket Arcade"<br>• `c0749c66` "'… order' preceded by a name is an order from a store"<br>• `a7e9dd44` "specified the store name, but the agent starts by listing all the customer's orders"<br>• `dd14ea25` "'Copperline Tools'… should start by retrieve this store"<br>• `c77bc73d` "'from harbor knits'… should start by retrieving this store"<br>• `fb77a52d` "should start by retrieving the store id"<br>• `e2e0f709` "should start by retrieving the store id"<br>• `72e33e74` "should start by retrieving the store id"<br>• `2c9307a3` "already know that 'Golden Hour Coffee' is a store based on the previous turn" |
| **2. Reveals internal policy details** · 8 traces | • `7d614db0` "don't have to know about the amount threshold"<br>• `cf892701` "don't have to know about the policy id"<br>• `5649ffb0` "how it's processed behind the scene"<br>• `e2e0f709` "Leaking details about the amount limit"<br>• `259155c9` "policy override… policy ID should not be leaked"<br>• `77fef59b` "must not leak policy ID"<br>• `72e33e74` "Also leaked policy id"<br>• `188a1c3a` "don't have to know about internal process" |
| **3. Reveals problems in the store data** · 2 traces | • `6776b7df` "Leaked information about wrong data in the database"<br>• `f3c5672b` "Leaked information about the data" |
| **4. No reply to the customer** · 4 traces | • `3b14d86e` "No answer… no fallback in case of internal error"<br>• `c2363050` "No tool call / no agent reply"<br>• `fb77a52d` "No agent reply"<br>• `47fec190` "Agent not replied" |
| **5. Escalates a refund that isn't eligible** · 2 traces | • `e2e0f709` "why escalating if the order is not eligible"<br>• `72e33e74` "Why escalating to a human if the order is not eligible" |
| **6. Says something the tool data contradicts** · 2 traces | • `dd14ea25` "Based on both order dates, those are not very recent"<br>• `2cfc15cc` "couldn't find a store named 'Blue Heron'… found an item from 'Blue Heron'" |
| **7. Guesses which order the customer means** · 3 traces | • `c77bc73d` "user specify 'a while ago' but the agent pull the recent order without listing the others"<br>• `2c9307a3` "'the other one' is ambiguous… It should ask for clarification"<br>• `188a1c3a` "What if it was eligible, will the agent process it?" |
| **8. Too much detail** · 2 traces | • `22f90c6f` "only asked for the current status and not these details"<br>• `188a1c3a` on the quote "I also found an older Northwind Books order, 7861, but it is not refund-eligible" |
| **9. Presents others' orders as the customer's** · 1 trace | • `a4aeceed` "There is no order of the user 9501 from the store 'Golden Hour Coffee'" |
| **10. Asks the customer for something it could look up** · 1 trace | • `cff5b634` "the agent can list recent order placed by this customer from the store" |

## Candidate failure modes

| Mode | Fails when… | Traces |
|---|---|---|
| `ignores_known_store` | The customer named a store, or an earlier turn found it, and the agent's first order lookup doesn't narrow to that store. | 9 |
| `reveals_internal_policy` | The reply tells the customer a policy id (`cw-refunds`), an internal threshold (the $100 limit), or how a request is processed behind the scenes. | 8 |
| `reveals_data_problems` | The reply tells the customer about errors in the store data (duplicate listings, negative price). | 2 |
| `no_reply` | The turn ends without any reply to the customer. | 4 |
| `escalates_ineligible_refund` | The agent opens a human review for a refund on an order the tool marks not eligible. | 2 |
| `contradicts_tool_data` | The reply says something a tool result, or another part of the same reply, contradicts. | 2 |
| `guesses_order` | Several orders could match, and the agent picks one to report on or act on without listing them or asking. | 3 |
| `too_much_detail` | The reply includes details the customer didn't ask for and doesn't need. | 2 |
| `shows_others_orders` | The reply presents orders that aren't the caller's as theirs. | 1 |
| `asks_for_lookup_info` | The agent asks the customer for something it could have found with its tools. | 1 |
