"""Tests for the comparison engine.

Only complete results participate. `disagree` requires >=2 complete providers
with differing ID sets; fewer than 2 complete -> unknown. A null (incomplete)
result must never be silently turned into 0. not_comparable is a passthrough.
"""

import pytest

from probe.compare import (
    AGREE,
    DISAGREE,
    NOT_COMPARABLE,
    UNKNOWN,
    apply_boundary_guard,
    compare,
)
from probe.model import QueryResult

A_IDS = [("0xaa", 0), ("0xbb", 0), ("0xcc", 1)]


def _provider_row(report, name):
    return next(p for p in report.providers if p.provider == name)


def test_all_agree():
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.complete("blockvision", A_IDS),
        QueryResult.complete("rpcpool", A_IDS),
    ]
    report = compare(results, comparable=True)
    assert report.verdict == AGREE
    for name in ("publicnode", "blockvision", "rpcpool"):
        row = _provider_row(report, name)
        assert row.count == 3
        assert row.missing_vs_union == frozenset()
        assert row.extra_vs_others == frozenset()
    # every complete pair is identical -> Jaccard 1.0
    assert all(j == 1.0 for j in report.pairwise_jaccard.values())


def test_one_provider_missing_ids_is_disagree():
    missing_one = [("0xaa", 0), ("0xbb", 0)]  # lacks ("0xcc", 1)
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.complete("blockvision", missing_one),
        QueryResult.complete("rpcpool", A_IDS),
    ]
    report = compare(results, comparable=True)
    assert report.verdict == DISAGREE
    bv = _provider_row(report, "blockvision")
    assert bv.missing_vs_union == frozenset([("0xcc", 1)])
    pn = _provider_row(report, "publicnode")
    assert pn.missing_vs_union == frozenset()
    # Jaccard between full and missing-one: |∩|=2, |∪|=3
    key = tuple(sorted(("publicnode", "blockvision")))
    assert report.pairwise_jaccard[key] == pytest.approx(2 / 3)


def test_extra_vs_others_flags_a_unique_id():
    with_extra = A_IDS + [("0xzz", 9)]
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.complete("blockvision", with_extra),
    ]
    report = compare(results, comparable=True)
    assert report.verdict == DISAGREE
    bv = _provider_row(report, "blockvision")
    assert bv.extra_vs_others == frozenset([("0xzz", 9)])


def test_null_result_is_not_turned_into_zero():
    # C is incomplete (unknown). A and B are complete and agree.
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.complete("blockvision", A_IDS),
        QueryResult.incomplete("rpcpool", "scan_budget", "0 nodes + hasNextPage"),
    ]
    report = compare(results, comparable=True)
    # two complete providers agree -> agree; the unknown one does not drag it
    assert report.verdict == AGREE
    rp = _provider_row(report, "rpcpool")
    assert rp.count is None  # NOT 0
    assert rp.missing_vs_union is None  # excluded from set comparison
    assert rp.status == "incomplete"


def test_fewer_than_two_complete_is_unknown():
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.incomplete("blockvision", "transient", "timeout"),
        QueryResult.unsupported("rpcpool", "definitive", "unknown variant"),
    ]
    report = compare(results, comparable=True)
    assert report.verdict == UNKNOWN


def test_zero_complete_is_unknown():
    results = [
        QueryResult.incomplete("publicnode", "cap_reached", "hit page cap"),
        QueryResult.unsupported("blockvision", "definitive", "no such filter"),
    ]
    report = compare(results, comparable=True)
    assert report.verdict == UNKNOWN


def test_not_comparable_passthrough():
    # Sets differ, but the query is not established as comparable -> not_comparable,
    # never "disagree".
    results = [
        QueryResult.complete("publicnode", A_IDS),
        QueryResult.complete("mysten_graphql", [("0xaa", 0)]),
    ]
    report = compare(results, comparable=False)
    assert report.verdict == NOT_COMPARABLE


# --- boundary guard ---

def _ev(digest, seq, ts):
    return {"id": (digest, seq), "timestampMs": ts}


def test_boundary_guard_excludes_both_endpoints():
    ts_start, ts_end = 1000, 2000
    events = [
        _ev("0xa", 0, 1000),  # == ts_start  -> excluded
        _ev("0xb", 0, 1500),  # interior     -> kept
        _ev("0xc", 0, 2000),  # == ts_end    -> excluded
        _ev("0xd", 0, 1999),  # interior     -> kept
    ]
    kept, excluded = apply_boundary_guard(events, ts_start, ts_end)
    assert excluded == 2
    assert [e["id"] for e in kept] == [("0xb", 0), ("0xd", 0)]


def test_boundary_guard_keeps_all_when_no_endpoint_hits():
    events = [_ev("0xa", 0, 1500), _ev("0xb", 0, 1600)]
    kept, excluded = apply_boundary_guard(events, 1000, 2000)
    assert excluded == 0
    assert len(kept) == 2
