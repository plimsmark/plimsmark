"""Shared live-probe helpers for the discovery/run scripts (items 5-7).

NETWORK-USING. Never imported by the test suite (conftest's socket guard only
loads under pytest). Every call is recorded as a full observation row.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from probe.classify import classify  # noqa: E402
from probe.transport import read_capped, BYTE_CAP  # noqa: E402

UA = "plimmark-sui-spike/0.1"
VANTAGE = os.environ.get("VANTAGE", "local-dev")

PROVIDERS = {
    "mysten_graphql": ("https://graphql.mainnet.sui.io/graphql", "graphql"),
    "publicnode": ("https://sui-rpc.publicnode.com", "jsonrpc"),
    "blockvision": ("https://sui-mainnet-endpoint.blockvision.org", "jsonrpc"),
    "rpcpool": ("https://mainnet.sui.rpcpool.com", "jsonrpc"),
}


def probe_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


PROBE_COMMIT = probe_commit()


@dataclass
class Observation:
    utc: str
    provider: str
    endpoint: str
    method_or_query: str
    params: object
    http_status: Optional[int]
    latency_ms: float
    response_bytes: int
    error_class: Optional[str]
    error_reason: Optional[str]
    user_agent: str
    vantage: str
    probe_commit: str


class Live:
    """A polite live client: <=2 req/s per provider, jitter, records every row."""

    def __init__(self, byte_cap: int = BYTE_CAP):
        self._client = httpx.Client(
            timeout=40.0,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
        )
        self._last_hit: dict[str, float] = {}
        self.byte_cap = byte_cap
        self.rows: list[Observation] = []

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _polite(self, provider: str):
        # Rule ceiling is <=2 req/s per provider. blockvision 429s at that rate,
        # so we run at ~1 req/s (>=1.0s spacing) plus 0-0.4s jitter to stay safe.
        last = self._last_hit.get(provider, 0.0)
        wait = 1.0 - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        time.sleep(random.uniform(0.0, 0.4))
        self._last_hit[provider] = time.monotonic()

    def post(self, provider: str, method_or_query: str, params, payload: dict):
        url, kind = PROVIDERS[provider]
        self._polite(provider)
        utc = datetime.now(timezone.utc).isoformat()
        t0 = time.time()
        status = None
        body = b""
        truncated = False
        err_class = None
        err_reason = None
        parsed = None
        try:
            with self._client.stream("POST", url, json=payload) as resp:
                status = resp.status_code
                body, truncated = read_capped(resp.iter_bytes(), self.byte_cap)
            latency = (time.time() - t0) * 1000.0
            if truncated:
                err_class, err_reason = "cap_reached", "byte cap hit while streaming"
            else:
                try:
                    parsed = json.loads(body) if body else None
                    cls, reason = classify(kind, status, parsed if parsed is not None else body.decode("utf-8", "replace"))
                    if cls != "ok":
                        err_class, err_reason = cls, reason
                except ValueError as exc:
                    cls, reason = classify(kind, status, exc)
                    err_class, err_reason = cls, reason
        except Exception as exc:  # noqa: BLE001
            latency = (time.time() - t0) * 1000.0
            cls, reason = classify(kind, None, exc)
            err_class, err_reason = cls, reason

        self.rows.append(
            Observation(
                utc=utc,
                provider=provider,
                endpoint=url,
                method_or_query=method_or_query,
                params=params,
                http_status=status,
                latency_ms=round(latency, 1),
                response_bytes=len(body),
                error_class=err_class,
                error_reason=err_reason,
                user_agent=UA,
                vantage=VANTAGE,
                probe_commit=PROBE_COMMIT,
            )
        )
        return status, parsed, body, (err_class, err_reason)

    def rpc(self, provider: str, method: str, params: list):
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        return self.post(provider, method, params, payload)

    def gql(self, query: str, variables: Optional[dict] = None, label: str = ""):
        payload = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        return self.post("mysten_graphql", label or query[:60], variables, payload)


def dump_rows(rows: list[Observation], path: str):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(asdict(r)) + "\n")
