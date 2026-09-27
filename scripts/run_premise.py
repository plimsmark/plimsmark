"""Item 6/7: execute the pinned spike_config against all providers.

Usage:  .venv/bin/python scripts/run_premise.py run1
        .venv/bin/python scripts/run_premise.py run2

Writes fixtures/premise_<date>_<run>.jsonl.gz (newline-delimited records:
meta / observation / result / comparison / freshness) plus gzipped raw bodies
under fixtures/raw/<date>_<run>/. Each JSON-RPC query runs TWICE per provider
for self-consistency; a provider that disagrees with itself is flagged and
excluded from that query's cross-provider comparison.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import RecordingTransport, PROVIDERS, UA, VANTAGE, PROBE_COMMIT  # noqa: E402
from probe.clients import JsonRpcClient, GraphQlClient, iso_to_ms, _WINDOW_QUERY  # noqa: E402
from probe.compare import compare, apply_boundary_guard  # noqa: E402
from probe.model import QueryResult  # noqa: E402

ROOT = HERE.parent
FIX = ROOT / "fixtures"
DATE = "2026-09-27"
JSONRPC = ["publicnode", "blockvision", "rpcpool"]


def gql_id_of(node):
    return (node["transaction"]["digest"], int(node["sequenceNumber"]))


def qr_to_dict(qr: QueryResult, pass_label=None):
    return {
        "kind": "result", "pass": pass_label, "provider": qr.provider,
        "status": qr.status, "completeness": qr.completeness,
        "ids": sorted(list(qr.ids)), "error_class": qr.error_class,
        "error_reason": qr.error_reason,
    }


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "run1"
    run_id = f"{DATE}_{run}"
    cfg = json.loads((ROOT / "spike_config.json").read_text())
    Q1_FILTER = cfg["queries"]["Q1"]["filter"]
    Q1B_TYPE = cfg["queries"]["Q1b"]["types"][0]
    Q2_TYPE = cfg["queries"]["Q2"]["type"]
    windows = cfg["queries"]["Q2"]["windows"]

    transport = RecordingTransport(run_id, str(FIX / "raw"))
    jr = {p: JsonRpcClient(transport, PROVIDERS[p][0], p) for p in JSONRPC}
    gq = GraphQlClient(transport, PROVIDERS["mysten_graphql"][0], "mysten_graphql",
                       id_of=gql_id_of, events_query=_WINDOW_QUERY)

    records = []
    started = datetime.now(timezone.utc).isoformat()

    # ---- Q1: MoveModule 0x2::coin, JSON-RPC only, twice each; GraphQL not_comparable ----
    print("Q1 MoveModule 0x2::coin (JSON-RPC x2 each; GraphQL not_comparable)")
    q1 = {}
    for p in JSONRPC:
        a = jr[p].query_events(Q1_FILTER)
        b = jr[p].query_events(Q1_FILTER)
        q1[p] = (a, b)
        records += [{"query": "Q1", **qr_to_dict(a, "a")}, {"query": "Q1", **qr_to_dict(b, "b")}]
        print(f"  {p:16} a={a.status}/{a.completeness} b={b.status}/{b.completeness}")
    _record_comparison(records, "Q1", q1, comparable=False, gql=None)

    # ---- Q1b: MoveEventType deny_list type, full history, all 4; JSON-RPC x2 ----
    print(f"Q1b MoveEventType {Q1B_TYPE} (full history, all 4)")
    q1b = {}
    for p in JSONRPC:
        a = jr[p].query_events({"MoveEventType": Q1B_TYPE})
        b = jr[p].query_events({"MoveEventType": Q1B_TYPE})
        q1b[p] = (a, b)
        records += [{"query": "Q1b", **qr_to_dict(a, "a")}, {"query": "Q1b", **qr_to_dict(b, "b")}]
        print(f"  {p:16} a={a.status}/{a.completeness} b={b.status}/{b.completeness}")
    g = gq.query_events({"type": Q1B_TYPE})
    records.append({"query": "Q1b", **qr_to_dict(g, "single")})
    print(f"  {'mysten_graphql':16} {g.status}/{g.completeness}")
    _record_comparison(records, "Q1b", q1b, comparable=True, gql=g)

    # ---- Q2: windowed MoveEventType PriceFeedUpdateEvent, all 4 ----
    print(f"Q2 MoveEventType {Q2_TYPE[:40]}... over {len(windows)} windows")
    for w in windows:
        label = w["label"]
        cs, ce = w["c_start"], w["c_end"]
        ts_s, ts_e = w["ts_c_start_ms"], w["ts_c_end_ms"]
        # seed = first matching event AFTER c_end (oldest event with checkpoint > c_end)
        seed = _q2_seed(gq, Q2_TYPE, ce)
        q2 = {}
        for p in JSONRPC:
            ra = _q2_jsonrpc(jr[p], Q2_TYPE, seed, ts_s, ts_e, p)
            rb = _q2_jsonrpc(jr[p], Q2_TYPE, seed, ts_s, ts_e, p)
            q2[p] = (ra, rb)
            records += [{"query": f"Q2:{label}", **qr_to_dict(ra, "a")},
                        {"query": f"Q2:{label}", **qr_to_dict(rb, "b")}]
            print(f"  [{label}] {p:16} a={ra.status}/{ra.completeness} b={rb.status}/{rb.completeness}")
        # GraphQL leg: checkpoint-bounded window
        gfilt = {"type": Q2_TYPE, "afterCheckpoint": cs - 1, "beforeCheckpoint": ce}
        gevents, gterm = gq.collect_window(gfilt)
        gres = _finish_window(gevents, gterm, ts_s, ts_e, "mysten_graphql")
        records.append({"query": f"Q2:{label}", **qr_to_dict(gres, "single"),
                        "seed": seed, "window": {"c_start": cs, "c_end": ce}})
        print(f"  [{label}] {'mysten_graphql':16} {gres.status}/{gres.completeness}")
        _record_comparison(records, f"Q2:{label}", q2, comparable=True, gql=gres)

    # ---- F: freshness, 3 samples ~20s apart ----
    print("F freshness (3 samples ~20s apart)")
    for s in range(cfg["freshness"]["samples"]):
        sample = _freshness_sample(jr, gq, Q2_TYPE, s)
        records.append({"kind": "freshness", "sample": s, **sample})
        print(f"  sample {s}: " + ", ".join(
            f"{p}=cp{v.get('checkpoint')}/lag{v.get('index_lag_ms')}ms" for p, v in sample["providers"].items()))
        if s < cfg["freshness"]["samples"] - 1:
            time.sleep(cfg["freshness"]["interval_s"])

    ended = datetime.now(timezone.utc).isoformat()

    # ---- assemble output ----
    out = FIX / f"premise_{DATE}_{run}.jsonl.gz"
    with gzip.open(out, "wt") as f:
        f.write(json.dumps({
            "kind": "meta", "run_id": run_id, "date": DATE, "started": started,
            "ended": ended, "user_agent": UA, "vantage": VANTAGE,
            "probe_commit": PROBE_COMMIT, "config_tip": cfg["tip_at_config"],
            "n_observations": len(transport.rows),
        }) + "\n")
        for row in transport.rows:
            f.write(json.dumps({"kind": "observation", **asdict(row)}) + "\n")
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")

    transport.close()
    print(f"\nwrote {out} ({len(transport.rows)} obs, {len(records)} records)")


def _self_consistent(a: QueryResult, b: QueryResult) -> bool:
    return a.status == "complete" and b.status == "complete" and a.ids == b.ids


def _record_comparison(records, query, per_provider, comparable, gql):
    """Build a cross-provider comparison from pass-a of self-consistent providers."""
    sc = {}
    complete_a = []
    for p, (a, b) in per_provider.items():
        consistent = _self_consistent(a, b)
        sc[p] = {
            "self_consistent": consistent,
            "a": {"status": a.status, "completeness": a.completeness},
            "b": {"status": b.status, "completeness": b.completeness},
        }
        # only self-consistent, complete providers enter cross comparison
        if consistent:
            complete_a.append(a)
        elif a.status != "complete" or b.status != "complete":
            complete_a.append(a)  # non-complete carried as unknown by compare()
        else:
            # complete but self-INCONSISTENT -> block: carry as incomplete/unknown
            complete_a.append(QueryResult.incomplete(p, "self_inconsistent",
                              f"pass a/b id sets differ ({a.completeness} vs {b.completeness})"))
    if gql is not None:
        complete_a.append(gql)
    report = compare(complete_a, comparable=comparable)
    records.append({
        "kind": "comparison", "query": query, "verdict": report.verdict,
        "comparable": comparable, "self_consistency": sc,
        "union_size": report.union_size,
        "pairwise_jaccard": {f"{k[0]}|{k[1]}": v for k, v in report.pairwise_jaccard.items()},
        "providers": [
            {"provider": pc.provider, "status": pc.status, "count": pc.count,
             "missing_vs_union": sorted(list(pc.missing_vs_union)) if pc.missing_vs_union else pc.missing_vs_union,
             "extra_vs_others": sorted(list(pc.extra_vs_others)) if pc.extra_vs_others else pc.extra_vs_others,
             "error_class": pc.error_class}
            for pc in report.providers
        ],
    })


def _q2_seed(gq, q2_type, c_end):
    """First matching event AFTER c_end (oldest event with checkpoint > c_end)."""
    outcome = gq._call(
        "query($f:EventFilter){events(first:1,filter:$f){nodes{sequenceNumber transaction{digest}}}}",
        {"f": {"type": q2_type, "afterCheckpoint": c_end}},
    )
    try:
        nodes = outcome.parsed()["data"]["events"]["nodes"]
    except Exception:
        return None
    if not nodes:
        return None
    n = nodes[0]
    return {"txDigest": n["transaction"]["digest"], "eventSeq": str(n["sequenceNumber"])}


def _q2_jsonrpc(client, q2_type, seed, ts_s, ts_e, provider):
    events, terminal = client.collect_window({"MoveEventType": q2_type}, seed, ts_s, ts_e)
    return _finish_window(events, terminal, ts_s, ts_e, provider)


def _finish_window(events, terminal, ts_s, ts_e, provider):
    kept, excluded = apply_boundary_guard(events, ts_s, ts_e)
    if terminal is None:
        qr = QueryResult.complete(provider, [e["id"] for e in kept])
        return qr
    return QueryResult.incomplete(provider, terminal, f"window not cleanly covered ({terminal})")


def _freshness_sample(jr, gq, q2_type, s):
    max_cp = 0
    prov = {}
    for p, client in jr.items():
        wall_before = datetime.now(timezone.utc).timestamp() * 1000
        try:
            cp = client.latest_checkpoint()
        except Exception as e:
            prov[p] = {"error": str(e)}
            continue
        st, parsed, *_ = _rpc_newest(client, q2_type)
        wall = datetime.now(timezone.utc).timestamp() * 1000
        newest_ts = parsed
        prov[p] = {"checkpoint": cp, "newest_event_ts_ms": newest_ts,
                   "index_lag_ms": int(wall - newest_ts) if newest_ts else None}
        max_cp = max(max_cp, cp)
    # graphql
    try:
        gcp = gq.latest_checkpoint()
        outcome = gq._call("query($f:EventFilter){events(last:1,filter:$f){nodes{timestamp}}}",
                           {"f": {"type": q2_type}})
        nodes = outcome.parsed()["data"]["events"]["nodes"]
        gts = iso_to_ms(nodes[0]["timestamp"]) if nodes else None
        wall = datetime.now(timezone.utc).timestamp() * 1000
        prov["mysten_graphql"] = {"checkpoint": gcp, "newest_event_ts_ms": gts,
                                  "index_lag_ms": int(wall - gts) if gts else None}
        max_cp = max(max_cp, gcp)
    except Exception as e:
        prov["mysten_graphql"] = {"error": str(e)}
    for p, v in prov.items():
        if "checkpoint" in v:
            v["checkpoint_lag"] = max_cp - v["checkpoint"]
    return {"max_checkpoint": max_cp, "providers": prov}


def _rpc_newest(client, q2_type):
    """Newest event timestampMs for the type on a JSON-RPC provider (limit 1 desc)."""
    outcome = client._call("suix_queryEvents", [{"MoveEventType": q2_type}, None, 1, True])
    try:
        data = outcome.parsed()["result"]["data"]
        ts = int(data[0]["timestampMs"]) if data else None
        return outcome.status_code, ts
    except Exception:
        return outcome.status_code, None


if __name__ == "__main__":
    main()
