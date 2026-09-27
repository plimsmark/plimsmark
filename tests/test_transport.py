"""Tests for the pure byte-cap helper. No socket involved."""

from probe.transport import read_capped


def test_under_cap_returns_full_body_not_truncated():
    chunks = [b"hello ", b"world"]
    body, truncated = read_capped(chunks, byte_cap=1024)
    assert body == b"hello world"
    assert truncated is False


def test_over_cap_stops_at_cap_and_flags_truncated():
    chunks = [b"a" * 10, b"b" * 10]
    body, truncated = read_capped(chunks, byte_cap=15)
    assert truncated is True
    assert len(body) == 15  # never materialize past the cap
    assert body == b"a" * 10 + b"b" * 5


def test_exactly_at_cap_is_not_truncated():
    body, truncated = read_capped([b"x" * 8], byte_cap=8)
    assert truncated is False
    assert len(body) == 8
