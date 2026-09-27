"""Tests for the pure checkpoint<->timestamp bisection used to define windows."""

from probe.windows import bisect_checkpoint


def test_floor_checkpoint_for_target():
    # synthetic chain: checkpoint c has timestamp c * 1000 ms
    ts_of = lambda c: c * 1000
    # target 5500ms -> floor checkpoint is 5 (ts 5000 <= 5500 < 6000)
    assert bisect_checkpoint(ts_of, 5500, lo=0, hi=100) == 5


def test_exact_hit_returns_that_checkpoint():
    ts_of = lambda c: c * 1000
    assert bisect_checkpoint(ts_of, 7000, lo=0, hi=100) == 7


def test_target_before_lo_returns_lo():
    ts_of = lambda c: c * 1000
    assert bisect_checkpoint(ts_of, -50, lo=3, hi=100) == 3


def test_target_after_hi_returns_hi():
    ts_of = lambda c: c * 1000
    assert bisect_checkpoint(ts_of, 10_000_000, lo=0, hi=42) == 42


def test_bisection_is_logarithmic_in_calls():
    calls = []

    def ts_of(c):
        calls.append(c)
        return c * 1000

    bisect_checkpoint(ts_of, 500_000, lo=0, hi=1_000_000)
    # ~log2(1e6) ~= 20 lookups, nowhere near linear
    assert len(calls) < 40
