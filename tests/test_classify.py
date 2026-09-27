"""Tests for the failure classifier.

Every input string here is a VERBATIM shape observed from a live Sui endpoint
(see reference/observed_2026-09-27-sui.md, dated 2026-09-27). We re-verify these
live later; here we only pin the classification logic.
"""

import httpx
import pytest

from probe.classify import (
    CAP_REACHED,
    DEFINITIVE,
    OK,
    OURS,
    SCAN_BUDGET,
    TRANSIENT,
    classify,
)

# --- verbatim bodies from reference/observed_2026-09-27-sui.md ---

DEPRECATION_32601 = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32601,
        "message": (
            "Method not found. JSON-RPC on public fullnodes has been deprecated. "
            "Please migrate to gRPC or GraphQL endpoints. See "
            "https://docs.sui.io/develop/accessing-data/json-rpc-migration "
            "for more information."
        ),
    },
}

UNKNOWN_VARIANT_32602 = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32602,
        "message": (
            "Invalid params: unknown variant `afterCheckpoint`, expected one of "
            "`All`, `Any`, `Sender`, `Transaction`, `MoveModule`, `MoveEventType`, "
            "`MoveEventModule`, `TimeRange`"
        ),
    },
}

PAGE_SIZE_TOO_LARGE = {
    "errors": [
        {
            "message": "Page size is too large: 51 > 50",
            "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
        }
    ]
}

SCAN_BUDGET_SHAPE = {
    "data": {"events": {"nodes": [], "pageInfo": {"hasNextPage": True}}}
}

NORMAL_GRAPHQL_PAGE = {
    "data": {
        "events": {
            "nodes": [{"timestamp": "2026-09-27T00:00:00Z"}],
            "pageInfo": {"hasNextPage": True},
        }
    }
}


# --- definitive ---

def test_minus_32601_method_not_found_is_definitive():
    cls, reason = classify("jsonrpc", 200, DEPRECATION_32601)
    assert cls == DEFINITIVE
    # verbatim message preserved, not paraphrased
    assert reason == DEPRECATION_32601["error"]["message"]


def test_minus_32602_unknown_variant_filter_is_definitive():
    cls, reason = classify("jsonrpc", 200, UNKNOWN_VARIANT_32602)
    assert cls == DEFINITIVE
    assert reason == UNKNOWN_VARIANT_32602["error"]["message"]


def test_no_longer_available_is_definitive():
    body = "This endpoint is no longer available."
    cls, reason = classify("jsonrpc", 410, body)
    assert cls == DEFINITIVE
    assert reason == body


def test_key_required_401_is_definitive():
    body = "API key required"
    cls, reason = classify("jsonrpc", 401, body)
    assert cls == DEFINITIVE
    assert reason == body


# --- ours ---

def test_page_size_too_large_is_ours():
    # We asked for first:51 when the declared cap is 50 -> our request was wrong.
    cls, reason = classify("graphql", 200, PAGE_SIZE_TOO_LARGE)
    assert cls == OURS
    assert reason == "Page size is too large: 51 > 50"


def test_json_decode_error_is_ours():
    exc = ValueError("Expecting value: line 1 column 1 (char 0)")
    cls, reason = classify("jsonrpc", 200, exc)
    assert cls == OURS
    assert "Expecting value" in reason


# --- transient ---

def test_timeout_exception_is_transient():
    exc = httpx.ReadTimeout("timed out")
    cls, reason = classify("jsonrpc", None, exc)
    assert cls == TRANSIENT
    assert "timed out" in reason


def test_connect_error_is_transient():
    exc = httpx.ConnectError("connection refused")
    cls, reason = classify("graphql", None, exc)
    assert cls == TRANSIENT
    assert "connection refused" in reason


def test_http_429_is_transient():
    cls, reason = classify("jsonrpc", 429, "Too Many Requests")
    assert cls == TRANSIENT
    assert "429" in reason or "Too Many Requests" in reason


def test_http_503_is_transient():
    cls, reason = classify("graphql", 503, "<html>Service Unavailable</html>")
    assert cls == TRANSIENT
    assert "503" in reason or "Service Unavailable" in reason


# --- scan_budget ---

def test_graphql_empty_page_with_next_is_scan_budget_shape():
    cls, reason = classify("graphql", 200, SCAN_BUDGET_SHAPE)
    assert cls == SCAN_BUDGET
    assert "hasNextPage" in reason


def test_non_empty_graphql_page_is_ok():
    cls, _ = classify("graphql", 200, NORMAL_GRAPHQL_PAGE)
    assert cls == OK


# --- GraphQL server-side execution error is transient, not definitive ---

def test_graphql_failed_to_list_events_is_transient():
    # Verbatim run1 shape: this identical query SUCCEEDED in run2, so a server-side
    # execution error must be transient (retryable), not definitive.
    body = {"errors": [{"message": "Failed to list events"}]}
    cls, reason = classify("graphql", 200, body)
    assert cls == TRANSIENT
    assert reason == "Failed to list events"


def test_graphql_schema_validation_stays_definitive():
    # A known definitive shape (schema validation / unknown field) is NOT retryable.
    body = {
        "errors": [
            {
                "message": 'Cannot query field "bogus" on type "Query".',
                "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
            }
        ]
    }
    cls, _ = classify("graphql", 200, body)
    assert cls == DEFINITIVE


def test_graphql_page_size_still_ours_not_transient():
    # Regression guard: page-size-too-large stays OURS even after the transient
    # default; it is our request, not a server hiccup.
    cls, _ = classify("graphql", 200, PAGE_SIZE_TOO_LARGE)
    assert cls == OURS


# --- ok passthrough for clean JSON-RPC result ---

def test_clean_jsonrpc_result_is_ok():
    body = {"jsonrpc": "2.0", "id": 1, "result": {"data": [], "hasNextPage": False}}
    cls, _ = classify("jsonrpc", 200, body)
    assert cls == OK


def test_cap_reached_is_not_produced_by_classify():
    # cap_reached is raised by the pagination engine (our own cap), never by a
    # provider body. classify must never invent it.
    assert CAP_REACHED == "cap_reached"
