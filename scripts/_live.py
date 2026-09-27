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
from probe.transport import read_capped, BYTE_CAP, HttpOutcome  # noqa: E402

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
    attempt: int = 0
    raw_path: Optional[str] = None
    raw_truncated: bool = False


# Rule ceiling is <=2 req/s per provider. blockvision 429s at that rate, so it
# gets a wider spacing; the others run at the ceiling.
PROVIDER_MIN_SPACING = {"blockvision": 1.2}
DEFAULT_MIN_SPACING = 0.5


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


import gzip  # noqa: E402
import pathlib  # noqa: E402

RAW_RUN_CAP = 50 * 1024 * 1024  # 50 MB per run for raw bodies


class RecordingTransport:
    """A transport-callable (for probe.clients) that is polite, retries transient
    failures with exponential backoff (each attempt its own observation row),
    streams with a byte cap, and gzips raw bodies under fixtures/raw/<run_id>/
    until a 50 MB per-run cap, after which it keeps metadata rows only and flags
    raw_truncated.
    """

    def __init__(self, run_id: str, raw_root: str, byte_cap: int = BYTE_CAP, max_retries: int = 3):
        self.run_id = run_id
        self.raw_dir = pathlib.Path(raw_root) / run_id
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.byte_cap = byte_cap
        self.max_retries = max_retries
        self.rows: list[Observation] = []
        self._client = httpx.Client(
            timeout=40.0, headers={"User-Agent": UA, "Content-Type": "application/json"}
        )
        self._last_hit: dict[str, float] = {}
        self._url2provider = {url: name for name, (url, _k) in PROVIDERS.items()}
        self._raw_bytes = 0
        self._seq = 0

    def close(self):
        self._client.close()

    def _polite(self, provider: str):
        spacing = PROVIDER_MIN_SPACING.get(provider, DEFAULT_MIN_SPACING)
        wait = spacing - (time.monotonic() - self._last_hit.get(provider, 0.0))
        if wait > 0:
            time.sleep(wait)
        time.sleep(random.uniform(0.0, 0.3))
        self._last_hit[provider] = time.monotonic()

    def _save_raw(self, provider: str, body: bytes) -> tuple[Optional[str], bool]:
        if self._raw_bytes + len(body) > RAW_RUN_CAP:
            return None, True  # run raw cap reached -> metadata only
        self._seq += 1
        path = self.raw_dir / f"{self._seq:05d}_{provider}.json.gz"
        with gzip.open(path, "wb") as f:
            f.write(body)
        self._raw_bytes += len(body)
        return str(path.relative_to(self.raw_dir.parent.parent)), False

    def __call__(self, url, payload, *, headers=None, byte_cap=None) -> HttpOutcome:
        provider = self._url2provider[url]
        kind = PROVIDERS[provider][1]
        cap = byte_cap or self.byte_cap
        method_or_query = payload.get("method") or payload.get("query", "")[:80]
        params = payload.get("params", payload.get("variables"))

        outcome = HttpOutcome(status_code=None, body=None)
        for attempt in range(self.max_retries + 1):
            self._polite(provider)
            utc = datetime.now(timezone.utc).isoformat()
            t0 = time.time()
            status = None
            body = b""
            truncated = False
            err = None
            try:
                with self._client.stream("POST", url, json=payload, headers=headers or {}) as resp:
                    status = resp.status_code
                    body, truncated = read_capped(resp.iter_bytes(), cap)
                latency = (time.time() - t0) * 1000.0
            except Exception as exc:  # noqa: BLE001
                latency = (time.time() - t0) * 1000.0
                err = exc

            # classify this attempt
            if err is not None:
                ec, er = classify(kind, None, err)
            elif truncated:
                ec, er = "cap_reached", "byte cap hit while streaming"
            else:
                try:
                    parsed = json.loads(body) if body else None
                    arg = parsed if parsed is not None else body.decode("utf-8", "replace")
                    cls, reason = classify(kind, status, arg)
                    ec, er = (None, None) if cls == "ok" else (cls, reason)
                except ValueError as exc:
                    ec, er = classify(kind, status, exc)

            raw_path, raw_trunc = (None, False)
            if body:
                raw_path, raw_trunc = self._save_raw(provider, body)

            self.rows.append(
                Observation(
                    utc=utc, provider=provider, endpoint=url,
                    method_or_query=method_or_query, params=params,
                    http_status=status, latency_ms=round(latency, 1),
                    response_bytes=len(body), error_class=ec, error_reason=er,
                    user_agent=UA, vantage=VANTAGE, probe_commit=PROBE_COMMIT,
                    attempt=attempt, raw_path=raw_path, raw_truncated=raw_trunc,
                )
            )

            outcome = HttpOutcome(
                status_code=status, body=body if not err else None,
                truncated=truncated, error=err, bytes_len=len(body),
            )

            # retry only on transient; each retry is its own row above
            if ec == "transient" and attempt < self.max_retries:
                time.sleep((2 ** attempt) + random.uniform(0.0, 0.5))
                continue
            break

        return outcome
