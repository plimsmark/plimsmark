# Semantics & comparability evidence — 2026-09-27

Vantage `local-dev`, UA `plimmark-sui-spike/0.1`. Every claim below is backed by
a live observation row in this run's `discovery*.rows.jsonl`. Re-verify; these go
stale.

## EventFilter fields (introspected live — item 5b)

From `fixtures/graphql_introspection_2026-09-27.json`, `EventFilter` input fields:

```
afterCheckpoint   :: UInt53
atCheckpoint      :: UInt53
beforeCheckpoint  :: UInt53
sender            :: SuiAddress
module            :: String     # "package or package::module" — EMITTING module
type              :: String     # "package, package::module, or FQ type name"
```

JSON-RPC `suix_queryEvents` filter variants (from the -32602 error text):
`All, Any, Sender, Transaction, MoveModule, MoveEventType, MoveEventModule, TimeRange`.

## Event identity (item 5b)

- JSON-RPC event id = `(id.txDigest, id.eventSeq)`.
- GraphQL event id = `(transaction.digest, sequenceNumber)` — introspected:
  `Event.sequenceNumber :: UInt53!`, `Event.transaction :: Transaction`,
  `Transaction.digest :: String!`.
- These are the **same identity**: GraphQL `sequenceNumber` == JSON-RPC
  `eventSeq`, GraphQL `transaction.digest` == JSON-RPC `txDigest`. So no
  fallback (tx, type, occurrence-index) is needed; identity is exact.

## JSON-RPC MoveModule 0x2::coin semantics (item 5c)

```
publicnode  MoveModule{0x2::coin} limit 50 -> 32 events, hasNextPage=False,
                                              oldest 2025-05-08, newest 2026-09-03
blockvision  same -> 32 events, same type, same span
rpcpool      same -> 32 events, same type, same span
```

Every one of those 32 events has type **`0x2::deny_list::PerTypeConfigCreated`** —
NOT a coin-module event. This is the direct evidence that JSON-RPC `MoveModule`
matches the **module of the transaction's Move call** (here: a call into
`0x2::coin`), and the events those calls emit happen to be `deny_list` events.

**Explicit caveat (as required):** publicnode's 32-event answer for
`MoveModule 0x2::coin` is NOT by itself evidence of a partial index. Direct Move
calls into `0x2::coin` that emit events are genuinely rare, so 32 may be the true
total — and all three JSON-RPC providers independently returned exactly 32, the
same types, and the same span, which is consistent with 32 being complete. Only
cross-provider **disagreement** could decide otherwise, and here there is none.

## GraphQL `module` is NOT equivalent to JSON-RPC `MoveModule` (item 5c)

```
GraphQL module=0x2::coin  first:5 -> 5 nodes, hasNextPage=True
GraphQL module=0x2        first:5 -> 5 nodes, hasNextPage=True
GraphQL type=0x2::coin    first:5 -> 2 nodes, hasNextPage=False
```

GraphQL `module` filters by the **emitting** module; JSON-RPC `MoveModule`
filters by the **called** module. Different meaning, different result sets.
Therefore **Q1's GraphQL leg is `not_comparable`**, never "different".

## The comparable predicate

Use **event struct type**: JSON-RPC `MoveEventType` == GraphQL `type` with a
fully-qualified type name. Both filter on the event's own struct type, which is
unambiguous. This is what Q1b and Q2 compare on.

## Window access strategy (item 5d — tested live, in order)

1. **compound `All[MoveEventType, TimeRange]`** — REJECTED, `-32602 Invalid
   params`, on publicnode / blockvision / rpcpool. Dead.
2. **cursor seeding (chosen primary)** — seed a descending `suix_queryEvents
   {MoveEventType}` from the GraphQL event id at/after `c_end`. ACCEPTED on all
   3 JSON-RPC providers; returned rows are all the requested type. Filters by
   type server-side, so it does not drown in off-type events.
3. **`TimeRange` alone (fallback)** — ACCEPTED on all 3; returns all types in the
   window, type filtered client-side. Used only if cursor seeding fails for a
   provider.

GraphQL uses the native `type` + `afterCheckpoint`/`beforeCheckpoint` range.
