"""Provenance stamp — identifies the exact code that ran.

A bare HEAD commit is a lie when the working tree has uncommitted changes (as it
did for run 1, whose runner was uncommitted). This reports:
  - `<commit>`                      when the tree is clean
  - `<commit>+dirty:<12-hex>`       when `git status --porcelain` is non-empty,
                                    where the suffix is a short sha256 of the
                                    `git diff HEAD` output.

Pure over an injected git-command runner: `run(args: list[str]) -> str`.
"""

from __future__ import annotations

import hashlib
from typing import Callable


def provenance(run: Callable[[list], str]) -> str:
    commit = run(["rev-parse", "HEAD"]).strip()
    porcelain = run(["status", "--porcelain"])
    if not porcelain.strip():
        return commit
    diff = run(["diff", "HEAD"])
    digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:12]
    return f"{commit}+dirty:{digest}"
