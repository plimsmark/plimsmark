"""Comparison engine — reduce per-provider QueryResults for one query+window to
a verdict, plus the evidence (missing/extra sets, pairwise Jaccard).

Rules:
  - Only complete results participate.
  - `disagree` requires >=2 complete providers with DIFFERING id sets.
  - fewer than 2 complete -> `unknown`.
  - if the query is not established as comparable -> `not_comparable`
    passthrough (never "disagree").
  - a null (incomplete/unsupported) result is unknown, never 0, and never
    participates in the set comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from probe.model import QueryResult

AGREE = "agree"
DISAGREE = "disagree"
NOT_COMPARABLE = "not_comparable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderComparison:
    provider: str
    status: str
    count: Optional[int]
    # Only defined for complete providers; None for non-participating providers.
    missing_vs_union: Optional[frozenset]
    extra_vs_others: Optional[frozenset]
    error_class: Optional[str] = None
    error_reason: Optional[str] = None


@dataclass(frozen=True)
class ComparisonReport:
    verdict: str
    comparable: bool
    providers: List[ProviderComparison]
    pairwise_jaccard: Dict[Tuple[str, str], float]
    union_size: Optional[int]


def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    if not union:
        return 1.0  # two empty complete sets are identical
    return len(a & b) / len(union)


def compare(results: List[QueryResult], comparable: bool = True) -> ComparisonReport:
    complete = [r for r in results if r.participates]
    union = frozenset().union(*(r.ids for r in complete)) if complete else frozenset()

    rows: List[ProviderComparison] = []
    for r in results:
        if r.participates:
            others = frozenset().union(
                *(o.ids for o in complete if o.provider != r.provider)
            ) if len(complete) > 1 else frozenset()
            rows.append(
                ProviderComparison(
                    provider=r.provider,
                    status=r.status,
                    count=r.completeness,
                    missing_vs_union=union - r.ids,
                    extra_vs_others=r.ids - others,
                    error_class=r.error_class,
                    error_reason=r.error_reason,
                )
            )
        else:
            rows.append(
                ProviderComparison(
                    provider=r.provider,
                    status=r.status,
                    count=None,  # NULL is not 0
                    missing_vs_union=None,
                    extra_vs_others=None,
                    error_class=r.error_class,
                    error_reason=r.error_reason,
                )
            )

    pairwise: Dict[Tuple[str, str], float] = {}
    for a, b in combinations(complete, 2):
        key = tuple(sorted((a.provider, b.provider)))
        pairwise[key] = _jaccard(a.ids, b.ids)

    verdict = _verdict(complete, comparable)

    return ComparisonReport(
        verdict=verdict,
        comparable=comparable,
        providers=rows,
        pairwise_jaccard=pairwise,
        union_size=len(union) if complete else None,
    )


def _verdict(complete: List[QueryResult], comparable: bool) -> str:
    if not comparable:
        return NOT_COMPARABLE
    if len(complete) < 2:
        return UNKNOWN
    first = complete[0].ids
    if all(r.ids == first for r in complete[1:]):
        return AGREE
    return DISAGREE


def apply_boundary_guard(
    events: List[dict], ts_start_ms: int, ts_end_ms: int
) -> Tuple[List[dict], int]:
    """Exclude events whose timestamp equals ts(c_start) or ts(c_end).

    Checkpoints can share a millisecond, so an event exactly on either boundary
    is ambiguous across the [c_start, c_end) window and is dropped on ALL
    providers alike. Returns (kept_events, excluded_count).
    """
    kept = []
    excluded = 0
    for e in events:
        ts = e.get("timestampMs")
        if ts == ts_start_ms or ts == ts_end_ms:
            excluded += 1
        else:
            kept.append(e)
    return kept, excluded
