"""Item 10 driver: scan every tracked file (decompressing .gz in memory) with the
pure scanner, and summarize hits, repo size, and the 10 largest files.

Prints a categorized dump. Non-fixture hits are what we may need to fix; fixture
hits are listed for a human decision (fixtures are dated evidence, never edited).

Run:  .venv/bin/python scripts/scan_repo.py
"""

from __future__ import annotations

import gzip
import pathlib
import socket
import subprocess
import sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from probe.scrub import scan  # noqa: E402

ROOT = HERE.parent
HOSTNAME = socket.gethostname()


def tracked_files():
    out = subprocess.check_output(["git", "ls-files"], text=True, cwd=ROOT)
    return [l for l in out.splitlines() if l]


def read_text(path: pathlib.Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".gz":
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
    return data.decode("utf-8", "replace")


def main():
    files = tracked_files()
    per_file = {}
    fixture_cat = Counter()
    nonfixture_cat = Counter()
    sizes = []
    for rel in files:
        p = ROOT / rel
        if not p.exists():
            continue
        sizes.append((p.stat().st_size, rel))
        hits = scan(read_text(p), hostname=HOSTNAME)
        if hits:
            per_file[rel] = hits
            is_fix = rel.startswith("fixtures/")
            for h in hits:
                (fixture_cat if is_fix else nonfixture_cat)[h["category"]] += 1

    print(f"hostname scanned for: {HOSTNAME!r}")
    print(f"tracked files: {len(files)}")
    total = sum(s for s, _ in sizes)
    print(f"total tracked size: {total} bytes ({total/1024/1024:.1f} MB)")
    print("\n10 largest tracked files:")
    for s, rel in sorted(sizes, reverse=True)[:10]:
        print(f"  {s:>10}  {rel}")

    print(f"\nNON-FIXTURE hit categories: {dict(nonfixture_cat)}")
    print(f"FIXTURE hit categories:     {dict(fixture_cat)}")

    print("\n=== NON-FIXTURE hits (candidates to fix) ===")
    for rel in sorted(per_file):
        if rel.startswith("fixtures/"):
            continue
        print(f"\n-- {rel} --")
        for h in per_file[rel]:
            print(f"  L{h['line']} [{h['category']}] {h['match']!r}  …{h['snippet']!r}")

    print("\n=== FIXTURE hits (collapsed: file -> category -> count) ===")
    fix_summary = defaultdict(Counter)
    fix_examples = defaultdict(dict)
    for rel in sorted(per_file):
        if not rel.startswith("fixtures/"):
            continue
        for h in per_file[rel]:
            fix_summary[rel][h["category"]] += 1
            fix_examples[rel].setdefault(h["category"], h)
    for rel in sorted(fix_summary):
        cats = dict(fix_summary[rel])
        print(f"  {rel}: {cats}")
        for cat, ex in fix_examples[rel].items():
            print(f"      e.g. [{cat}] {ex['match']!r} …{ex['snippet'][:60]!r}")


if __name__ == "__main__":
    main()
