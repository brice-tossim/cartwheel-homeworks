# Batch 4: 15 uniformly sampled traces

## Outside the failure modes

| Kind | What | Where |
|---|---|---|
| Improvement idea | When the customer names a store, filter their orders by that store in the first lookup. In these conversations the agent still found the right order, but only after listing every order (or searching the store name as a product) and then matching the store through the catalog: more tool calls and tokens than one store-filtered lookup. They count as close negatives for `misses_store_orders`. | `39224ed8`, `6238f72c`, `57b33232`, `2efac6b6`, `60c6a13a`, `36ccfba9` |
