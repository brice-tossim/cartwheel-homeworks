# Workshop notes (Part C)

10 fresh conversations (11 runs) were run through the Cartwheel CLI on 2026-11-09, on `gpt-4o-mini`, against a copy of the database (`data/part_c_runs.db`). They covered three roles (shopper, merchant, support) and five tools. Traces went to both Raindrop Workshop (local) and Langfuse, under the same trace id, and were reviewed in the review app as `batch_5_workshop`. Workshop's coding agent inspected them blind, without my notes or failure modes.

To check the order facts below without touching your own database or policies, build a fresh copy under the same name (the seed is deterministic):

```sh
uv run python -m seed.generate --db data/part_c_runs.db --policies data/part_c_policies
```

It holds the original world, not the side effects of these runs (such as the email-change ticket).

## Inspected runs

| Run (Workshop / Langfuse trace id) | Session | Caller | Request |
|---|---|---|---|
| `6e1108f51db7a3780b52eadee95a2fcd` | `cli-shopper-1-1794205215` | shopper 1 | Blue Heron order status (turn 1) |
| `a55bb0eb07f86aeffddda132252a6912` | `cli-shopper-1-1794205215` | shopper 1 | "The newest one" (turn 2) |
| `3b73c26ecf515a88662370137e9de024` | `cli-shopper-1-1794205227` | shopper 1 | Atlas Stationery refund, damaged |
| `8b8e1cf662d952e292a5c8d690562c1a` | `cli-shopper-1-1794205238` | shopper 1 | Bright Socket refund |
| `d06b5de3734d75fb10eb21058f003182` | `cli-shopper-1-1794205244` | shopper 1 | Harbor Knits refund, March |
| `95f876b55ef425963d73051945054f00` | `cli-shopper-86-1794205252` | shopper 86 | Cancel the Petal & Stem order |
| `b903d5843291daedc55c523fb4b6cf68` | `cli-shopper-1-1794205269` | shopper 1 | Return window and restocking fee |
| `d5f9bf160b561ff11587c16c7b2567fc` | `cli-shopper-1-1794205278` | shopper 1 | Change account email |
| `d1179bd75aad9504cb092018bc3e7d1f` | `cli-merchant-9001-1794205285` | merchant 9001 | Order 830 shipped? Pending orders? |
| `fd84705bf85d8fd07f9c982df9765601` | `cli-support-9501-1794205296` | support 9501 | Order 4455 arrived broken |
| `c4ff39f028c91c0cd1f0fa41cb97a961` | `cli-shopper-1-1794205306` | shopper 1 | Check a friend's order 180 |

A follow-up turn was later added to the friend's-order conversation with `--resume`: `6137e8bfe5dca7371a6c4ac9d428a961` ("it's order 180").

## Workshop's suggestions and my decisions

| Workshop suggestion | Decision | Why |
|---|---|---|
| Blue Heron: the agent could not match the store in the order list | **Accepted**: `misses_store_orders` | The list held order #4455 from Blue Heron, and the agent said it could not find one. |
| Blue Heron turn 2: store named without a new lookup | **Rejected** | The claim is correct (#4455 is Blue Heron), and the answer is what the customer needed. |
| Petal & Stem: cancellation stalled on store identification (uncertain) | **Revised** to a confirmed `misses_store_orders` | "I don't see an order for Petal & Stem" is false: #5473 is the customer's only Petal & Stem order. |
| Support refund for #4455: approval condition left out, plus "original packaging" | **Rejected** | No refund was attempted, so no rule required mentioning approval. The support agent got the answer they needed. |
| Friend's order: the reply contradicts itself | **Revised** to a confusing answer (new candidate, 1 case) | Refusing is right (order 180 belongs to another user). The agent then asks for the number the customer already gave. In turn 2 it pointed the friend to support, with no failure. |
| Return policy: no policy citation | **Rejected**, and the reverse recorded: `reveals_internal_details` | The reply shows "policy id: cw-returns". My taxonomy counts that as a failure; Workshop applied the spec's RESP-1. |
| Return policy: store overrides left out | **Accepted** as an incomplete answer (new candidate) | The retrieved policy says stores may override the 30-day window. The reply gives 30 days as the rule. |
| Atlas and Harbor Knits: searches found nothing, worth investigating | **Revised** to `misses_store_orders` for both | Both stores have orders for user 1 (#1689 and #5086). The agent searched the store name as a product and never listed the orders. |
| Bright Socket: refusal supported by `refund_eligible: false` | **Rejected**: `misses_store_orders` | The search returned Copperline Tools #6182, a "Sturdy Socket Set". The Bright Socket order is #301, which is refund-eligible. |
| Email change: escalated, no failure | **Accepted** | The spec requires escalating account changes (ESC-2). |

The merchant run (order 830 and pending orders) was not discussed by Workshop.

## Uncertainty case

Workshop marked Petal & Stem as uncertain: "the trace alone does not establish which order was Petal & Stem." The order list shows store numbers but no store names, so the trace cannot settle it. The database does: #5473 is from store 3, Petal & Stem.

## Challenge: Workshop with database access

Workshop missed three failures because it trusted the tool results. I gave it the database path (read-only) and asked it to recheck those three runs. It ran SQL and returned rows that match mine:

- **Bright Socket:** it now calls the refusal incorrect, since the search returned an unrelated socket set from Copperline Tools.
- **Atlas:** it agrees a matching order (#1689) was missed, while noting the description doesn't prove it was the damaged item.
- **Harbor Knits:** it still sees no failure, because the only order is a scarf, not a sweater. I count it as `misses_store_orders`: the store and the time match, and the item is clothing, so the agent should have found the order and asked. This boundary belongs in the mode's definition.

## Takeaways

- Without the data behind the trace, Workshop checks replies against tool results but can't see orders the tools never returned. It missed all 3 `misses_store_orders` cases that hid behind an empty or wrong search.
- With read-only database access, it confirmed 2 of the 3 and made a defensible call on the third.
- New candidates to watch: **incomplete answer** (2 cases across both Workshop rounds) and **confusing answer** (1 case).
