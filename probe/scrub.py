"""Public-release scanner — a pure function flagging likely secrets, PII, local
paths, private IPs, and a given hostname in text.

It errs toward over-reporting (the word "secret" is flagged even in prose); a
human decides what is a real leak vs a legitimate keyword. `scan` is pure: the
hostname to look for is passed in, not read from the machine.
"""

from __future__ import annotations

import re
from typing import List, Optional

# category -> list of compiled patterns
_PATTERNS = {
    "token": [
        re.compile(r"gho_[A-Za-z0-9]{4,}"),
        re.compile(r"ghp_[A-Za-z0-9]{4,}"),
        re.compile(r"\bsk-[A-Za-z0-9]{4,}"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
        re.compile(r"(?i)api[_-]?key"),
        re.compile(r"(?i)secret"),
        re.compile(r"(?i)password"),
    ],
    "local_path": [
        re.compile(r"/Users/"),
        re.compile(r"/home/"),
        re.compile(r"/private/tmp"),
    ],
    "email": [
        re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    ],
    "private_ip": [
        re.compile(
            r"\b(?:"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|169\.254\.\d{1,3}\.\d{1,3}"
            r")\b"
        ),
    ],
}


def scan(text: str, hostname: Optional[str] = None) -> List[dict]:
    """Return hits: [{category, line, match, snippet}], line 1-indexed."""
    hits: List[dict] = []
    lines = text.split("\n")
    patterns = dict(_PATTERNS)
    if hostname:
        patterns = {**patterns, "hostname": [re.compile(re.escape(hostname))]}
    for i, line in enumerate(lines, start=1):
        for category, pats in patterns.items():
            for pat in pats:
                for m in pat.finditer(line):
                    start = max(0, m.start() - 20)
                    end = min(len(line), m.end() + 20)
                    hits.append({
                        "category": category,
                        "line": i,
                        "match": m.group(0),
                        "snippet": line[start:end],
                    })
    return hits
