"""Tests for the static site generator.

Runs the generator against the REAL committed fixtures (network-free) and asserts
that key values appear, that progressive enhancement holds, and that the page
loads no external resource.
"""

import pathlib
import re

from scripts.build_site import CNAME, FIXTURE_LINKS, load_data, render

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
    """No resource that triggers a network fetch on load.

    Inline <script> and inline <svg> are allowed (they make no request);
    external scripts, stylesheets, fonts, images, and CSS url(http...) are not.
    Anchor links to GitHub (<a href="https...">) are fine — they only fetch on
    click, so they are not counted here.
    """
    html = render(load_data(ROOT))
    low = html.lower()
    for bad in (
        "<script src", "<script type=\"text/javascript\" src",
        "<img", "<link", "@import", "url(http", "url('http", 'url("http',
        "fonts.googleapis", "fonts.gstatic", "srcset",
        "<iframe", "<video", "<audio", "<object", "<embed", "@font-face",
    ):
        assert bad not in low, f"external-resource marker present: {bad}"
    # every <script> is inline — no src attribute on any script tag
    for tag in re.findall(r"<script[^>]*>", low):
        assert "src" not in tag, f"script has src attribute: {tag}"


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


# ---------------- Item 12: design system + scroll framework ----------------

def test_all_six_section_ids_and_hero_present():
    html = render(load_data(ROOT))
    for sid in ("hero", "sec-1", "sec-2", "sec-3", "sec-4", "sec-5", "sec-6"):
        assert f'id="{sid}"' in html, f"missing section id: {sid}"


def test_reduced_motion_media_query_present():
    html = render(load_data(ROOT))
    assert "prefers-reduced-motion" in html
    # a reduce block must actually neutralise animation/transition
    assert "animation" in html and "transition" in html


def test_depth_gauge_links_to_every_section():
    """The depth gauge nav is keyboard-reachable: real anchor links, one per section."""
    html = render(load_data(ROOT))
    assert 'class="gauge"' in html or "gauge" in html
    for n in range(1, 7):
        assert f'href="#sec-{n}"' in html, f"gauge missing link to sec-{n}"


def test_reveal_is_hidden_only_under_js_class():
    """Progressive enhancement: reveal-hiding CSS must be scoped to a JS-only
    class on the root element, so content is fully visible when JS is off."""
    html = render(load_data(ROOT))
    # the hiding rule must be qualified by the js flag class, never global
    assert re.search(r"\.js-anim[^{]*\.reveal\b[^{]*\{[^}]*opacity\s*:\s*0", html), (
        "reveal elements must only be hidden under the .js-anim root class"
    )
    # a bare `.reveal{opacity:0}` (unqualified) would break the no-JS view
    assert not re.search(r"(^|[},])\s*\.reveal\s*\{[^}]*opacity\s*:\s*0", html), (
        "found an unqualified .reveal opacity:0 rule (breaks no-JS view)"
    )


def test_key_numbers_present_as_static_text_not_only_js():
    """Counters animate toward values that are ALSO present as static text."""
    html = render(load_data(ROOT))
    # strip inline <script> blocks: the numbers must survive with JS removed
    without_js = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    for token in ("32", "1416"):
        assert token in without_js, f"{token} missing from no-JS static text"


def test_counters_carry_their_target_as_visible_text():
    """A count-up element shows its final value even before/without animation:
    data-count target equals the element's own text content."""
    html = render(load_data(ROOT))
    for m in re.finditer(r'data-count="([0-9]+)"[^>]*>([^<]*)<', html):
        target, shown = m.group(1), m.group(2).strip().replace(",", "")
        assert shown == target, f"counter shows {shown!r} but targets {target!r}"


def test_no_js_view_contains_all_section_headings():
    """With every <script> removed, all six section headings remain."""
    html = render(load_data(ROOT))
    without_js = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    for heading in ("verdict", "Findings", "Method", "Limits", "Evidence", "Correction"):
        assert heading in without_js, f"heading {heading!r} missing from no-JS view"


# ---------------- Item 13: hero + section 1 ----------------

def _section(html, sid):
    """Slice out one <section id="sid"> ... </section> block."""
    m = re.search(rf'<section id="{sid}".*?</section>', html, flags=re.DOTALL)
    assert m, f"section {sid} not found"
    return m.group(0)


def test_hero_has_plimsoll_mark_on_the_waterline():
    html = render(load_data(ROOT))
    hero = _section_or_hero(html, "hero")
    assert 'class="buoy"' in hero, "hero missing waterline Plimsoll buoy mark"
    # the buoy is a Plimsoll mark: circle + bisecting line inside the hero SVG scene
    assert "<circle" in hero and "<line" in hero


def _section_or_hero(html, sid):
    m = re.search(rf'<section id="{sid}".*?</section>', html, flags=re.DOTALL)
    assert m, f"section {sid} not found"
    return m.group(0)


def test_section1_shows_four_ships_one_per_provider():
    d = load_data(ROOT)
    html = render(d)
    sec1 = _section(html, "sec-1")
    ships = re.findall(r'class="ship\b', sec1)
    assert len(ships) == 4, f"expected 4 ships, found {len(ships)}"
    # each ship is labelled with a provider id read from the fixtures
    for provider in d["cfg"]["providers"]:
        assert provider in sec1, f"ship label missing provider {provider}"


def test_section1_ships_share_one_waterline():
    """Agreement is drawn as four ships level on a single waterline."""
    html = render(load_data(ROOT))
    sec1 = _section(html, "sec-1")
    assert 'class="waterline"' in sec1 or "waterline" in sec1


def test_section1_has_refuted_ink_stamp():
    d = load_data(ROOT)
    html = render(d)
    sec1 = _section(html, "sec-1")
    m = re.search(r'class="stamp"[^>]*>(.*?)</', sec1, flags=re.DOTALL)
    assert m, "no REFUTED ink stamp element in section 1"
    assert d["verdict"] in m.group(1), "stamp does not carry the verdict text"


def test_section1_countups_target_agreed_values():
    d = load_data(ROOT)
    html = render(d)
    sec1 = _section(html, "sec-1")
    targets = set(re.findall(r'data-count="([0-9]+)"', sec1))
    assert str(d["q1_count"]) in targets, "Q1 count-up missing in section 1"
    assert str(d["q1b_count"]) in targets, "Q1b count-up missing in section 1"


# ---------------- Item 14: section 2 finding micro-visuals ----------------

def test_finding_a_terminal_shows_dated_evidence_not_a_live_site_error():
    from html import unescape

    d = load_data(ROOT)
    sec2 = _section(render(d), "sec-2")
    match = re.search(r'<figure class="terminal".*?</figure>', sec2, flags=re.DOTALL)
    assert match, "no archived response figure"
    fig = match.group(0)
    fixture = (ROOT / "fixtures" / "mysten_fullnode_jsonrpc_2026-09-27.md").read_text()
    request_match = re.search(r"^- Request: `(.+)`$", fixture, re.MULTILINE)
    time_match = re.search(r"^- UTC: (.+)$", fixture, re.MULTILINE)
    assert request_match and time_match
    request = json.loads(request_match.group(1))
    recorded_at = time_match.group(1)

    # The displayed request must be the request that actually produced the evidence.
    assert request["method"] in fig
    assert "suix_queryEvents" not in fig
    payload = re.search(r'class="term-request"[^>]*>(.*?)</code>', fig, re.DOTALL)
    assert payload
    assert json.loads(unescape(payload.group(1))) == request
    assert recorded_at in fig
    assert "Recorded response" in fig
    assert "not a live request or a website error" in fig
    assert "mysten_fullnode_jsonrpc_2026-09-27.md" in fig
    assert d["msg_32601"] in unescape(fig)
    assert "-32601" in fig
    assert 'class="type"' not in fig, "typing animation makes historical evidence look live"


def test_finding_b_module_vs_event_type_diagram():
    sec2 = _section(render(load_data(ROOT)), "sec-2")
    assert 'class="diagram"' in sec2, "no MoveModule-vs-type diagram"
    for token in ("called module", "event type", "0x2::coin", "deny_list"):
        assert token in sec2, f"diagram missing {token!r}"


def test_finding_c_sonar_scan_budget_trap():
    sec2 = _section(render(load_data(ROOT)), "sec-2")
    assert 'class="sonar"' in sec2, "no sonar sweep visual"
    for token in ("0 nodes", "hasNextPage", "not empty"):
        assert token in sec2, f"sonar missing {token!r}"
    # The paragraph itself must distinguish documented behaviour from observations;
    # the chart caption's substitute disclosure is not enough.
    paragraph = re.search(r"scan-budget trap:.*?</h3>\s*<p>(.*?)</p>", sec2,
                          flags=re.DOTALL).group(1)
    text = " ".join(re.sub(r"<[^>]+>", "", paragraph).split())
    for claim in (
        "Documented GraphQL behaviour",
        "The client code in this spike is built to handle this behaviour",
        "no such page occurred in the recorded runs",
        "Keep paginating while the cursor advances",
        "treat a stalled cursor (no advance) as an incomplete, unknown result",
        "never as an empty set",
    ):
        assert claim in text, f"scan-budget paragraph missing {claim!r}"


def test_finding_d_timeline_shows_ms_drift_from_fixtures():
    d = load_data(ROOT)
    sec2 = _section(render(d), "sec-2")
    assert 'class="timeline"' in sec2, "no timestamp-drift timeline"
    tl = re.search(r'class="timeline".*?</figure>', sec2, flags=re.DOTALL).group(0)
    assert str(d["ts"]["lag_min"]) in tl, "timeline missing lag_min (ms) from fixtures"
    assert str(d["ts"]["lag_max"]) in tl, "timeline missing lag_max (ms) from fixtures"
    assert "ms" in tl
    # labelled per the item-8 conclusion: GraphQL matches the chain, legacy is late
    assert "checkpoint" in tl.lower() and "json-rpc" in tl.lower()


def test_finding_e_route_map_blocked_and_open_channel():
    sec2 = _section(render(load_data(ROOT)), "sec-2")
    assert 'class="route"' in sec2, "no route-map visual"
    for token in ("Invalid params", "cursor"):
        assert token in sec2, f"route map missing {token!r}"
    # a blocked channel and an open one
    assert "blocked" in sec2.lower() and "open" in sec2.lower()


# ---------------- Item 15: sections 3-6 ----------------

def test_section3_pipeline_stages_in_order():
    sec3 = _section(render(load_data(ROOT)), "sec-3")
    assert 'class="pipeline"' in sec3, "no pipeline visual"
    stages = ["providers", "pagination", "identity match", "self-consistency", "verdict"]
    positions = [sec3.lower().find(s) for s in stages]
    assert all(p >= 0 for p in positions), f"missing pipeline stage: {stages}"
    assert positions == sorted(positions), "pipeline stages out of order"


def test_section3_pipeline_nodes_light_in_sequence_only_under_js():
    """Nodes are fully visible by default; the staggered light-up is JS-only."""
    html = render(load_data(ROOT))
    # the lit state is gated behind .js-anim so no-JS keeps every node visible
    assert re.search(r"\.js-anim[^{]*\.pipe-node", html), (
        "pipeline light-up must be scoped under .js-anim"
    )


def test_section4_loadline_gauge_marks_each_limit():
    sec4 = _section(render(load_data(ROOT)), "sec-4")
    assert 'class="loadline"' in sec4, "no vertical Plimsoll load-line gauge"
    marks = re.findall(r'class="ll-mark', sec4)
    assert len(marks) >= 5, f"expected a mark per limit, found {len(marks)}"


def test_section5_cargo_manifest_links_every_fixture():
    sec5 = _section(render(load_data(ROOT)), "sec-5")
    assert 'class="manifest"' in sec5, "no cargo-manifest grid"
    cards = re.findall(r'class="manifest-card', sec5)
    assert len(cards) == len(FIXTURE_LINKS), (
        f"manifest has {len(cards)} cards, expected {len(FIXTURE_LINKS)}"
    )
    for _label, path in FIXTURE_LINKS:
        assert f"/{path}" in sec5, f"manifest missing GitHub link for {path}"


def test_section6_amendment_strikes_old_and_writes_corrected():
    d = load_data(ROOT)
    sec6 = _section(render(d), "sec-6")
    assert 'class="amendment"' in sec6, "no ship's-log amendment"
    struck = re.search(r'class="struck"[^>]*>(.*?)</p>', sec6, flags=re.DOTALL)
    corrected = re.search(r'class="corrected"[^>]*>(.*?)</p>', sec6, flags=re.DOTALL)
    assert struck, "no struck-through old claim"
    assert corrected, "no corrected claim written beneath"
    assert "partial" in struck.group(1).lower() or "stale" in struck.group(1).lower()


def test_section6_strike_animation_is_js_only():
    """The strike-through draws under JS; with JS off the old claim is already
    struck (line-through) and the correction already written."""
    html = render(load_data(ROOT))
    assert re.search(r"\.js-anim[^{]*\.struck", html), "strike animation must be JS-scoped"


# ---------------- Item 17: real latency chart (section 1) ----------------
# These tests re-parse the committed run files INDEPENDENTLY of build_site and
# recompute every expected value, so a hardcoded chart cannot pass them.

import gzip  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import statistics  # noqa: E402

PROVIDERS = ("mysten_graphql", "publicnode", "blockvision", "rpcpool")


def _fixture_latencies():
    """Every latency_ms on every observation row of both committed runs."""
    out = {p: [] for p in PROVIDERS}
    for run in ("run1", "run2"):
        path = ROOT / "fixtures" / f"premise_2026-09-27_{run}.jsonl.gz"
        with gzip.open(path, "rt") as f:
            for line in f:
                r = json.loads(line)
                if r.get("kind") == "observation" and r.get("latency_ms") is not None:
                    out[r["provider"]].append(r["latency_ms"])
    return out


def _latency_fig(html):
    m = re.search(r'<figure class="latency".*?</figure>', html, flags=re.DOTALL)
    assert m, "no latency chart figure"
    return m.group(0)


def _lat_row(fig, provider):
    m = re.search(rf'<div class="lat-row" data-provider="{provider}".*?</svg>', fig,
                  flags=re.DOTALL)
    assert m, f"no latency row for {provider}"
    return m.group(0)


def test_latency_chart_in_section1_has_one_row_per_provider():
    sec1 = _section(render(load_data(ROOT)), "sec-1")
    fig = _latency_fig(sec1)
    rows = re.findall(r'class="lat-row" data-provider="([a-z_]+)"', fig)
    assert sorted(rows) == sorted(PROVIDERS)


def test_latency_row_stats_match_fixture_values():
    fig = _latency_fig(render(load_data(ROOT)))
    for p, vals in _fixture_latencies().items():
        q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
        row = _lat_row(fig, p)
        assert f'data-n="{len(vals)}"' in row, p
        assert f'data-min="{min(vals):.1f}"' in row, p
        assert f'data-q1="{q1:.1f}"' in row, p
        assert f'data-median="{med:.1f}"' in row, p
        assert f'data-q3="{q3:.1f}"' in row, p
        assert f'data-max="{max(vals):.1f}"' in row, p


def test_latency_svg_coordinates_are_log_mapped_from_fixture():
    """The median tick and range line x-coords are log10(ms) mapped onto a
    0..1000 viewBox across whole decades spanning the fixture min..max."""
    lat = _fixture_latencies()
    allv = [v for vs in lat.values() for v in vs]
    lo = math.floor(math.log10(min(allv)))
    hi = math.ceil(math.log10(max(allv)))

    def x(v):
        return f"{1000 * (math.log10(v) - lo) / (hi - lo):.1f}"

    fig = _latency_fig(render(load_data(ROOT)))
    for p, vals in lat.items():
        med = statistics.median(vals)
        row = _lat_row(fig, p)
        assert f'<line class="lat-med" x1="{x(med)}" x2="{x(med)}"' in row, p
        assert f'<line class="lat-range" x1="{x(min(vals))}" x2="{x(max(vals))}"' in row, p


def test_latency_axis_labelled_in_ms_with_decade_ticks():
    lat = _fixture_latencies()
    allv = [v for vs in lat.values() for v in vs]
    lo = math.floor(math.log10(min(allv)))
    hi = math.ceil(math.log10(max(allv)))
    fig = _latency_fig(render(load_data(ROOT)))
    assert "latency_ms" in fig or "latency (ms)" in fig
    for k in range(lo, hi + 1):
        assert f"{10 ** k:,} ms" in fig, f"missing axis tick {10 ** k:,} ms"


# ---------------- Item 18: real pagination step chart (finding c) ----------------
# No committed row or raw body records a 0-node + hasNextPage:true page, so the
# chart shows the real Q1b full-history GraphQL scan from run 1 instead. These
# tests rebuild that page sequence independently from the committed raw bodies.

Q1B_TYPE = "0x2::deny_list::PerTypeConfigCreated"


def _fixture_q1b_pages():
    pages = []
    with gzip.open(ROOT / "fixtures" / "premise_2026-09-27_run1.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            p = r.get("params") or {}
            if (r.get("kind") == "observation" and r["provider"] == "mysten_graphql"
                    and isinstance(p, dict) and "first" in p
                    and p.get("filter", {}).get("type") == Q1B_TYPE):
                with gzip.open(ROOT / "fixtures" / r["raw_path"], "rt") as b:
                    ev = json.load(b)["data"]["events"]
                pages.append((len(ev["nodes"]), ev["pageInfo"]["hasNextPage"]))
    return pages


def _pager_fig(html):
    m = re.search(r'<figure class="sonar".*?</figure>', html, flags=re.DOTALL)
    assert m, "no sonar/pagination figure"
    return m.group(0)


def test_fixture_q1b_scan_really_has_no_empty_trap_page():
    """Guards the caption's honesty claim: the substitute scan has no 0-node page."""
    pages = _fixture_q1b_pages()
    assert pages and all(n > 0 for n, _ in pages)
    assert sum(n for n, _ in pages) == 1416


def test_pager_step_path_is_drawn_from_real_page_sizes():
    from scripts.build_site import PG_X0, PG_X1, PG_Y0, PG_Y1

    pages = _fixture_q1b_pages()
    total = sum(n for n, _ in pages)
    n = len(pages)

    def x(i):
        return f"{PG_X0 + (PG_X1 - PG_X0) * i / n:.1f}"

    def y(c):
        return f"{PG_Y0 - (PG_Y0 - PG_Y1) * c / total:.1f}"

    cum, d = 0, f"M{x(0)},{y(0)}"
    for i, (k, _) in enumerate(pages, start=1):
        cum += k
        d += f" V{y(cum)} H{x(i)}"
    fig = _pager_fig(_section(render(load_data(ROOT)), "sec-2"))
    assert f'<path class="seabed" d="{d}"' in fig


def test_pager_per_page_markers_carry_real_counts():
    pages = _fixture_q1b_pages()
    fig = _pager_fig(render(load_data(ROOT)))
    assert f'data-pages="{len(pages)}"' in fig
    cum = 0
    for i, (k, nxt) in enumerate(pages, start=1):
        cum += k
        assert (f'data-page="{i}" data-nodes="{k}" data-cum="{cum}" '
                f'data-has-next="{str(nxt).lower()}"') in fig, i


def test_pager_caption_says_it_is_a_substitute_and_cites_source():
    fig = _pager_fig(render(load_data(ROOT)))
    assert "substitute" in fig.lower()
    assert "Q1b" in fig and Q1B_TYPE in fig
    assert "run 1" in fig and "2026-09-27" in fig
    assert "fixtures/raw/2026-09-27_run1/" in fig


def test_pager_axes_are_labelled():
    fig = _pager_fig(render(load_data(ROOT)))
    assert "page" in fig and "cumulative events" in fig


def test_pager_replay_controls_keep_recorded_final_values_without_js():
    pages = _fixture_q1b_pages()
    fig = _pager_fig(render(load_data(ROOT)))
    total = sum(nodes for nodes, _ in pages)
    assert "Recorded replay" in fig
    assert "not live" in fig
    assert "Playback timing is illustrative" in fig
    assert 'class="pg-controls" hidden' in fig
    for control in ("pg-play", "pg-restart", "pg-slider"):
        assert f'class="{control}"' in fig
    assert f'min="1" max="{len(pages)}" value="{len(pages)}"' in fig
    assert f'class="pg-page">{len(pages)}</span>' in fig
    assert f'class="pg-nodes">{pages[-1][0]}</span>' in fig
    assert f'class="pg-total">{total:,}</span>' in fig
    assert 'class="pg-next">false</span>' in fig
    assert 'class="pg-head"' in fig
    assert 'id="q1b-page"' in fig and 'for="q1b-page"' in fig
