"""Size Q1b (full history) and Q2 (recent window) so item 6 windows are sane.

Run:  .venv/bin/python scripts/measure.py
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live  # noqa: E402

ROOT = HERE.parent
cfg = json.loads((ROOT / "spike_config.json").read_text())
Q1B_TYPE = cfg["queries"]["Q1b"]["types"][0]
Q2_TYPE = cfg["queries"]["Q2"]["type"]

GQL = (
    "query($first:Int,$after:String,$filter:EventFilter){"
    "events(first:$first,after:$after,filter:$filter){"
    "pageInfo{hasNextPage endCursor} nodes{sequenceNumber transaction{digest}}}}"
)


def gql_count(live, filt, cap):
    cursor, n, pages = None, 0, 0
    while pages < cap:
        _, p, _, (ec, er) = live.gql(GQL, {"first": 50, "after": cursor, "filter": filt}, label="measure")
        if not (p and p.get("data", {}).get("events")):
            return n, pages, f"err:{ec}"
        e = p["data"]["events"]
        n += len(e["nodes"])
        pages += 1
        if not e["pageInfo"]["hasNextPage"]:
            return n, pages, "complete"
        cursor = e["pageInfo"]["endCursor"]
    return n, pages, "cap"


def main():
    live = Live()
    # Q1b full history via GraphQL type filter
    n, pages, status = gql_count(live, {"type": Q1B_TYPE}, cap=60)
    print(f"Q1b {Q1B_TYPE}\n   full history GraphQL: {n} events in {pages} pages ({status})")

    # Q2 recent window exact count via GraphQL checkpoint range
    w = next(w for w in cfg["queries"]["Q2"]["windows"] if w["label"] == "recent_1h")
    filt = {"type": Q2_TYPE, "afterCheckpoint": w["c_start"] - 1, "beforeCheckpoint": w["c_end"] + 1}
    n2, pages2, status2 = gql_count(live, filt, cap=200)
    print(f"Q2 {Q2_TYPE}\n   recent_1h 5-min window GraphQL: {n2} events in {pages2} pages ({status2})")
    live.close()


if __name__ == "__main__":
    main()
