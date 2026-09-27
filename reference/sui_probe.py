"""Sui feasibility spike — does bracketed's SPAN model apply to Sui? (2026-09-27)

Usage:  python3 scripts/sui_probe.py

Deliberately a standalone, human-run, NETWORK-using script — like live_probe.py, and
for the same reason: it hits live endpoints, results change, and a red CI run should
mean our code broke, not that Sui changed. It imports NOTHING from `bracketed` and is
imported by NOTHING in the runner or tests; it exists only to answer the one question
that decides whether bracketed can measure Sui at all:

    bracketed's core abstraction is the SPAN — the widest eth_getLogs block range a query
    still succeeds at, stored as a bracket (max_ok < limit <= min_fail). Sui is not EVM:
    events are paginated by CURSOR, not fetched by block range. Does a CHECKPOINT RANGE
    behave like a span — i.e. does a widening range fail at some width we can bracket?

What it checks (freeze the output in fixtures/observed_2026-09-27-sui.md):
  1. endpoint liveness + how each failure classifies (deprecation / 503 / unknown network)
  2. GraphQL EventFilter + events() args, by INTROSPECTION (the schema changes across
     versions — never trust memory)
  3. the page-size cap (first:51 -> error), a span-INDEPENDENT known constant
  4. THE DECISIVE TEST: a widening afterCheckpoint..beforeCheckpoint range — does it fail?
  5. the scan budget (forward-from-genesis returns 0 nodes + hasNextPage:true)
  6. JSON-RPC EventFilter: is there a checkpoint range at all? (no — only TimeRange)
  7. retention / completeness on a third-party JSON-RPC index (0x2::coin)

Nothing here is trusted from memory; every line prints what the live endpoint returned.
"""

import json
import sys
import time
import urllib.request

TIMEOUT = 40.0
UA = "bracketed-sui-spike/0.1 (+https://bracketedz.com)"

GRAPHQL = "https://graphql.mainnet.sui.io/graphql"
GRAPHQL_ALT = "https://sui-mainnet.mystenlabs.com/graphql"
FULLNODE_RPC = "https://fullnode.mainnet.sui.io"           # Mysten — JSON-RPC deprecated
THIRD_PARTY_RPC = {
    "publicnode": "https://sui-rpc.publicnode.com",
    "blockvision": "https://sui-mainnet-endpoint.blockvision.org",
    "rpcpool": "https://mainnet.sui.rpcpool.com",
    "drpc": "https://sui.drpc.org",
}


def _post(url, payload):
    """POST JSON, returning (http_status|None, parsed|None, error_text). Non-raising, so
    one dead endpoint never stops the sweep — the same discipline as probe.http_transport."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw), ""
            except json.JSONDecodeError:
                return r.status, None, raw[:300].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), ""
        except json.JSONDecodeError:
            return e.code, None, raw[:300].decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — a dead endpoint is a finding, not a crash
        return None, None, f"{type(e).__name__}: {e}"


def gql(query, url=GRAPHQL):
    return _post(url, {"query": query})


def rpc(method, params, url):
    return _post(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _err(parsed):
    if isinstance(parsed, dict):
        if "error" in parsed:                       # JSON-RPC envelope
            e = parsed["error"]
            return f"code={e.get('code')} {e.get('message', '')}"
        if "errors" in parsed:                      # GraphQL envelope
            return parsed["errors"][0].get("message", "")
    return None


def section(title):
    print(f"\n{'=' * 78}\n{title}\n{'-' * 78}")


def probe_liveness():
    section("1. Endpoint liveness + classification")
    st, p, txt = rpc("sui_getLatestCheckpointSequenceNumber", [], FULLNODE_RPC)
    print(f"  Mysten fullnode JSON-RPC  http={st}  {_err(p) or txt}")

    st, p, txt = gql("{ chainIdentifier checkpoint { sequenceNumber } }")
    tip = None
    if isinstance(p, dict) and p.get("data"):
        tip = int(p["data"]["checkpoint"]["sequenceNumber"])
        print(f"  Mysten GraphQL            http={st}  ALIVE  tip_checkpoint={tip:,}")
    else:
        print(f"  Mysten GraphQL            http={st}  {_err(p) or txt}")

    st, p, txt = gql("{ chainIdentifier }", url=GRAPHQL_ALT)
    print(f"  mystenlabs.com/graphql    http={st}  {_err(p) or txt or 'ALIVE'}")

    for name, url in THIRD_PARTY_RPC.items():
        st, p, txt = rpc("sui_getLatestCheckpointSequenceNumber", [], url)
        res = p.get("result") if isinstance(p, dict) else None
        print(f"  {name:20}  http={st}  "
              f"{('checkpoint=' + res) if res else (_err(p) or txt)}")
    return tip


def probe_graphql_schema():
    section("2. GraphQL EventFilter + events() args (INTROSPECTED, not remembered)")
    _, p, _ = gql('{ __type(name:"EventFilter"){ inputFields{ name '
                  'type{ name } } } }')
    fields = p["data"]["__type"]["inputFields"]
    print("  EventFilter input fields:")
    for f in fields:
        print(f"    {f['name']:16} :: {f['type']['name']}")
    checkpoint_filters = [f["name"] for f in fields if "heckpoint" in f["name"]]
    print(f"  -> checkpoint-range filters present: {checkpoint_filters or 'NONE'}")

    _, p, _ = gql('{ __type(name:"Query"){ fields{ name args{ name '
                  'type{ name ofType{ name } } } } } }')
    for fld in p["data"]["__type"]["fields"]:
        if fld["name"] == "events":
            args = [(a["name"], a["type"].get("name")
                     or (a["type"].get("ofType") or {}).get("name"))
                    for a in fld["args"]]
            print(f"  events() args: {args}")


def probe_page_cap():
    section("3. Page-size cap (first:51) — a span-INDEPENDENT known constant")
    _, p, _ = gql("{ events(first:51){ pageInfo{hasNextPage} } }")
    print(f"  events(first:51) -> {_err(p)}")
    _, p, _ = gql("{ events(first:50){ pageInfo{hasNextPage} nodes{timestamp} } }")
    e = p["data"]["events"]
    print(f"  events(first:50) accepted: nodes={len(e['nodes'])} "
          f"hasNextPage={e['pageInfo']['hasNextPage']}")


def probe_widening_range(tip):
    section("4. THE DECISIVE TEST: a widening checkpoint range — does it fail?")
    if tip is None:
        print("  (no tip checkpoint — GraphQL unreachable, skipping)")
        return
    print("  afterCheckpoint = tip-width, beforeCheckpoint = tip, first:50\n")
    print(f"  {'width':>12}  {'secs':>5}  result")
    for width in (1, 10, 100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000):
        after, before = tip - width, tip
        t0 = time.time()
        _, p, txt = gql(f"{{ events(first:50, filter:{{afterCheckpoint:{after}, "
                        f"beforeCheckpoint:{before}}}){{ pageInfo{{hasNextPage}} "
                        f"nodes{{timestamp}} }} }}")
        dt = time.time() - t0
        if _err(p):
            outcome = f"ERROR {_err(p)}"
        else:
            e = p["data"]["events"]
            outcome = (f"nodes={len(e['nodes'])} "
                       f"hasNextPage={e['pageInfo']['hasNextPage']}")
        print(f"  {width:>12,}  {dt:>5.1f}  {outcome}")
    print("\n  If every width returns 50 nodes with no failure, the RANGE does not bind —")
    print("  the page size does, and it is span-INDEPENDENT. There is no bracket to find.")


def probe_scan_budget(tip):
    section("5. Scan budget (partial page + hasNextPage, not a range failure)")
    _, p, _ = gql("{ events(first:50){ pageInfo{hasNextPage} nodes{timestamp} } }")
    e = p["data"]["events"]
    print(f"  no filter, first:50            -> nodes={len(e['nodes'])} "
          f"hasNextPage={e['pageInfo']['hasNextPage']}  (forward from genesis)")
    _, p, _ = gql("{ events(first:50, filter:{afterCheckpoint:1}){ "
                  "pageInfo{hasNextPage} nodes{timestamp} } }")
    e = p["data"]["events"]
    print(f"  afterCheckpoint:1, first:50    -> nodes={len(e['nodes'])} "
          f"hasNextPage={e['pageInfo']['hasNextPage']}")
    _, p, _ = gql("{ events(last:50){ pageInfo{hasPreviousPage hasNextPage} "
                  "nodes{timestamp} } }")
    e = p["data"]["events"]
    print(f"  last:50 (from tip backward)    -> nodes={len(e['nodes'])} "
          f"pageInfo={e['pageInfo']}")
    print("\n  Zero nodes + hasNextPage:true is a SCAN BUDGET exhausted before a match —")
    print("  span-independent (fixed budget per request), paged through with cursors.")


def probe_jsonrpc_filters():
    section("6. JSON-RPC EventFilter: is there a checkpoint range? (only TimeRange)")
    _, p, _ = rpc("suix_queryEvents", [{"afterCheckpoint": 1}, None, 3, False],
                  THIRD_PARTY_RPC["publicnode"])
    print(f"  publicnode {{afterCheckpoint}} -> {_err(p)}")
    _, p, _ = rpc("suix_queryEvents",
                  [{"TimeRange": {"startTime": "1746600000000",
                                  "endTime": "1746700000000"}}, None, 3, False],
                  THIRD_PARTY_RPC["publicnode"])
    ok = isinstance(p, dict) and p.get("result")
    print(f"  publicnode {{TimeRange}}       -> "
          f"{'accepted, ' + str(len(ok['data'])) + ' events' if ok else _err(p)}")


def probe_retention():
    section("7. Retention / index completeness on a third-party JSON-RPC (0x2::coin)")
    _, p, _ = rpc("suix_queryEvents",
                  [{"MoveModule": {"package": "0x2", "module": "coin"}}, None, 50, False],
                  THIRD_PARTY_RPC["publicnode"])
    r = p.get("result") if isinstance(p, dict) else None
    if not r:
        print(f"  {_err(p)}")
        return
    ts = sorted(int(e["timestampMs"]) for e in r["data"] if e.get("timestampMs"))
    span = ""
    if ts:
        fmt = lambda ms: time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))
        span = f"  oldest={fmt(ts[0])} newest={fmt(ts[-1])}"
    print(f"  0x2::coin events={len(r['data'])} hasNextPage={r['hasNextPage']}{span}")
    print("  0x2::coin on mainnet has vastly more than this — a partial/unreliable index,")
    print("  which is itself an advertised-vs-measured finding about the provider.")


def main():
    print("Sui feasibility spike — run date matters; results go stale (that is the point).")
    tip = probe_liveness()
    probe_graphql_schema()
    probe_page_cap()
    probe_widening_range(tip)
    probe_scan_budget(tip)
    probe_jsonrpc_filters()
    probe_retention()
    print("\nVerdict is written up in HANDOFF 'Sui feasibility (spike, 2026-09-27)'.")


if __name__ == "__main__":
    sys.exit(main())
