"""Item 8: timestamp ground truth.

Re-derives the edge set live from the run2 fixture (Q2 recent_1h events present on
GraphQL but outside the JSON-RPC ts-window) plus the oldest_available event, then
for each tx collects the event timestamp, the containing checkpoint (seq +
timestamp), and that checkpoint's own timestamp fetched independently by sequence
number, on BOTH paradigms. Concludes which paradigm's event timestamp equals the
containing checkpoint's timestamp, and whether both agree on WHICH checkpoint.

Run:  .venv/bin/python scripts/ground_truth.py
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, PROVIDERS, UA, VANTAGE, PROBE_COMMIT, dump_rows  # noqa: E402

ROOT = HERE.parent
FIX = ROOT / "fixtures"
DATE = "2026-09-27"
JSONRPC = ["publicnode", "blockvision", "rpcpool"]


def iso_to_ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def derive_edge_txs():
    recs = [json.loads(l) for l in gzip.open(FIX / f"premise_{DATE}_run2.jsonl.gz", "rt")]
    byq = {}
    for r in recs:
        if r.get("kind") == "result":
            byq.setdefault(r["query"], {})[(r["provider"], r["pass"])] = r
    rec = byq["Q2:recent_1h"]
    gql = {tuple(i) for i in rec[("mysten_graphql", "single")]["ids"]}
    jr = set()
    for p in JSONRPC:
        jr |= {tuple(i) for i in rec[(p, "a")]["ids"]}
    edge = gql - jr
    txs = sorted({d for d, _s in edge})
    # oldest_available event tx
    old = {tuple(i) for i in byq["Q2:oldest_available"][("publicnode", "a")]["ids"]}
    old_txs = sorted({d for d, _s in old})
    return txs, old_txs


GQL_EFFECTS = (
    "query($d:String!){ transactionEffects(digest:$d){ timestamp "
    "checkpoint{ sequenceNumber timestamp } "
    "events{ nodes{ sequenceNumber timestamp } } } }"
)
GQL_CHECKPOINT = "query($n:UInt53!){ checkpoint(sequenceNumber:$n){ sequenceNumber timestamp } }"


def collect(live, tx):
    row = {"tx": tx, "graphql": {}, "jsonrpc": {}}
    # --- GraphQL ---
    _, p, _, (ec, er) = live.gql(GQL_EFFECTS, {"d": tx}, label="gql effects")
    eff = (p or {}).get("data", {}).get("transactionEffects") if p else None
    if eff:
        cp = eff.get("checkpoint") or {}
        ev0 = (eff.get("events") or {}).get("nodes") or []
        ev_ts = ev0[0]["timestamp"] if ev0 else None
        row["graphql"] = {
            "checkpoint_seq": cp.get("sequenceNumber"),
            "checkpoint_ts": cp.get("timestamp"),
            "effects_ts": eff.get("timestamp"),
            "event_ts": ev_ts,
            "event_ts_ms": iso_to_ms(ev_ts) if ev_ts else None,
        }
        cp_seq = cp.get("sequenceNumber")
        if cp_seq is not None:
            _, pc, _, _ = live.gql(GQL_CHECKPOINT, {"n": cp_seq}, label="gql cp")
            cpn = (pc or {}).get("data", {}).get("checkpoint") if pc else None
            row["graphql"]["checkpoint_ts_by_seq"] = cpn.get("timestamp") if cpn else None
    else:
        row["graphql"] = {"error_class": ec, "error_reason": er}

    # --- each JSON-RPC provider ---
    for name in JSONRPC:
        d = {}
        _, p, _, (ec, er) = live.rpc(name, "suix_queryEvents", [{"Transaction": tx}, None, 50, False])
        res = (p or {}).get("result") if p else None
        if res and res.get("data"):
            e0 = res["data"][0]
            d["event_ts_ms"] = int(e0["timestampMs"]) if e0.get("timestampMs") else None
        else:
            d["event_error"] = f"{ec}: {er}"
        _, p, _, (ec, er) = live.rpc(name, "sui_getTransactionBlock", [tx, {"showEvents": False}])
        res = (p or {}).get("result") if p else None
        if res:
            d["tx_ts_ms"] = int(res["timestampMs"]) if res.get("timestampMs") else None
            d["checkpoint_seq"] = int(res["checkpoint"]) if res.get("checkpoint") else None
        else:
            d["txblock_error"] = f"{ec}: {er}"
        cps = d.get("checkpoint_seq")
        if cps is not None:
            _, p, _, (ec, er) = live.rpc(name, "sui_getCheckpoint", [str(cps)])
            res = (p or {}).get("result") if p else None
            d["checkpoint_ts_ms"] = int(res["timestampMs"]) if res and res.get("timestampMs") else None
        row["jsonrpc"][name] = d
    return row


def conclude(row):
    g = row["graphql"]
    cp_ts_ms = iso_to_ms(g["checkpoint_ts"]) if g.get("checkpoint_ts") else None
    cp_seq = g.get("checkpoint_seq")
    # checkpoint agreement across providers
    jr_cps = [row["jsonrpc"][p].get("checkpoint_seq") for p in JSONRPC]
    checkpoint_agree = all(c == cp_seq for c in jr_cps if c is not None) and cp_seq is not None
    # which event-ts equals the containing checkpoint ts
    gql_event_matches = g.get("event_ts_ms") == cp_ts_ms
    jr_event_matches = {p: (row["jsonrpc"][p].get("event_ts_ms") == cp_ts_ms) for p in JSONRPC}
    jr_tx_matches = {p: (row["jsonrpc"][p].get("tx_ts_ms") == cp_ts_ms) for p in JSONRPC}
    return {
        "checkpoint_seq": cp_seq, "checkpoint_ts_ms": cp_ts_ms,
        "checkpoint_agree": checkpoint_agree,
        "gql_event_matches_checkpoint": gql_event_matches,
        "jsonrpc_event_matches_checkpoint": jr_event_matches,
        "jsonrpc_txblock_matches_checkpoint": jr_tx_matches,
    }


def main():
    edge, old = derive_edge_txs()
    all_txs = edge + old
    print(f"edge txs (recent_1h): {len(edge)}; oldest txs: {len(old)}; total {len(all_txs)}")
    live = Live()
    rows = []
    for tx in all_txs:
        r = collect(live, tx)
        r["conclusion"] = conclude(r)
        rows.append(r)
        c = r["conclusion"]
        print(f"  {tx[:12]}.. cp={c['checkpoint_seq']} agree={c['checkpoint_agree']} "
              f"gql_ev==cp:{c['gql_event_matches_checkpoint']} "
              f"jr_ev==cp:{[c['jsonrpc_event_matches_checkpoint'][p] for p in JSONRPC]} "
              f"jr_tx==cp:{[c['jsonrpc_txblock_matches_checkpoint'][p] for p in JSONRPC]}")
    dump_rows(live.rows, str(FIX / f"ground_truth_{DATE}.rows.jsonl"))
    (FIX / f"ground_truth_{DATE}.data.json").write_text(json.dumps(
        {"edge_txs": edge, "oldest_txs": old, "rows": rows,
         "meta": {"ua": UA, "vantage": VANTAGE, "probe_commit": PROBE_COMMIT}}, indent=2, default=str))
    live.close()
    print(f"wrote ground_truth_{DATE}.data.json ({len(live.rows)} obs)")


if __name__ == "__main__":
    main()
