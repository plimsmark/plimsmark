# Corrections — 2026-09-27

Corrections to earlier dated claims. Earlier fixtures are left unchanged; this
file records what the live evidence now shows.

## The "partial / stale index" claim about publicnode's 0x2::coin answer is REFUTED

**Earlier claim** (the bracketed spike, `reference/observed_2026-09-27-sui.md` §7):
publicnode's `suix_queryEvents {MoveModule: 0x2::coin}` returning only 32 events,
newest ~3 weeks stale, indicated a *partial / unreliable event index* on the
third-party node — "advertised-vs-measured".

**Correction: this is refuted by the cross-provider evidence.**

- The 32 events are **not** coin-module events. Every one has type
  `0x2::deny_list::PerTypeConfigCreated`. JSON-RPC `MoveModule` filters by the
  **module of the transaction's Move call** (a call into `0x2::coin`), not by the
  event's own type; the events those calls emit are `deny_list` events. (Evidence:
  `semantics_2026-09-27.md` §"JSON-RPC MoveModule 0x2::coin semantics".)
- All **three** independent JSON-RPC providers — publicnode, blockvision, rpcpool —
  return exactly **32** events, the **same** type, the **same** oldest/newest span,
  and `hasNextPage = false`. Three independent indexes agreeing on the identical
  bounded set is the opposite of a partial/stale index; it is consistent with 32
  being the true count of `0x2::coin`-called events that emit `deny_list` events.
  (Evidence: run1/run2 Q1 comparison in `premise_2026-09-27.md` §4 — Q1 `agree`,
  publicnode = blockvision = rpcpool = 32, both runs.)
- A genuine high-volume `0x2::coin`-related type behaves differently: querying the
  event's own struct type as `MoveEventType` (`0x2::deny_list::PerTypeConfigCreated`)
  returns **1416** events across all four providers, identical id sets — not 32.
  The "32" was an artifact of the `MoveModule` filter's called-module semantics,
  never a retention gap.

**Takeaway:** `MoveModule` matches the transaction's called module, not the event
type. A small count under `MoveModule` is not evidence of a partial index. To
enumerate a specific event type, filter by `MoveEventType` (JSON-RPC) / `type` with
a fully-qualified type name (GraphQL).
