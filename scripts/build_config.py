"""Item 5e/5f: pin the query set + concrete Q2 windows into spike_config.json.

Windows are checkpoint ranges [c_start, c_end) placed by binary-searching the
checkpoint whose GraphQL timestamp floors a target wall-clock time. c_end sits
>= 1h before the run reference time so freshness lag cannot masquerade as
missing data.

Run:  .venv/bin/python scripts/build_config.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, PROVIDERS, VANTAGE, PROBE_COMMIT, dump_rows  # noqa: E402
from probe.windows import bisect_checkpoint  # noqa: E402

DATE = "2026-09-27"
FIX = HERE.parent / "fixtures"
ROOT = HERE.parent

Q1B_TYPE = "0x2::deny_list::PerTypeConfigCreated"
Q2_TYPE = "0x55300367a2d40813727ccac4ecee977a39fb9cdb46f2e6b2c354b9798f5de2c0::event::PriceFeedUpdateEvent"

HOUR = 3_600_000
DAY = 86_400_000
WINDOW = 5 * 60 * 1000  # 5 minutes


def iso_to_ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def main():
    live = Live()

    # tip checkpoint + timestamp
    st, parsed, body, _ = live.gql(
        "{ checkpoint { sequenceNumber timestamp } }", label="tip"
    )
    tip = int(parsed["data"]["checkpoint"]["sequenceNumber"])
    tip_ts = iso_to_ms(parsed["data"]["checkpoint"]["timestamp"])
    print(f"tip checkpoint={tip:,} ts={parsed['data']['checkpoint']['timestamp']}")

    # memoized live ts_of(checkpoint) -> ms
    memo: dict[int, int] = {tip: tip_ts}

    def ts_of(c: int) -> int:
        if c not in memo:
            _, p, _, (ec, er) = live.gql(
                "query($n:UInt53!){ checkpoint(sequenceNumber:$n){ timestamp } }",
                {"n": c},
                label=f"cp {c}",
            )
            memo[c] = iso_to_ms(p["data"]["checkpoint"]["timestamp"])
        return memo[c]

    def window_for(target_end_ms: int, label: str) -> dict:
        c_end = bisect_checkpoint(ts_of, target_end_ms, lo=1, hi=tip)
        c_start = bisect_checkpoint(ts_of, target_end_ms - WINDOW, lo=1, hi=tip)
        w = {
            "label": label,
            "target_end_ms": target_end_ms,
            "c_start": c_start,
            "c_end": c_end,
            "ts_c_start_ms": ts_of(c_start),
            "ts_c_end_ms": ts_of(c_end),
            "ts_c_start": datetime.fromtimestamp(ts_of(c_start) / 1000, timezone.utc).isoformat(),
            "ts_c_end": datetime.fromtimestamp(ts_of(c_end) / 1000, timezone.utc).isoformat(),
        }
        print(f"  {label:10} [{c_start:,}, {c_end:,}) {w['ts_c_start']} .. {w['ts_c_end']}")
        return w

    print("\nComputing Q2 windows (5 min each), c_end at ~1h / ~30d / ~365d before tip:")
    windows = [
        window_for(tip_ts - HOUR, "recent_1h"),
        window_for(tip_ts - 30 * DAY, "d30"),
        window_for(tip_ts - 365 * DAY, "d365"),
    ]

    # Does Q2_TYPE exist in each window? (a 0 here means "use oldest period" note)
    print("\nQ2 type existence per window (GraphQL type+checkpoint range):")
    for w in windows:
        _, p, _, (ec, er) = live.gql(
            "query($f:EventFilter){events(first:1,filter:$f){nodes{sequenceNumber}}}",
            {"f": {"type": Q2_TYPE, "afterCheckpoint": w["c_start"] - 1, "beforeCheckpoint": w["c_end"] + 1}},
            label=f"exist {w['label']}",
        )
        has = bool(p and p.get("data", {}).get("events", {}).get("nodes"))
        w["q2_type_present"] = has
        print(f"  {w['label']:10} present={has}" + ("" if p else f" class={ec} {er}"))

    config = {
        "date": DATE,
        "vantage": VANTAGE,
        "probe_commit": PROBE_COMMIT,
        "tip_at_config": {"checkpoint": tip, "ts_ms": tip_ts},
        "providers": {k: {"endpoint": v[0], "paradigm": v[1]} for k, v in PROVIDERS.items()},
        "jsonrpc_page_size": 50,
        "identity": {
            "jsonrpc": "(txDigest, eventSeq)",
            "graphql": "(transaction.digest, sequenceNumber)",
            "equivalent": True,
            "note": "exact match; GraphQL sequenceNumber == JSON-RPC eventSeq, transaction.digest == txDigest",
        },
        "comparable_predicate": {
            "use": "MoveEventType (JSON-RPC) == type with fully-qualified type name (GraphQL)",
            "not_comparable": "JSON-RPC MoveModule (called module) != GraphQL module (emitting module)",
            "evidence": "MoveModule 0x2::coin returns 0x2::deny_list::PerTypeConfigCreated events (deny_list-typed, coin-called); GraphQL module=0x2::coin returns a different set.",
        },
        "boundary_guard": "exclude events with ts == ts(c_start) or ts == ts(c_end) on all providers",
        "queries": {
            "Q1": {
                "description": "JSON-RPC MoveModule 0x2::coin, full history",
                "kind": "move_module",
                "filter": {"MoveModule": {"package": "0x2", "module": "coin"}},
                "providers": ["publicnode", "blockvision", "rpcpool"],
                "graphql": "not_comparable",
                "graphql_reason": "MoveModule (called module) has no established GraphQL equivalent; module filter differs in meaning.",
            },
            "Q1b": {
                "description": "Event types from Q1's results, each as MoveEventType, full history, all 4 providers",
                "kind": "move_event_type_full_history",
                "types": [Q1B_TYPE],
                "providers": ["publicnode", "blockvision", "rpcpool", "mysten_graphql"],
                "comparable": True,
                "note": "GraphQL leg uses type=<FQ type name>; identity equivalent. If a type caps, move to Q2 window scheme.",
            },
            "Q2": {
                "description": "One high-volume MoveEventType over three 5-min windows",
                "kind": "move_event_type_window",
                "type": Q2_TYPE,
                "type_source": "most frequent MoveEventType in newest ~200 tip events accepted by all 3 JSON-RPC providers (Pyth PriceFeedUpdateEvent)",
                "providers": ["publicnode", "blockvision", "rpcpool", "mysten_graphql"],
                "windows": windows,
                "access_strategy": {
                    "primary": "strategy2_cursor_seed",
                    "primary_detail": "seed JSON-RPC descending suix_queryEvents {MoveEventType} from the GraphQL event id at/after c_end; paginate until ts < ts(c_start); accepted on all 3 JSON-RPC providers.",
                    "fallback": "strategy3_timerange",
                    "fallback_detail": "TimeRange alone (accepted on all 3), type filtered client-side.",
                    "rejected": "strategy1_compound All[MoveEventType,TimeRange] -> definitive Invalid params on all 3.",
                },
            },
        },
        "freshness": {"samples": 3, "interval_s": 20},
        "run": {"page_cap": 400, "request_cap": 1500, "byte_cap_bytes": 8 * 1024 * 1024, "retries": 3},
    }

    (ROOT / "spike_config.json").write_text(json.dumps(config, indent=2))
    dump_rows(live.rows, str(FIX / f"build_config_{DATE}.rows.jsonl"))
    print(f"\nwrote spike_config.json and {len(live.rows)} observation rows")
    live.close()


if __name__ == "__main__":
    main()
