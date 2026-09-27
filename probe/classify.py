"""Failure classifier — pure mapping from a provider response to a class.

    classify(provider_kind, http_status, body_or_exception) -> (class, verbatim_reason)

`provider_kind` is "jsonrpc" or "graphql". `body_or_exception` is one of:
  - an Exception (transport failure, or a parse error we raised)
  - a parsed JSON dict (JSON-RPC or GraphQL envelope)
  - a raw string (unparseable body, e.g. an HTML 5xx page)

The verbatim_reason is ALWAYS the exact provider text (or exception repr) — never
paraphrased — because a spike's value is in the raw evidence it keeps.

Classes:
  definitive   method not found, unsupported filter, invalid params (unknown
               variant), "no longer available", key required
  transient    timeout, connection error, 429, 5xx
  ours         a request WE built wrong (e.g. page size over the declared cap),
               or our own parse error
  scan_budget  GraphQL SHAPE: 0 nodes + hasNextPage true (the pagination engine
               confirms "no advancing cursor" before treating it as terminal)
  ok           a clean, usable response

`cap_reached` is NEVER produced here — it is our own page/byte/request cap, which
only the pagination engine (item 4) can raise.
"""

from __future__ import annotations

from typing import Tuple, Union

DEFINITIVE = "definitive"
TRANSIENT = "transient"
OURS = "ours"
SCAN_BUDGET = "scan_budget"
CAP_REACHED = "cap_reached"
OK = "ok"

# Substrings that mark a permanent, no-retry refusal, kept verbatim.
_DEFINITIVE_MARKERS = (
    "no longer available",
    "method not found",
    "api key",
    "key required",
    "requires a key",
    "unauthorized",
    "unknown variant",
    "unsupported",
)

# JSON-RPC error codes we treat as definitive.
_DEFINITIVE_RPC_CODES = (-32601, -32602)


def _reason_from_body(body: object) -> str:
    """Best verbatim message from a parsed body, else its string form."""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and "message" in err:
            return str(err["message"])
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict) and "message" in first:
                return str(first["message"])
    return str(body)


def classify(
    provider_kind: str,
    http_status: Union[int, None],
    body_or_exception: object,
) -> Tuple[str, str]:
    # 1. Transport / parse exceptions.
    if isinstance(body_or_exception, BaseException):
        exc = body_or_exception
        reason = f"{type(exc).__name__}: {exc}"
        # A JSON parse error means WE mishandled the body -> ours.
        if isinstance(exc, ValueError):
            return OURS, reason
        # Everything else transport-shaped (timeout, connect, read, OS) -> transient.
        return TRANSIENT, reason

    body = body_or_exception
    reason = _reason_from_body(body)

    # 2. JSON-RPC error envelope — code decides first.
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("code")
        msg = str(body["error"].get("message", ""))
        if code in _DEFINITIVE_RPC_CODES:
            return DEFINITIVE, msg
        if any(m in msg.lower() for m in _DEFINITIVE_MARKERS):
            return DEFINITIVE, msg
        # An RPC error with a non-definitive code and 5xx/429 status -> transient.
        if http_status is not None and (http_status == 429 or http_status >= 500):
            return TRANSIENT, msg
        return DEFINITIVE, msg  # unknown RPC error: conservatively no-retry

    # 3. GraphQL error envelope.
    if isinstance(body, dict) and isinstance(body.get("errors"), list) and body["errors"]:
        msg = reason
        low = msg.lower()
        if "page size is too large" in low:
            return OURS, msg  # we asked for more than the declared cap
        if any(m in low for m in _DEFINITIVE_MARKERS):
            return DEFINITIVE, msg
        if http_status is not None and (http_status == 429 or http_status >= 500):
            return TRANSIENT, msg
        return DEFINITIVE, msg

    # 4. HTTP status on a body with no structured error.
    if http_status is not None:
        if http_status == 429 or http_status >= 500:
            return TRANSIENT, f"HTTP {http_status}: {reason}"
        if http_status in (401, 403):
            return DEFINITIVE, reason
        if http_status == 410:  # Gone
            if any(m in reason.lower() for m in _DEFINITIVE_MARKERS):
                return DEFINITIVE, reason
            return DEFINITIVE, reason

    # 5. Raw string bodies (no envelope) — scan markers.
    if isinstance(body, str):
        if any(m in body.lower() for m in _DEFINITIVE_MARKERS):
            return DEFINITIVE, body

    # 6. GraphQL success shapes: detect the scan-budget shape.
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        events = body["data"].get("events")
        if isinstance(events, dict):
            nodes = events.get("nodes")
            page_info = events.get("pageInfo") or {}
            if isinstance(nodes, list) and len(nodes) == 0 and page_info.get("hasNextPage"):
                return SCAN_BUDGET, f"0 nodes + hasNextPage={page_info.get('hasNextPage')}"

    # 7. Anything else is a clean, usable response.
    return OK, reason
