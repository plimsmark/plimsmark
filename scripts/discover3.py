"""Item 5d final: does JSON-RPC cursor-seeding (strategy 2) work?

Strategy 2 = start a descending suix_queryEvents from the event ID of the first
matching event after c_end, obtained from GraphQL. This is more precise than
strategy 3 (TimeRange + client-side type filter) because it filters by
MoveEventType server-side. We test whether a GraphQL-derived event id is a valid
JSON-RPC cursor on all 3 providers.

Run:  .venv/bin/python scripts/discover3.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, dump_rows  # noqa: E402

DATE = "2026-09-27"
FIX = HERE.parent / "fixtures"
Q2_TYPE = "0x55300367a2d40813727ccac4ecee977a39fb9cdb46f2e6b2c354b9798f5de2c0::event::PriceFeedUpdateEvent"

GQL_EVENTS = (
    "query($last:Int,$before:String,$filter:EventFilter){"
    "events(last:$last,before:$before,filter:$filter){"
    "pageInfo{hasPreviousPage startCursor} "
    "nodes{sequenceNumber timestamp transaction{digest} contents{type{repr}}}}}"
)


def main():
    live = Live()
    findings = {}

    # 1. Get a recent PriceFeedUpdateEvent id from GraphQL (newest matching).
    print("Fetching newest PriceFeedUpdateEvent from GraphQL as a seed cursor...")
    st, parsed, body, (ec, er) = live.gql(
        GQL_EVENTS, {"last": 5, "filter": {"type": Q2_TYPE}}, label="gql seed"
    )
    nodes = parsed["data"]["events"]["nodes"]
    seed_node = nodes[-1]  # newest
    seed = {"txDigest": seed_node["transaction"]["digest"], "eventSeq": str(seed_node["sequenceNumber"])}
    seed_ts = seed_node["timestamp"]
    print(f"  seed id={seed} ts={seed_ts}")
    findings["seed"] = {"id": seed, "ts": seed_ts}

    # 2. Use that GraphQL id as a JSON-RPC cursor with MoveEventType descending.
    print("\nStrategy 2: seed JSON-RPC descending scan from the GraphQL event id")
    strat2 = {}
    for name in ("publicnode", "blockvision", "rpcpool"):
        st, parsed, body, (ec, er) = live.rpc(
            name, "suix_queryEvents", [{"MoveEventType": Q2_TYPE}, seed, 10, True]
        )
        if parsed and parsed.get("result") is not None:
            data = parsed["result"]["data"]
            # every returned event should be older than (or equal boundary to) the seed
            tss = [int(e["timestampMs"]) for e in data if e.get("timestampMs")]
            older = all(t <= int(datetime.fromisoformat(seed_ts.replace("Z", "+00:00")).timestamp() * 1000) for t in tss)
            types_ok = all(e.get("type") == Q2_TYPE for e in data)
            strat2[name] = {
                "accepted": True, "count": len(data),
                "all_type_match": types_ok, "all_older_than_seed": older,
                "hasNextPage": parsed["result"]["hasNextPage"],
            }
            print(f"  {name:16} accepted count={len(data)} type_ok={types_ok} older_than_seed={older}")
        else:
            strat2[name] = {"accepted": False, "error_class": ec, "error_reason": er}
            print(f"  {name:16} class={ec} {er}")
    findings["strategy2_cursor_seed"] = strat2

    dump_rows(live.rows, str(FIX / f"discovery3_{DATE}.rows.jsonl"))
    (FIX / f"discovery3_{DATE}.summary.json").write_text(json.dumps(findings, indent=2, default=str))
    print(f"\n  wrote {len(live.rows)} observation rows")
    live.close()


if __name__ == "__main__":
    main()
