"""Tests for the static site generator.

Runs the generator against the REAL committed fixtures (network-free) and asserts
that key values appear and that the page loads no external resource.
"""

import pathlib

from scripts.build_site import CNAME, load_data, render

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_reads_q1_and_q1b_counts_from_fixtures():
    d = load_data(ROOT)
    assert d["q1_count"] == 32
    assert d["q1b_count"] == 1416


def test_html_contains_verdict_and_key_counts():
    html = render(load_data(ROOT))
    assert "REFUTED" in html
    assert "32" in html
    assert "1416" in html


def test_html_contains_both_run_time_ranges():
    d = load_data(ROOT)
    html = render(d)
    assert d["run1"]["started"] in html
    assert d["run1"]["ended"] in html
    assert d["run2"]["started"] in html
    assert d["run2"]["ended"] in html


def test_page_references_no_external_resource():
    html = render(load_data(ROOT)).lower()
    for bad in ("<script", "<img", "<link", "@import", "url(http", "fonts.googleapis", "srcset"):
        assert bad not in html, f"external-resource marker present: {bad}"


def test_quotes_verbatim_32601_message():
    html = render(load_data(ROOT))
    assert "-32601" in html
    assert "JSON-RPC on public fullnodes has been deprecated" in html


def test_lists_all_four_providers():
    html = render(load_data(ROOT))
    for p in ("mysten_graphql", "publicnode", "blockvision", "rpcpool"):
        assert p in html


def test_cname_is_exact_domain():
    assert CNAME == "plimsmark.com"
