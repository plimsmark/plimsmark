"""Diagnose the recent_1h GraphQL(603) vs JSON-RPC(582) gap: are the differing
events at the window edges (a cross-paradigm windowing artifact) or in the
interior (a real index difference)? And are they truly absent from JSON-RPC?
"""
from __future__ import annotations
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import RecordingTransport, PROVIDERS  # noqa
from probe.clients import GraphQlClient, JsonRpcClient, _WINDOW_QUERY  # noqa
from probe.compare import apply_boundary_guard  # noqa

cfg = json.loads((HERE.parent / "spike_config.json").read_text())
Q2 = cfg["queries"]["Q2"]["type"]
w = next(x for x in cfg["queries"]["Q2"]["windows"] if x["label"] == "recent_1h")
cs, ce, ts_s, ts_e = w["c_start"], w["c_end"], w["ts_c_start_ms"], w["ts_c_end_ms"]
print(f"window checkpoints [{cs},{ce})  ts [{ts_s},{ts_e})  span={ts_e-ts_s}ms")

t = RecordingTransport("diag", str(HERE.parent / "fixtures" / "raw"))
gq = GraphQlClient(t, PROVIDERS["mysten_graphql"][0], "mysten_graphql",
                   id_of=lambda n: (n["transaction"]["digest"], int(n["sequenceNumber"])),
                   events_query=_WINDOW_QUERY)
pn = JsonRpcClient(t, PROVIDERS["publicnode"][0], "publicnode")

# GraphQL checkpoint-bounded window
gev, gterm = gq.collect_window({"type": Q2, "afterCheckpoint": cs - 1, "beforeCheckpoint": ce})
# JSON-RPC cursor-seeded ts window
oc = gq._call("query($f:EventFilter){events(first:1,filter:$f){nodes{sequenceNumber transaction{digest}}}}",
              {"f": {"type": Q2, "afterCheckpoint": ce}})
n = oc.parsed()["data"]["events"]["nodes"][0]
seed = {"txDigest": n["transaction"]["digest"], "eventSeq": str(n["sequenceNumber"])}
jev, jterm = pn.collect_window({"MoveEventType": Q2}, seed, ts_s, ts_e)

gkept, gx = apply_boundary_guard(gev, ts_s, ts_e)
jkept, jx = apply_boundary_guard(jev, ts_s, ts_e)
gids = {tuple(e["id"]) for e in gkept}
jids = {tuple(e["id"]) for e in jkept}
gts = {tuple(e["id"]): e["timestampMs"] for e in gkept}
jts = {tuple(e["id"]): e["timestampMs"] for e in jkept}
print(f"\nGraphQL kept={len(gids)} (raw {len(gev)}, boundary-excl {gx}, term={gterm})")
print(f"JSONRPC kept={len(jids)} (raw {len(jev)}, boundary-excl {jx}, term={jterm})")
print(f"GraphQL raw ts range: [{min(e['timestampMs'] for e in gev)}, {max(e['timestampMs'] for e in gev)}]")
print(f"JSONRPC raw ts range: [{min(e['timestampMs'] for e in jev)}, {max(e['timestampMs'] for e in jev)}]")

only_g = gids - jids
only_j = jids - gids
print(f"\nonly in GraphQL: {len(only_g)}   only in JSON-RPC: {len(only_j)}")

def place(ts):
    if ts <= ts_s: return f"<=start (+{ts-ts_s})"
    if ts >= ts_e: return f">=end ({ts-ts_e})"
    d_from_start = ts - ts_s; d_to_end = ts_e - ts
    edge = "EDGE" if min(d_from_start, d_to_end) < 2000 else "interior"
    return f"{edge} (+{d_from_start} from start, -{d_to_end} to end)"

print("\n-- events only in GraphQL (id -> gql ts, placement) --")
for i in sorted(only_g, key=lambda x: gts[x])[:30]:
    print(f"   {i[0][:12]}..:{i[1]}  ts={gts[i]}  {place(gts[i])}")
print("\n-- events only in JSON-RPC --")
for i in sorted(only_j, key=lambda x: jts[x])[:30]:
    print(f"   {i[0][:12]}..:{i[1]}  ts={jts[i]}  {place(jts[i])}")

# Are the GraphQL-only events truly absent from JSON-RPC's index, or just outside
# its ts-window? Look them up directly on publicnode by transaction.
print("\n-- verify a few GraphQL-only events exist on publicnode (by Transaction) --")
for i in sorted(only_g, key=lambda x: gts[x])[:5]:
    st, p, body, (ec, er) = None, None, None, (None, None)
    oc = t(PROVIDERS["publicnode"][0], {"jsonrpc":"2.0","id":1,"method":"suix_queryEvents",
          "params":[{"Transaction": i[0]}, None, 50, False]}, headers={})
    try:
        data = oc.parsed()["result"]["data"]
        match = [(e["id"]["eventSeq"], e.get("timestampMs")) for e in data if e.get("type")==Q2]
        print(f"   {i[0][:12]}..:{i[1]} -> publicnode has type events at seqs/ts {match}")
    except Exception as e:
        print(f"   {i[0][:12]}.. lookup err {e}")
t.close()
