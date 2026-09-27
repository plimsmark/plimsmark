"""JSON-RPC and GraphQL clients with cursor pagination.

Both clients talk only to an injected `transport` callable, so every pagination
path is exercised network-free with recorded responses.

Pagination contract (item 4):
  - fewer results than requested with hasNextPage true is NORMAL — keep going.
  - GraphQL 0 nodes + hasNextPage true: continue WHILE the cursor advances;
    if the cursor stalls, that is scan_budget -> incomplete.
  - JSON-RPC page cap (default 400) and GraphQL request cap (default 1500) ->
    cap_reached -> incomplete, recording the coverage reached.
  - a truncated body (byte cap) -> cap_reached -> incomplete.
  - a definitive refusal -> unsupported; transient/ours -> incomplete.
"""

from __future__ import annotations

from typing import Callable, Optional

from probe.classify import (
    DEFINITIVE,
    OK,
    SCAN_BUDGET,
    TRANSIENT,
    classify,
)
from probe.model import QueryResult
from probe.transport import BYTE_CAP

JSONRPC_PAGE_SIZE = 50
JSONRPC_PAGE_CAP = 400
GRAPHQL_PAGE_SIZE = 50
GRAPHQL_REQUEST_CAP = 1500


def _jsonrpc_id(ev: dict):
    """JSON-RPC event identity = (txDigest, eventSeq)."""
    i = ev["id"]
    return (i["txDigest"], int(i["eventSeq"]))


def _outcome_to_result(kind, provider, outcome):
    """Turn a non-usable HTTP outcome into a QueryResult, or return (None, parsed)
    if the outcome is usable and should be parsed by the caller."""
    # byte cap hit -> cap_reached before we even try to parse a truncated body
    if outcome.truncated:
        return QueryResult.incomplete(
            provider, "cap_reached", "byte cap hit while streaming (body truncated)"
        )
    # transport exception
    if outcome.error is not None:
        cls, reason = classify(kind, outcome.status_code, outcome.error)
        return _class_to_result(provider, cls, reason)
    # parse the body
    try:
        parsed = outcome.parsed()
    except ValueError as exc:
        cls, reason = classify(kind, outcome.status_code, exc)
        return _class_to_result(provider, cls, reason)
    return (None, parsed)


def _class_to_result(provider, cls, reason):
    if cls == DEFINITIVE:
        return QueryResult.unsupported(provider, DEFINITIVE, reason)
    # transient, ours, cap_reached, scan_budget all -> incomplete (unknown)
    return QueryResult.incomplete(provider, cls, reason)


class JsonRpcClient:
    def __init__(
        self,
        transport: Callable,
        url: str,
        provider: str,
        page_size: int = JSONRPC_PAGE_SIZE,
        page_cap: int = JSONRPC_PAGE_CAP,
        byte_cap: int = BYTE_CAP,
        headers: Optional[dict] = None,
    ):
        self.transport = transport
        self.url = url
        self.provider = provider
        self.page_size = page_size
        self.page_cap = page_cap
        self.byte_cap = byte_cap
        self.headers = headers or {}

    def _call(self, method, params):
        return self.transport(
            self.url,
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers=self.headers,
            byte_cap=self.byte_cap,
        )

    def latest_checkpoint(self) -> int:
        outcome = self._call("sui_getLatestCheckpointSequenceNumber", [])
        parsed = outcome.parsed()
        return int(parsed["result"])

    def query_events(self, event_filter: dict) -> QueryResult:
        cursor = None
        ids = set()
        coverage_newest = None
        coverage_oldest = None
        for page in range(self.page_cap):
            outcome = self._call(
                "suix_queryEvents",
                [event_filter, cursor, self.page_size, True],  # descending order
            )
            early = _outcome_to_result("jsonrpc", self.provider, outcome)
            if isinstance(early, QueryResult):
                return early
            _, parsed = early

            cls, reason = classify("jsonrpc", outcome.status_code, parsed)
            if cls != OK:
                return _class_to_result(self.provider, cls, reason)

            result = parsed.get("result") or {}
            data = result.get("data") or []
            for ev in data:
                ids.add(_jsonrpc_id(ev))
                ts = ev.get("timestampMs")
                if ts is not None:
                    ts = int(ts)
                    coverage_newest = ts if coverage_newest is None else max(coverage_newest, ts)
                    coverage_oldest = ts if coverage_oldest is None else min(coverage_oldest, ts)

            if not result.get("hasNextPage"):
                return QueryResult.complete(self.provider, ids)
            cursor = result.get("nextCursor")

        # fell out of the loop -> we hit our own page cap with more pages remaining
        return QueryResult.incomplete(
            self.provider,
            "cap_reached",
            f"page cap {self.page_cap} reached; coverage timestampMs "
            f"[{coverage_oldest}, {coverage_newest}], {len(ids)} events so far",
        )


_EVENTS_QUERY = (
    "query($first:Int!,$after:String,$filter:EventFilter){"
    "events(first:$first,after:$after,filter:$filter){"
    "pageInfo{hasNextPage endCursor} nodes{__typename}}}"
)


class GraphQlClient:
    def __init__(
        self,
        transport: Callable,
        url: str,
        provider: str,
        id_of: Callable,
        page_size: int = GRAPHQL_PAGE_SIZE,
        request_cap: int = GRAPHQL_REQUEST_CAP,
        byte_cap: int = BYTE_CAP,
        events_query: str = _EVENTS_QUERY,
        headers: Optional[dict] = None,
    ):
        self.transport = transport
        self.url = url
        self.provider = provider
        self.id_of = id_of
        self.page_size = page_size
        self.request_cap = request_cap
        self.byte_cap = byte_cap
        self.events_query = events_query
        self.headers = headers or {}

    def _call(self, query, variables):
        return self.transport(
            self.url,
            {"query": query, "variables": variables},
            headers=self.headers,
            byte_cap=self.byte_cap,
        )

    def latest_checkpoint(self) -> int:
        outcome = self._call("{ checkpoint { sequenceNumber } }", {})
        parsed = outcome.parsed()
        return int(parsed["data"]["checkpoint"]["sequenceNumber"])

    def checkpoint_by_sequence(self, seq: int) -> dict:
        outcome = self._call(
            "query($n:UInt53!){ checkpoint(sequenceNumber:$n){ sequenceNumber timestamp } }",
            {"n": seq},
        )
        parsed = outcome.parsed()
        return parsed["data"]["checkpoint"]

    def query_events(self, event_filter: dict, id_of: Optional[Callable] = None) -> QueryResult:
        id_of = id_of or self.id_of
        cursor = None
        ids = set()
        for _request in range(self.request_cap):
            outcome = self._call(
                self.events_query,
                {"first": self.page_size, "after": cursor, "filter": event_filter},
            )
            early = _outcome_to_result("graphql", self.provider, outcome)
            if isinstance(early, QueryResult):
                return early
            _, parsed = early

            events = (parsed.get("data") or {}).get("events") or {}
            nodes = events.get("nodes")
            page_info = events.get("pageInfo") or {}
            has_next = page_info.get("hasNextPage")
            end_cursor = page_info.get("endCursor")

            # error envelope (no usable events connection)?
            if nodes is None:
                cls, reason = classify("graphql", outcome.status_code, parsed)
                if cls == OK:
                    cls, reason = "ours", "GraphQL response had no events connection"
                return _class_to_result(self.provider, cls, reason)

            if len(nodes) == 0 and has_next:
                # scan budget: only survivable if the cursor is advancing
                if end_cursor is None or end_cursor == cursor:
                    return QueryResult.incomplete(
                        self.provider,
                        SCAN_BUDGET,
                        f"0 nodes + hasNextPage=true, cursor did not advance "
                        f"(endCursor={end_cursor!r})",
                    )
                cursor = end_cursor
                continue

            for node in nodes:
                ids.add(id_of(node))

            if not has_next:
                return QueryResult.complete(self.provider, ids)
            cursor = end_cursor

        return QueryResult.incomplete(
            self.provider,
            "cap_reached",
            f"request cap {self.request_cap} reached; {len(ids)} events so far",
        )
