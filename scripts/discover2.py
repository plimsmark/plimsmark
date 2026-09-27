"""Item 5c(final)/5d/5e groundwork: comparability evidence, Q1b volume, Q2 tip
sampling, and JSON-RPC window-access strategy.

Run:  .venv/bin/python scripts/discover2.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, dump_rows  # noqa: E402

DATE = "2026-09-27"
FIX = HERE.parent / "fixtures"

Q1B_TYPE = "0x2::deny_list::PerTypeConfigCreated"

# GraphQL events query pulling the identity + type
GQL_EVENTS = (
    "query($first:Int,$last:Int,$after:String,$before:String,$filter:EventFilter){"
    "events(first:$first,last:$last,after:$after,before:$before,filter:$filter){"
    "pageInfo{hasNextPage hasPreviousPage startCursor endCursor} "
    "nodes{sequenceNumber timestamp transaction{digest} contents{type{repr}}}}}"
)


def section(t):
    print(f"\n{'='*78}\n{t}\n{'-'*78}")


def iso_to_ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def main():
    live = Live()
    findings = {}

    # === B. Q1b comparability: MoveEventType == GraphQL type on the deny_list type ===
    section(f"5c. Q1b type {Q1B_TYPE} — MoveEventType vs GraphQL type (identity match)")
    q1b = {}
    for name in ("publicnode", "blockvision", "rpcpool"):
        st, parsed, body, (ec, er) = live.rpc(
            name, "suix_queryEvents", [{"MoveEventType": Q1B_TYPE}, None, 50, False]
        )
        if parsed and parsed.get("result"):
            r = parsed["result"]
            ids = [(e["id"]["txDigest"], int(e["id"]["eventSeq"])) for e in r["data"]]
            q1b[name] = {"count": len(ids), "hasNextPage": r["hasNextPage"], "ids": ids}
            print(f"  {name:16} count={len(ids)} hasNextPage={r['hasNextPage']}")
        else:
            q1b[name] = {"error_class": ec, "error_reason": er}
            print(f"  {name:16} class={ec} {er}")

    st, parsed, body, (ec, er) = live.gql(
        GQL_EVENTS, {"first": 50, "filter": {"type": Q1B_TYPE}}, label="gql q1b type"
    )
    if parsed and parsed.get("data", {}).get("events"):
        e = parsed["data"]["events"]
        gids = [(n["transaction"]["digest"], int(n["sequenceNumber"])) for n in e["nodes"]]
        q1b["mysten_graphql"] = {
            "count": len(gids),
            "hasNextPage": e["pageInfo"]["hasNextPage"],
            "ids": gids,
        }
        print(f"  {'mysten_graphql':16} count={len(gids)} hasNextPage={e['pageInfo']['hasNextPage']}")
    else:
        q1b["mysten_graphql"] = {"error_class": ec, "error_reason": er}
        print(f"  mysten_graphql   class={ec} {er}")
    findings["q1b"] = q1b

    # === C. Q2 tip sampling: newest ~200 events on GraphQL, tally types ===
    section("5e. Q2 tip sampling — most frequent MoveEventType in newest ~200 events")
    counter = Counter()
    before = None
    tip_ts = None
    for _ in range(4):
        st, parsed, body, (ec, er) = live.gql(
            GQL_EVENTS, {"last": 50, "before": before}, label="gql tip sample"
        )
        if not (parsed and parsed.get("data", {}).get("events")):
            print(f"  sampling stopped: class={ec} {er}")
            break
        e = parsed["data"]["events"]
        for n in e["nodes"]:
            counter[n["contents"]["type"]["repr"]] += 1
            if tip_ts is None and n.get("timestamp"):
                tip_ts = n["timestamp"]
        if not e["pageInfo"]["hasPreviousPage"]:
            break
        before = e["pageInfo"]["startCursor"]
    top = counter.most_common(10)
    print(f"  sampled {sum(counter.values())} events, {len(counter)} distinct types; tip_ts={tip_ts}")
    for tp, n in top:
        print(f"    {n:4}  {tp}")
    findings["tip_sample"] = {"tip_ts": tip_ts, "top": top}

    # Verify the most frequent types are accepted as MoveEventType by all 3 JSON-RPC.
    section("5e. Q2 candidate acceptance as MoveEventType on all 3 JSON-RPC providers")
    q2_candidate = None
    for tp, _n in top:
        accepted = {}
        for name in ("publicnode", "blockvision", "rpcpool"):
            st, parsed, body, (ec, er) = live.rpc(
                name, "suix_queryEvents", [{"MoveEventType": tp}, None, 5, True]
            )
            ok = bool(parsed and parsed.get("result") is not None and ec is None)
            accepted[name] = {"ok": ok, "error_class": ec, "count": (len(parsed["result"]["data"]) if ok else None)}
        all_ok = all(v["ok"] for v in accepted.values())
        print(f"  {'ACCEPT' if all_ok else 'reject':7} {tp}  {[ (k,v['ok']) for k,v in accepted.items()]}")
        if all_ok and q2_candidate is None:
            q2_candidate = tp
    findings["q2_candidate"] = q2_candidate
    print(f"  -> Q2 candidate MoveEventType: {q2_candidate}")

    # === D. 5d window-access strategy: compound All[MoveEventType, TimeRange] ===
    section("5d. Window access strategy — compound All[MoveEventType, TimeRange]")
    # window: 60s ending ~1h before tip timestamp
    if tip_ts and q2_candidate:
        tip_ms = iso_to_ms(tip_ts)
        end_ms = tip_ms - 3600_000            # ~1h before tip
        start_ms = end_ms - 60_000            # 60s window
        strat = {}
        for name in ("publicnode", "blockvision", "rpcpool"):
            filt = {"All": [
                {"MoveEventType": q2_candidate},
                {"TimeRange": {"startTime": str(start_ms), "endTime": str(end_ms)}},
            ]}
            st, parsed, body, (ec, er) = live.rpc(name, "suix_queryEvents", [filt, None, 50, True])
            if parsed and parsed.get("result") is not None:
                r = parsed["result"]
                strat[name] = {"accepted": True, "count": len(r["data"]), "hasNextPage": r["hasNextPage"]}
                print(f"  {name:16} All[type,TimeRange] accepted count={len(r['data'])} hasNextPage={r['hasNextPage']}")
            else:
                strat[name] = {"accepted": False, "error_class": ec, "error_reason": er}
                print(f"  {name:16} All[type,TimeRange] class={ec} {er}")
        findings["window_strategy_compound"] = {"window_ms": [start_ms, end_ms], "result": strat}

        # Fallback probe: TimeRange alone (strategy 3) acceptance
        section("5d. Fallback — TimeRange alone (strategy 3) acceptance")
        for name in ("publicnode", "blockvision", "rpcpool"):
            filt = {"TimeRange": {"startTime": str(start_ms), "endTime": str(end_ms)}}
            st, parsed, body, (ec, er) = live.rpc(name, "suix_queryEvents", [filt, None, 50, True])
            if parsed and parsed.get("result") is not None:
                r = parsed["result"]
                print(f"  {name:16} TimeRange alone count={len(r['data'])} hasNextPage={r['hasNextPage']}")
            else:
                print(f"  {name:16} TimeRange alone class={ec} {er}")
    else:
        print("  (no tip_ts or q2_candidate — skipping window strategy)")

    dump_rows(live.rows, str(FIX / f"discovery2_{DATE}.rows.jsonl"))
    (FIX / f"discovery2_{DATE}.summary.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\n  wrote {len(live.rows)} observation rows")
    live.close()


if __name__ == "__main__":
    main()
