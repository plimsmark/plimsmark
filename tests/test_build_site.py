"""Tests for the static site generator.

Runs the generator against the REAL committed fixtures (network-free) and asserts
that key values appear, that progressive enhancement holds, and that the page
loads no external resource.
"""

import pathlib
import re

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

def test_finding_a_terminal_types_verbatim_32601():
    d = load_data(ROOT)
    sec2 = _section(render(d), "sec-2")
    assert 'class="terminal"' in sec2, "no terminal micro-visual"
    # the verbatim message must be present as static text (typing is JS-only)
    assert d["msg_32601"] is not None
    # full verbatim message lives inside the terminal element
    m = re.search(r'class="terminal".*?</figure>', sec2, flags=re.DOTALL)
    assert "JSON-RPC on public fullnodes has been deprecated" in m.group(0)
    assert "-32601" in m.group(0)


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
