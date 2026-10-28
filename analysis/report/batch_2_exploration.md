# Batch 2: 30 by role (10 shopper, 10 merchant, 10 support)

## Groups and their notes

| Group | Notes |
|---|---|
| **1. Doesn't narrow the search to a known store** · 4 traces | • `1bd92460` "The customer already provided the store name. The agent could use it to filter the customer order"<br>• `275066f1` "The agent should filter the order using the store id"<br>• `55e41507` "The agent ignores the store name and list all the shopper's orders"<br>• `22f0af59` "The agent should filter the customer's orders by the store name" |
| **2. Reveals internal policy details** · 4 traces | • `5ccf99b3` "Leaked policy ID"<br>• `20359fb5` "Leaked internal information (policy ID)"<br>• `a39aefca` "Leaked internal information (policy ID)"<br>• `22f0af59` "Leaked policy ID" |
| **3. Reveals problems in the store data** · 1 trace | • `104c7ebc` "Leaked wrong data" |
| **4. No reply to the customer** · 3 traces, all merchants | • `275066f1` "No agent reply"<br>• `94b6ab79` "No agent reply"<br>• `845aadd3` "No agent reply" |
| **5. Escalates a refund that isn't eligible** · 1 trace | • `55e41507` "the agent escalate to human an order with a none eligible refund" |
| **7. Guesses which order the customer means** · 3 traces | • `dd6f0728` "The agent might ask a follow up question. As the user is a merchant, I'm assuming he want a specific order"<br>• `f87559c0` "The agent should ask follow up question or list the detail of this order as it says 'I found multiple ...'"<br>• `20018215` "The agent guessed an order instead of asking for a specific order to check" |
| **8. Too much detail** · 2 traces | • `a39aefca` "the answer is too long as the user already said that he is already overwhelmed"<br>• `22f0af59` "Useless detail" (on "store ID 17") |
| **11. Unclear next step** (new) · 2 traces | • `fc6c8df9` "What a way to answer :D?" (on "Order ID needed.")<br>• `8ebded8f` "What can mean 'another detail' for someone? The agent should be very specific to better guide a user" |
| **12. Date errors** (new) · 1 trace | • `d7e3af35` "Wrong answer. The agent didn't pay attention about the 'WORLD_ASOF' variable" |
| **13. Searches a store name as a product** (new) · 1 trace, plus 1 revisited | • `20018215` "The agent looked for all products with name 'Pocket Arcade' instead of looking for orders from the store name 'Pocket Arcade'"<br>• `a4aeceed` (batch 1, revisited) "The agent search all product named 'Golden Hour Coffee' or similar instead of filtering or find orders where the store name is 'Golden Hour Coffee'" |
| **14. Ignores the caller's role** (new) · 1 revisited | • `a4aeceed` (batch 1, revisited) "the support asks the question as if he was a shopper. Then the agent listed everything especially orders that don't belong to the current user" |

## Candidate failure modes

See [failure_modes.md](failure_modes.md), shared by every batch.

## Outside the failure modes

| Kind | What | Where |
|---|---|---|
| Bug | `find_order`'s fuzzy match lets a one-letter difference match another word: "pocket" scores 0.83 against "socket", above the 0.8 threshold, so "Pocket Arcade" returned socket sets. Needs a fix and a regression test. | `agent/tools.py` (`_title_score`), seen in `20018215` |
| Improvement idea | When the customer asks for "the latest" order, fetch only the latest one instead of the whole list, to save tokens. | `1dfc8b53` |
| Test data | Role-mismatched scenarios: 7 of 13 support and 5 of 13 merchant conversations in batches 1–2 are worded like a shopper ("I placed an order", "my order from…"). 5 more support ones name no customer. Only 1 support conversation reads like real support work. | Scenario generation (HW3) |
