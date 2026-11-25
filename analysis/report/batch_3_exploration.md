# Batch 3: 25 traces from depth searches

## Outside the failure modes

| Kind | What | Where |
|---|---|---|
| Improvement idea | When the customer names a store, look up that store's orders in one step. The agent found the right two orders but needed 5 tool calls (the whole order list, a product-name search, a catalog search, then two order fetches) where a lookup filtered by store would need 1 or 2. | `dd14ea25` (batch 1, revisited) |
