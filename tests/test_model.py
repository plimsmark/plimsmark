"""Tests for QueryResult — the completeness/status model.

The load-bearing invariant: NULL is not 0. A result that did not paginate to a
clean finish has completeness = None (unknown), never a count.
"""

import pytest

from probe.model import QueryResult

IDS = [("0xdeadbeef", 0), ("0xdeadbeef", 1), ("0xfeed", 0)]


def test_complete_result_counts_its_ids():
    r = QueryResult.complete("publicnode", IDS)
    assert r.status == "complete"
    assert r.completeness == 3
    assert r.ids == frozenset(IDS)
    assert r.error_class is None


def test_complete_with_no_events_is_zero_not_none():
    # A clean finish that genuinely found nothing IS 0 — distinct from unknown.
    r = QueryResult.complete("publicnode", [])
    assert r.status == "complete"
    assert r.completeness == 0
    assert r.ids == frozenset()


def test_incomplete_result_is_unknown_not_zero():
    r = QueryResult.incomplete("blockvision", "scan_budget", "0 nodes + hasNextPage")
    assert r.status == "incomplete"
    assert r.completeness is None  # NULL, not 0
    assert r.error_class == "scan_budget"
    assert r.error_reason == "0 nodes + hasNextPage"


def test_unsupported_result_is_unknown_not_zero():
    r = QueryResult.unsupported("blockvision", "definitive", "unknown variant `afterCheckpoint`")
    assert r.status == "unsupported"
    assert r.completeness is None
    assert r.error_class == "definitive"


def test_only_complete_results_participate_helper():
    complete = QueryResult.complete("publicnode", IDS)
    incomplete = QueryResult.incomplete("rpcpool", "cap_reached", "hit page cap")
    unsupported = QueryResult.unsupported("mysten_graphql", "definitive", "no such filter")
    assert complete.participates is True
    assert incomplete.participates is False
    assert unsupported.participates is False


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        QueryResult(provider="x", status="bogus", completeness=None, ids=frozenset())


def test_complete_must_have_int_completeness():
    # constructing a "complete" result with None completeness is a contradiction
    with pytest.raises(ValueError):
        QueryResult(provider="x", status="complete", completeness=None, ids=frozenset())


def test_incomplete_must_not_carry_a_count():
    # completeness must be None for non-complete statuses — guards NULL-is-not-0
    with pytest.raises(ValueError):
        QueryResult(provider="x", status="incomplete", completeness=5, ids=frozenset())
