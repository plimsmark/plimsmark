"""Pure checkpoint<->timestamp bisection.

Windows are checkpoint ranges [c_start, c_end). To place a window at a target
wall-clock time we need the checkpoint whose timestamp floors the target. This
is a standard bisection over a monotonic non-decreasing timestamp function; the
live `ts_of` (one GraphQL call per probe) is injected, so the search logic is
testable without a socket.
"""

from __future__ import annotations

from typing import Callable


def bisect_checkpoint(
    ts_of: Callable[[int], int], target_ms: int, lo: int, hi: int
) -> int:
    """Return the greatest checkpoint c in [lo, hi] with ts_of(c) <= target_ms.

    Clamps to lo if the target precedes ts_of(lo), and to hi if it follows
    ts_of(hi). Assumes ts_of is non-decreasing in the checkpoint number.
    """
    if target_ms <= ts_of(lo):
        return lo
    if target_ms >= ts_of(hi):
        return hi
    # invariant: ts_of(lo) <= target < ts_of(hi)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts_of(mid) <= target_ms:
            lo = mid
        else:
            hi = mid
    return lo
