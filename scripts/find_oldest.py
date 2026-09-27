"""Find the oldest checkpoint where Q2_TYPE exists, and rewrite the d365 window
in spike_config.json as an 'oldest_available' window (per item 5e: if the type
did not exist yet, use the oldest period where it does and say so).

Existence is probed with a BACKWARD scan (events(last:1, beforeCheckpoint:c+1)),
which fills immediately and avoids the forward scan-budget trap. present(c) is
monotonic: once the type exists at some checkpoint <= c it exists for all larger
c, so we binary-search the smallest such c.

Run:  .venv/bin/python scripts/find_oldest.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, dump_rows  # noqa: E402
from probe.windows import bisect_checkpoint  # noqa: E402

DATE = "2026-09-27"
ROOT = HERE.parent
FIX = ROOT / "fixtures"
WINDOW = 5 * 60 * 1000
Q2_TYPE = "0x55300367a2d40813727ccac4ecee977a39fb9cdb46f2e6b2c354b9798f5de2c0::event::PriceFeedUpdateEvent"


def iso_to_ms(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def main():
    live = Live()
    cfg = json.loads((ROOT / "spike_config.json").read_text())
    tip = cfg["tip_at_config"]["checkpoint"]

    memo_ts: dict[int, int] = {}

    def ts_of(c):
        if c not in memo_ts:
            _, p, _, _ = live.gql(
                "query($n:UInt53!){ checkpoint(sequenceNumber:$n){ timestamp } }",
                {"n": c}, label=f"cp {c}",
            )
            memo_ts[c] = iso_to_ms(p["data"]["checkpoint"]["timestamp"])
        return memo_ts[c]

    def present(c):
        """True if a Q2_TYPE event exists at checkpoint <= c (backward scan)."""
        _, p, _, (ec, er) = live.gql(
            "query($f:EventFilter){events(last:1,filter:$f){nodes{sequenceNumber}}}",
            {"f": {"type": Q2_TYPE, "beforeCheckpoint": c + 1}}, label=f"present {c}",
        )
        nodes = (p or {}).get("data", {}).get("events", {}).get("nodes")
        return bool(nodes)

    # binary search smallest c in [1, tip] with present(c)
    lo, hi = 1, tip
    if not present(hi):
        print("Q2 type not present even at tip?! aborting")
        return
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if present(mid):
            hi = mid
        else:
            lo = mid
    first_c = hi
    first_ts = ts_of(first_c)
    print(f"first appearance: checkpoint={first_c:,} ts={datetime.fromtimestamp(first_ts/1000, timezone.utc).isoformat()}")

    # oldest window starts at first_c, ends ~5 min later
    c_end = bisect_checkpoint(ts_of, first_ts + WINDOW, lo=first_c, hi=tip)
    oldest = {
        "label": "oldest_available",
        "note": "365d-ago window was empty (type not yet deployed); using the oldest 5-min window where the type exists",
        "c_start": first_c,
        "c_end": c_end,
        "ts_c_start_ms": ts_of(first_c),
        "ts_c_end_ms": ts_of(c_end),
        "ts_c_start": datetime.fromtimestamp(ts_of(first_c) / 1000, timezone.utc).isoformat(),
        "ts_c_end": datetime.fromtimestamp(ts_of(c_end) / 1000, timezone.utc).isoformat(),
        "q2_type_present": True,
    }
    print(f"  oldest window [{first_c:,}, {c_end:,}) {oldest['ts_c_start']} .. {oldest['ts_c_end']}")

    # replace the d365 window
    cfg["queries"]["Q2"]["windows"] = [
        w for w in cfg["queries"]["Q2"]["windows"] if w["label"] != "d365"
    ] + [oldest]
    (ROOT / "spike_config.json").write_text(json.dumps(cfg, indent=2))
    dump_rows(live.rows, str(FIX / f"find_oldest_{DATE}.rows.jsonl"))
    print(f"\nupdated spike_config.json; {len(live.rows)} rows")
    live.close()


if __name__ == "__main__":
    main()
