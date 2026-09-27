"""QueryResult — per-provider outcome of one query over one window.

Invariant (load-bearing): NULL is not 0. Only a query that paginated to a clean
finish has an integer completeness. Anything that did not finish cleanly has
completeness = None (unknown) and does NOT participate in comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

_VALID_STATUS = ("complete", "incomplete", "unsupported")


@dataclass(frozen=True)
class QueryResult:
    provider: str
    status: str
    completeness: Optional[int]
    ids: frozenset
    error_class: Optional[str] = None
    error_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUS:
            raise ValueError(
                f"status must be one of {_VALID_STATUS}, got {self.status!r}"
            )
        if self.status == "complete":
            if not isinstance(self.completeness, int):
                raise ValueError(
                    "a complete result must carry an integer completeness "
                    "(the count of events), never None"
                )
            if self.completeness != len(self.ids):
                raise ValueError(
                    f"complete result completeness ({self.completeness}) must "
                    f"equal len(ids) ({len(self.ids)})"
                )
        else:
            # incomplete / unsupported: unknown, never a count. NULL is not 0.
            if self.completeness is not None:
                raise ValueError(
                    f"a {self.status} result is unknown; completeness must be "
                    f"None (NULL is not 0), got {self.completeness!r}"
                )

    @property
    def participates(self) -> bool:
        """Only complete results participate in cross-provider comparison."""
        return self.status == "complete"

    @classmethod
    def complete(cls, provider: str, ids: Iterable) -> "QueryResult":
        frozen = frozenset(ids)
        return cls(
            provider=provider,
            status="complete",
            completeness=len(frozen),
            ids=frozen,
        )

    @classmethod
    def incomplete(
        cls, provider: str, error_class: str, error_reason: str
    ) -> "QueryResult":
        return cls(
            provider=provider,
            status="incomplete",
            completeness=None,
            ids=frozenset(),
            error_class=error_class,
            error_reason=error_reason,
        )

    @classmethod
    def unsupported(
        cls, provider: str, error_class: str, error_reason: str
    ) -> "QueryResult":
        return cls(
            provider=provider,
            status="unsupported",
            completeness=None,
            ids=frozenset(),
            error_class=error_class,
            error_reason=error_reason,
        )
