"""Client + pagination tests, driven entirely by a fake transport fed recorded
responses. Covers the pagination edge cases called out in item 4:

  - fewer results than requested with hasNextPage true (normal, keep going)
  - GraphQL 0 nodes + hasNextPage true: continue while the cursor advances,
    else scan_budget -> incomplete
  - JSON-RPC page cap 400 and GraphQL request cap 1500 -> cap_reached, incomplete
  - byte cap while streaming -> cap_reached, incomplete
  - definitive filter refusal -> unsupported
"""

import json

import httpx
import pytest

from probe.clients import GraphQlClient, JsonRpcClient
from probe.transport import HttpOutcome


# --- fake transport + response builders ---

class FakeTransport:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.requests = []

    def __call__(self, url, payload, *, headers=None, byte_cap=None):
        self.requests.append(payload)
        if not self._outcomes:
            raise AssertionError("FakeTransport exhausted — client over-requested")
        return self._outcomes.pop(0)


def _ok(obj):
    body = json.dumps(obj).encode()
    return HttpOutcome(status_code=200, body=body, bytes_len=len(body))


def rpc_event(digest, seq, ts="1690000000000", type_="0x2::coin::CoinCreated"):
    return {
        "id": {"txDigest": digest, "eventSeq": str(seq)},
        "type": type_,
        "timestampMs": ts,
    }


def rpc_page(events, has_next, next_cursor=None):
    return _ok(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "data": events,
                "nextCursor": next_cursor,
                "hasNextPage": has_next,
            },
        }
    )


def gql_page(nodes, has_next, end_cursor):
    return _ok(
        {
            "data": {
                "events": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                }
            }
        }
    )


# GraphQL identity is pinned live in item 5; tests use an explicit extractor.
def gql_node(digest, seq):
    return {"transactionBlock": {"digest": digest}, "seq": seq}


def gql_id_of(node):
    return (node["transactionBlock"]["digest"], node["seq"])


# ============================ JSON-RPC ============================

def test_jsonrpc_single_page_complete():
    t = FakeTransport([rpc_page([rpc_event("0xA", 0), rpc_event("0xB", 0)], False)])
    c = JsonRpcClient(t, "http://x", "publicnode")
    r = c.query_events({"MoveModule": {"package": "0x2", "module": "coin"}})
    assert r.status == "complete"
    assert r.completeness == 2
    assert r.ids == frozenset([("0xA", 0), ("0xB", 0)])


def test_jsonrpc_multi_page_cursor_descending():
    cur = {"txDigest": "0xA", "eventSeq": "0"}
    t = FakeTransport(
        [
            rpc_page([rpc_event("0xA", 0)], True, next_cursor=cur),
            rpc_page([rpc_event("0xB", 0)], False),
        ]
    )
    c = JsonRpcClient(t, "http://x", "publicnode", page_size=50)
    r = c.query_events({"MoveEventType": "0x2::coin::CoinCreated"})
    assert r.status == "complete"
    assert r.ids == frozenset([("0xA", 0), ("0xB", 0)])
    # params = [filter, cursor, limit, descending] — descending True, page size 50
    first_params = t.requests[0]["params"]
    assert first_params[1] is None  # first cursor
    assert first_params[2] == 50
    assert first_params[3] is True  # descending order
    # second request seeds the returned cursor
    assert t.requests[1]["params"][1] == cur


def test_jsonrpc_fewer_than_requested_with_next_keeps_going():
    # 1 event on a page whose page_size is 50, hasNextPage true -> NOT the end.
    t = FakeTransport(
        [
            rpc_page([rpc_event("0xA", 0)], True, next_cursor={"txDigest": "0xA", "eventSeq": "0"}),
            rpc_page([rpc_event("0xB", 0)], False),
        ]
    )
    c = JsonRpcClient(t, "http://x", "publicnode", page_size=50)
    r = c.query_events({"MoveEventType": "T"})
    assert r.status == "complete"
    assert r.completeness == 2


def test_jsonrpc_page_cap_reached_is_incomplete():
    cur = {"txDigest": "0xA", "eventSeq": "0"}
    # every page says hasNextPage true; cap at 3 pages
    t = FakeTransport([rpc_page([rpc_event(f"0x{i}", 0)], True, cur) for i in range(3)])
    c = JsonRpcClient(t, "http://x", "publicnode", page_size=50, page_cap=3)
    r = c.query_events({"MoveEventType": "T"})
    assert r.status == "incomplete"
    assert r.error_class == "cap_reached"
    assert len(t.requests) == 3  # stopped exactly at the cap


def test_jsonrpc_definitive_filter_is_unsupported():
    err = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32602,
            "message": "Invalid params: unknown variant `afterCheckpoint`",
        },
    }
    t = FakeTransport([_ok(err)])
    c = JsonRpcClient(t, "http://x", "blockvision")
    r = c.query_events({"afterCheckpoint": 1})
    assert r.status == "unsupported"
    assert r.error_class == "definitive"
    assert "unknown variant" in r.error_reason


def test_jsonrpc_transient_is_incomplete():
    t = FakeTransport([HttpOutcome(status_code=None, body=None, error=httpx.ConnectError("refused"))])
    c = JsonRpcClient(t, "http://x", "rpcpool")
    r = c.query_events({"MoveEventType": "T"})
    assert r.status == "incomplete"
    assert r.error_class == "transient"


def test_jsonrpc_byte_cap_truncation_is_cap_reached():
    t = FakeTransport([HttpOutcome(status_code=200, body=b'{"trunca', truncated=True, bytes_len=8)])
    c = JsonRpcClient(t, "http://x", "publicnode")
    r = c.query_events({"MoveEventType": "T"})
    assert r.status == "incomplete"
    assert r.error_class == "cap_reached"


def test_jsonrpc_latest_checkpoint():
    t = FakeTransport([_ok({"jsonrpc": "2.0", "id": 1, "result": "327443667"})])
    c = JsonRpcClient(t, "http://x", "publicnode")
    assert c.latest_checkpoint() == 327443667


# ============================ GraphQL ============================

def test_graphql_multi_page_complete():
    t = FakeTransport(
        [
            gql_page([gql_node("0xA", 0)], True, "c1"),
            gql_page([gql_node("0xB", 0)], False, "c2"),
        ]
    )
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    r = g.query_events({"type": "0x2::coin::CoinCreated"})
    assert r.status == "complete"
    assert r.ids == frozenset([("0xA", 0), ("0xB", 0)])
    # second request seeds the endCursor as `after`
    assert t.requests[1]["variables"]["after"] == "c1"


def test_graphql_empty_page_with_advancing_cursor_survives():
    # 0 nodes + hasNextPage true, but the cursor advances -> keep going, then real data.
    t = FakeTransport(
        [
            gql_page([], True, "c1"),
            gql_page([gql_node("0xA", 0)], False, "c2"),
        ]
    )
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    r = g.query_events({"type": "T"})
    assert r.status == "complete"
    assert r.completeness == 1


def test_graphql_empty_page_with_stuck_cursor_is_scan_budget():
    # advances once (None -> c1), then stalls (c1 -> c1) -> scan_budget, incomplete.
    t = FakeTransport(
        [
            gql_page([], True, "c1"),
            gql_page([], True, "c1"),
        ]
    )
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    r = g.query_events({"type": "T"})
    assert r.status == "incomplete"
    assert r.error_class == "scan_budget"


def test_graphql_request_cap_reached_is_incomplete():
    t = FakeTransport([gql_page([gql_node(f"0x{i}", 0)], True, f"c{i}") for i in range(3)])
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of, request_cap=3)
    r = g.query_events({"type": "T"})
    assert r.status == "incomplete"
    assert r.error_class == "cap_reached"
    assert len(t.requests) == 3


def test_graphql_latest_checkpoint():
    t = FakeTransport([_ok({"data": {"checkpoint": {"sequenceNumber": "327443669"}}})])
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    assert g.latest_checkpoint() == 327443669


def test_graphql_checkpoint_by_sequence():
    t = FakeTransport(
        [_ok({"data": {"checkpoint": {"sequenceNumber": "100", "timestamp": "2026-09-27T00:00:00Z"}}})]
    )
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    cp = g.checkpoint_by_sequence(100)
    assert cp["sequenceNumber"] == "100"
    assert cp["timestamp"] == "2026-09-27T00:00:00Z"


# ==================== windowed collection (Q2) ====================

def rpc_ev_ts(digest, seq, ts_ms):
    return {"id": {"txDigest": digest, "eventSeq": str(seq)}, "timestampMs": str(ts_ms), "type": "T"}


def test_jsonrpc_collect_window_stops_when_crossing_start():
    # window [1000, 2000). Descending seed returns some newer-than-window, then
    # in-window, then an older-than-window event that stops pagination.
    t = FakeTransport(
        [
            rpc_page([rpc_ev_ts("0xNEW", 0, 2500), rpc_ev_ts("0xA", 0, 1800)], True, {"c": 1}),
            rpc_page([rpc_ev_ts("0xB", 0, 1200), rpc_ev_ts("0xOLD", 0, 500)], True, {"c": 2}),
        ]
    )
    c = JsonRpcClient(t, "http://x", "publicnode", page_size=50)
    events, terminal = c.collect_window({"MoveEventType": "T"}, {"c": 0}, ts_start_ms=1000, ts_end_ms=2000)
    assert terminal is None  # cleanly crossed the window start
    ids = [e["id"] for e in events]
    assert ids == [("0xA", 0), ("0xB", 0)]  # 0xNEW excluded (>=end), 0xOLD stops (<start)
    assert len(t.requests) == 2  # stopped as soon as it crossed, no third page


def test_jsonrpc_collect_window_cap_reached():
    cur = {"c": 1}
    # every page in-window and hasNextPage true -> never crosses start -> cap
    t = FakeTransport([rpc_page([rpc_ev_ts(f"0x{i}", 0, 1500)], True, cur) for i in range(3)])
    c = JsonRpcClient(t, "http://x", "publicnode", page_size=50, page_cap=3)
    events, terminal = c.collect_window({"MoveEventType": "T"}, None, ts_start_ms=1000, ts_end_ms=2000)
    assert terminal == "cap_reached"
    assert len(events) == 3


def test_graphql_collect_window_complete():
    def gnode(digest, seq, ts):
        return {"sequenceNumber": seq, "timestamp": ts, "transaction": {"digest": digest}}

    t = FakeTransport(
        [
            _ok({"data": {"events": {"nodes": [gnode("0xA", 0, "2026-09-27T00:00:01Z")],
                                      "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}}),
            _ok({"data": {"events": {"nodes": [gnode("0xB", 1, "2026-09-27T00:00:02Z")],
                                      "pageInfo": {"hasNextPage": False, "endCursor": "c2"}}}}),
        ]
    )
    g = GraphQlClient(t, "http://g", "mysten_graphql", id_of=gql_id_of)
    events, terminal = g.collect_window({"type": "T", "afterCheckpoint": 10, "beforeCheckpoint": 20})
    assert terminal is None
    ids = [e["id"] for e in events]
    assert ids == [("0xA", 0), ("0xB", 1)]
    assert events[0]["timestampMs"] == 1790467201000  # ISO -> epoch ms
