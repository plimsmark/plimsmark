# Observed — Sui mainnet feasibility spike, 2026-09-27

Can bracketed measure Sui? This freezes the live shapes that decide it. Every line was
read from a live endpoint on 2026-09-27 by `scripts/sui_probe.py` (re-run it to refresh —
these go stale, which is the point of dating them). Vantage: the dev machine, UA
`bracketed-sui-spike/0.1`. Tip checkpoint drifted 327,442,319 → 327,443,669 across the
run as the chain advanced (~327.4M).

**The one question this spike answers:** bracketed's core abstraction is the SPAN — the
widest `eth_getLogs` block range a query still succeeds at, stored as a bracket
(`max_ok < limit <= min_fail`). Sui paginates events by CURSOR, not by range. Does a
CHECKPOINT RANGE behave like a span — does a widening range FAIL at some width we can
bracket? **Answer: no.** See §4.

---

## 1. Endpoint liveness + classification

```
Mysten fullnode JSON-RPC   fullnode.mainnet.sui.io   HTTP 200, rpc -32601:
  "Method not found. JSON-RPC on public fullnodes has been deprecated. Please migrate to
   gRPC or GraphQL endpoints. See https://docs.sui.io/develop/accessing-data/json-rpc-migration
   for more information."
Mysten GraphQL             graphql.mainnet.sui.io/graphql   ALIVE, tip ~327.44M
Mysten GraphQL (alt)       sui-mainnet.mystenlabs.com/graphql   connection reset / unreachable
publicnode  (JSON-RPC)     sui-rpc.publicnode.com            ALIVE, checkpoint 327443667
blockvision (JSON-RPC)     sui-mainnet-endpoint.blockvision.org  ALIVE, checkpoint 327443668
rpcpool     (JSON-RPC)     mainnet.sui.rpcpool.com           ALIVE, checkpoint 327443669
drpc                       sui.drpc.org   HTTP 400, code 11 "Unknown network"
```

- **The official JSON-RPC is gone.** `-32601` is a DEFINITIVE "this method no longer
  exists" — the whole JSON-RPC surface on Mysten fullnodes is retired in favour of
  GraphQL/gRPC. In bracketed's taxonomy this is a definitive, permanent refusal (never
  retry), and it is a property of the API generation, not a span.
- **`sui.drpc.org` "Unknown network" (code 11) is a WRONG URL, not a missing chain.** dRPC
  routes by a network parameter / key scheme (e.g. `lb.drpc.org/.../sui`), so the bare
  `sui.drpc.org` host does not resolve to their Sui service. Not a provider outage — our
  endpoint string is wrong. (Treat like `misconfigured`, not a provider failure.)
- publicnode / blockvision / rpcpool still serve the legacy JSON-RPC and are at the live
  tip. Blast API ("no longer available") and Ankr (requires a key) were not re-probed.

## 2. GraphQL EventFilter + events() — INTROSPECTED (the schema changes across versions)

`__type(name:"EventFilter")` input fields:

```
afterCheckpoint  :: UInt53   "Limit to events that occured strictly after the given checkpoint."
atCheckpoint     :: UInt53   "Limit to events in the given checkpoint."
beforeCheckpoint :: UInt53   "Limit to event that occured strictly before the given checkpoint."
sender           :: SuiAddress
module           :: String   "Events emitted by a particular module" (package or package::module)
type             :: String   "package, package::module, or fully-qualified type name"
```

`events()` arguments: `first:Int, after:String, last:Int, before:String, filter:EventFilter`
— Relay-style cursor pagination (`after`/`before` are opaque cursors) plus the filter.

**So a checkpoint RANGE filter exists** (`afterCheckpoint` + `beforeCheckpoint` bound a
range; `atCheckpoint` scopes to one). This is the only thing on Sui that *looks* like an
EVM block range. §4 tests whether it behaves like a span.

## 3. Page-size cap — a span-INDEPENDENT known constant

```
events(first:51)  ->  {"errors":[{"message":"Page size is too large: 51 > 50",
                        "extensions":{"code":"GRAPHQL_VALIDATION_FAILED"}}]}
events(first:50)  ->  accepted
```

The cap is 50 nodes per page, stated up front as a VALIDATION error (before execution).
It caps OUTPUT NODES, not the range — it is a fixed, declared, span-independent constant,
not a hidden limit to discover. You page past it with cursors.

## 4. THE DECISIVE TEST — a widening checkpoint range does NOT fail

`events(first:50, filter:{afterCheckpoint: tip-width, beforeCheckpoint: tip})`, near the tip:

```
       width   secs  result
           1    0.4  nodes=0  hasNextPage=False   (strictly-after/before excludes both ends)
          10    1.1  nodes=50 hasNextPage=True
         100    0.4  nodes=50 hasNextPage=True
       1,000    1.0  nodes=50 hasNextPage=True
      10,000    0.6  nodes=50 hasNextPage=True
     100,000    0.5  nodes=50 hasNextPage=True
   1,000,000    1.1  nodes=50 hasNextPage=True
  10,000,000    1.1  nodes=50 hasNextPage=True
```

**A range 10,000,000 checkpoints wide answers identically to one 10 wide — 50 nodes,
hasNextPage:true, in ~1s.** There is no width at which the query fails, times out, or is
cost-capped. The range is a FILTER, not a capacity limit; what binds is the page size
(§3, span-independent) and the scan budget (§5). There is no "widest range that still
succeeds" to bracket, because every range succeeds up to the page cap. **The span model
has no failure edge on Sui.**

## 5. Scan budget — a partial page, not a range failure

```
events(first:50)                             -> nodes=0  hasNextPage=True   (forward from genesis)
events(first:50, filter:{afterCheckpoint:1}) -> nodes=0  hasNextPage=True
events(last:50)                              -> nodes=50 hasPreviousPage=True hasNextPage=False
```

Scanning FORWARD from genesis returns ZERO nodes with `hasNextPage:true` — not "no
events", but a SCAN BUDGET exhausted before it accumulated a page (early checkpoints are
sparse and it examines only a bounded number per request). `last:50` from the tip fills a
page immediately. So the binding behaviour on a sparse query is: return whatever the
budget found (possibly nothing) plus a cursor to continue — span-INDEPENDENT (a fixed
per-request budget), handled by following `after`/`before`, never by narrowing a range.

## 6. JSON-RPC has NO checkpoint range — only TimeRange

```
publicnode suix_queryEvents {afterCheckpoint:1}  ->  rpc -32602 "Invalid params":
  "unknown variant `afterCheckpoint`, expected one of `All`, `Any`, `Sender`,
   `Transaction`, `MoveModule`, `MoveEventType`, `MoveEventModule`, `TimeRange`"
publicnode suix_queryEvents {TimeRange:{startTime,endTime}}  ->  accepted, returns events
blockvision  {afterCheckpoint:1}  ->  same "unknown variant `afterCheckpoint`" error
```

The surviving JSON-RPC `EventFilter` has exactly one RANGE dimension and it is TIME
(`TimeRange`), not checkpoints. No `afterCheckpoint`/`beforeCheckpoint` on any provider
tested. So even the range that GraphQL offers does not exist on JSON-RPC.

## 7. Retention / index completeness — a data-quality finding, not a span

```
publicnode suix_queryEvents {MoveModule:{package:"0x2", module:"coin"}} limit 50
  ->  32 events, hasNextPage:FALSE, oldest 2025-05-08, newest 2026-09-03
```

`0x2::coin` on mainnet has orders of magnitude more activity than 32 events, and the
newest returned event is ~3 weeks stale against a live tip. So this is NOT a clean
"retention window since date X" — it is a PARTIAL / unreliable event index on the
third-party node (event indexing is expensive; providers prune or cap it). That gap
between what the endpoint advertises (a full node) and what it serves (a truncated index)
is a genuine advertised-vs-measured finding — but it is about the provider's index
quality, not a span the chain imposes.

---

## What this decides

Sui GraphQL offers a checkpoint range, but **widening it never fails** (§4), so there is
no span to bracket. The real limits — page size 50 (§3), scan budget (§5), TimeRange-only
on JSON-RPC (§6), partial third-party indexes (§7) — are all either span-INDEPENDENT
constants or data-quality properties, none of them a "widest range that still succeeds".
The verdict and Phase 2 design are in HANDOFF "Sui feasibility (spike, 2026-09-27)".
