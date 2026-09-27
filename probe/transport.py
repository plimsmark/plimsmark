"""Transport seam.

Clients talk to a `transport` callable, never to httpx directly, so the whole
pagination surface can be exercised network-free with recorded responses. The
real transport (httpx, used only by live discovery in items 5-7) streams the
body and enforces an 8 MB per-body cap; the byte-cap logic itself lives in the
pure helper `read_capped` so it is testable without a socket.

    transport(url, payload, *, headers, byte_cap) -> HttpOutcome
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

BYTE_CAP = 8 * 1024 * 1024  # 8 MB per body


@dataclass
class HttpOutcome:
    """One HTTP attempt. Exactly one of (body) or (error) is meaningful."""

    status_code: Optional[int]
    body: Optional[bytes]
    truncated: bool = False  # byte cap hit while streaming -> cap_reached
    error: Optional[BaseException] = None
    bytes_len: int = 0

    def parsed(self):
        """Parse body as JSON. Raises ValueError (JSONDecodeError) on garbage,
        which the classifier maps to `ours`."""
        if self.body is None:
            return None
        return _json.loads(self.body)


def read_capped(chunks: Iterable[bytes], byte_cap: int = BYTE_CAP) -> Tuple[bytes, bool]:
    """Accumulate chunks up to byte_cap. Returns (body, truncated).

    Stops and reports truncated=True the moment the cap is exceeded, so we never
    materialize a huge body only to count it.
    """
    buf = bytearray()
    truncated = False
    for chunk in chunks:
        buf.extend(chunk)
        if len(buf) > byte_cap:
            truncated = True
            del buf[byte_cap:]
            break
    return bytes(buf), truncated


def httpx_transport(client, method: str = "POST"):
    """Build a transport bound to an httpx.Client. Live use only (items 5-7)."""

    def _transport(url, payload, *, headers=None, byte_cap: int = BYTE_CAP) -> HttpOutcome:
        try:
            with client.stream(
                method, url, json=payload, headers=headers or {}
            ) as resp:
                body, truncated = read_capped(resp.iter_bytes(), byte_cap)
                return HttpOutcome(
                    status_code=resp.status_code,
                    body=body,
                    truncated=truncated,
                    bytes_len=len(body),
                )
        except Exception as exc:  # noqa: BLE001 — a dead endpoint is a finding
            return HttpOutcome(status_code=None, body=None, error=exc)

    return _transport
