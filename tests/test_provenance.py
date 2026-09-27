"""Tests for provenance — a pure function over a git-command runner.

Run 1 rows recorded a probe_commit (HEAD) that did NOT contain the runner code
that actually ran (it was uncommitted). Provenance must instead report
`<commit>` for a clean tree, or `<commit>+dirty:<short diff hash>` when there are
uncommitted changes, so a stamp always identifies the exact code that ran.
"""

from probe.provenance import provenance


def _fake_git(head, porcelain, diff):
    def run(args):
        if args[:2] == ["rev-parse", "HEAD"]:
            return head + "\n"
        if args[:2] == ["status", "--porcelain"]:
            return porcelain
        if args[:2] == ["diff", "HEAD"]:
            return diff
        raise AssertionError(f"unexpected git args {args}")
    return run


def test_clean_tree_is_bare_commit():
    run = _fake_git("abc123def456", porcelain="", diff="")
    assert provenance(run) == "abc123def456"


def test_clean_tree_ignores_trailing_whitespace_in_status():
    run = _fake_git("abc123def456", porcelain="   \n", diff="")
    assert provenance(run) == "abc123def456"


def test_dirty_tree_appends_dirty_and_diff_hash():
    run = _fake_git("abc123def456", porcelain=" M scripts/run.py\n", diff="some diff text")
    result = provenance(run)
    assert result.startswith("abc123def456+dirty:")
    h = result.split(":", 1)[1]
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_dirty_diff_hash_is_stable_and_content_dependent():
    a = provenance(_fake_git("c0", " M a\n", diff="diff ONE"))
    b = provenance(_fake_git("c0", " M a\n", diff="diff ONE"))
    c = provenance(_fake_git("c0", " M a\n", diff="diff TWO"))
    assert a == b            # same diff -> same hash
    assert a != c            # different diff -> different hash
