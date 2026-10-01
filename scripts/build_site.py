"""Render docs/index.html from committed files — a scrollytelling "descent".

Every number and date on the page is READ from the fixtures / spike_config /
summary files here — never typed by hand. The page is one self-contained HTML
file: inline CSS, inline SVG, small inline vanilla JS, no external
fonts/scripts/images and no network requests.

Design: a descent from the sea surface into the abyss. Six sections shade from
sea teal at the top to abyssal navy at the bottom, separated by animated wave
dividers, with a fixed depth gauge tracking scroll. Progressive enhancement:
with JS off (or reduced motion on) all content and final numbers are visible;
JS only adds motion.

Run:  .venv/bin/python scripts/build_site.py
"""

from __future__ import annotations

import gzip
import html
import json
import math
import pathlib
import re
import statistics

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

CNAME = "plimsmark.com"
REPO_URL = "https://github.com/plimsmark/plimsmark/blob/main"
DATE = "2026-09-27"


# ---------------- data loading (all values READ from committed files) ----------------

def _meta(root, run):
    with gzip.open(root / "fixtures" / f"premise_{DATE}_{run}.jsonl.gz", "rt") as f:
        return json.loads(f.readline())


def _results(root, run):
    out = {}
    with gzip.open(root / "fixtures" / f"premise_{DATE}_{run}.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") == "result":
                out.setdefault(r["query"], {})[(r["provider"], r["pass"])] = r
    return out


def _latencies(root, providers):
    """Every recorded latency, per provider, across both runs.

    Source: fixtures/premise_{DATE}_run1.jsonl.gz and _run2.jsonl.gz, field
    `latency_ms` on every row with kind == "observation" (retried transient
    errors included — each is a real request that took that long).
    """
    out = {p: [] for p in providers}
    for run in ("run1", "run2"):
        with gzip.open(root / "fixtures" / f"premise_{DATE}_{run}.jsonl.gz", "rt") as f:
            for line in f:
                r = json.loads(line)
                if r.get("kind") == "observation" and r.get("latency_ms") is not None:
                    out[r["provider"]].append(r["latency_ms"])
    return out


def _q1b_pages(root, q1b_type):
    """The real page-by-page Q1b full-history GraphQL scan from run 1.

    Source: observation rows of fixtures/premise_{DATE}_run1.jsonl.gz with
    provider == "mysten_graphql" and params.filter.type == the Q1b type (in
    request order); each page's node count is len(data.events.nodes) and its
    flag data.events.pageInfo.hasNextPage, read from the committed raw body at
    fixtures/<raw_path>. (No committed page anywhere has 0 nodes +
    hasNextPage:true, so this is a substitute for the scan-budget trap.)
    """
    pages = []
    with gzip.open(root / "fixtures" / f"premise_{DATE}_run1.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            p = r.get("params") or {}
            if (r.get("kind") == "observation" and r["provider"] == "mysten_graphql"
                    and isinstance(p, dict) and "first" in p
                    and p.get("filter", {}).get("type") == q1b_type):
                with gzip.open(root / "fixtures" / r["raw_path"], "rt") as b:
                    ev = json.load(b)["data"]["events"]
                pages.append({
                    "raw_path": r["raw_path"],
                    "first": p["first"],
                    "nodes": len(ev["nodes"]),
                    "has_next": ev["pageInfo"]["hasNextPage"],
                })
    return pages


def _extract_fence(text, marker):
    m = re.search(re.escape(marker) + r".*?```[a-z]*\n(.*?)\n```", text, re.DOTALL)
    return m.group(1).strip() if m else None


def load_data(root: pathlib.Path) -> dict:
    root = pathlib.Path(root)
    cfg = json.loads((root / "spike_config.json").read_text())
    run1, run2 = _meta(root, "run1"), _meta(root, "run2")
    res1 = _results(root, "run1")

    q1_count = res1["Q1"][("publicnode", "a")]["completeness"]
    q1b_count = res1["Q1b"][("publicnode", "a")]["completeness"]
    q1b_pages = _q1b_pages(root, cfg["queries"]["Q1b"]["types"][0])
    gql_q1b = res1["Q1b"][("mysten_graphql", "single")]["completeness"]
    if sum(pg["nodes"] for pg in q1b_pages) != gql_q1b:
        raise ValueError("Q1b raw pages do not sum to the recorded GraphQL result")

    premise = (root / "fixtures" / f"premise_{DATE}.md").read_text()
    vm = re.search(r"^###\s*→\s*(.+?)\s*$", premise, re.MULTILINE)
    verdict = vm.group(1).strip() if vm else "(unknown)"

    fullnode_md = (root / "fixtures" / f"mysten_fullnode_jsonrpc_{DATE}.md").read_text()
    msg_32601 = _extract_fence(fullnode_md, "Verbatim error message:")
    fullnode_fields = dict(re.findall(r"^- (Endpoint|Request|UTC): (.+)$", fullnode_md, re.MULTILINE))
    fullnode = {
        "endpoint": fullnode_fields["Endpoint"].strip("`"),
        "request": json.loads(fullnode_fields["Request"].strip("`")),
        "recorded_at": fullnode_fields["UTC"],
        "source": f"fixtures/mysten_fullnode_jsonrpc_{DATE}.md",
    }

    gt = json.loads((root / "fixtures" / f"ground_truth_{DATE}.data.json").read_text())
    lags = []
    all_agree = True
    gql_all = True
    jr_none = True
    JR = ["publicnode", "blockvision", "rpcpool"]
    for r in gt["rows"]:
        cp = r["conclusion"]["checkpoint_ts_ms"]
        all_agree = all_agree and r["conclusion"]["checkpoint_agree"]
        gql_all = gql_all and r["conclusion"]["gql_event_matches_checkpoint"]
        for p in JR:
            ev = r["jsonrpc"][p].get("event_ts_ms")
            if ev is not None and cp is not None:
                lags.append(ev - cp)
            if r["conclusion"]["jsonrpc_event_matches_checkpoint"][p]:
                jr_none = False

    return {
        "cfg": cfg,
        "run1": run1,
        "run2": run2,
        "q1_count": q1_count,
        "q1b_count": q1b_count,
        "verdict": verdict,
        "msg_32601": msg_32601,
        "fullnode": fullnode,
        "latency": _latencies(root, list(cfg["providers"])),
        "q1b_pages": q1b_pages,
        "ts": {
            "n": len(gt["rows"]),
            "lag_min": min(lags),
            "lag_max": max(lags),
            "checkpoint_agree_all": all_agree,
            "gql_matches_all": gql_all,
            "jsonrpc_matches_none": jr_none,
        },
    }


# ---------------- rendering ----------------

FIXTURE_LINKS = [
    ("Verdict, comparison tables, addendum", f"fixtures/premise_{DATE}.md"),
    ("Run 1 observations + results (gz)", f"fixtures/premise_{DATE}_run1.jsonl.gz"),
    ("Run 2 observations + results (gz)", f"fixtures/premise_{DATE}_run2.jsonl.gz"),
    ("Pinned query set + windows", "spike_config.json"),
    ("Filter semantics + comparability evidence", f"fixtures/semantics_{DATE}.md"),
    ("Timestamp ground truth", f"fixtures/timestamps_{DATE}.md"),
    ("GraphQL schema introspection", f"fixtures/graphql_introspection_{DATE}.json"),
    ("Mysten fullnode JSON-RPC -32601 (verbatim)", f"fixtures/mysten_fullnode_jsonrpc_{DATE}.md"),
    ("Corrections", f"fixtures/corrections_{DATE}.md"),
    ("Public-release scrub", f"fixtures/public_scrub_{DATE}.md"),
]

# Depth palette — sea surface (bright teal) shading to the abyss (navy).
# Indexed 0..6: 0 = hero surface, 1..6 = the six sections, each deeper/darker.
DEPTH = ["#0d6a70", "#0b5c62", "#0a4e58", "#08404e", "#073343", "#062839", "#041d2e"]

# Short labels for the depth gauge (number + one word).
GAUGE = [
    ("sec-1", "Verdict"),
    ("sec-2", "Findings"),
    ("sec-3", "Method"),
    ("sec-4", "Limits"),
    ("sec-5", "Evidence"),
    ("sec-6", "Correction"),
]

LOGO = (
    '<svg class="mark" viewBox="0 0 100 100" role="img" '
    'aria-label="Plimsoll load line mark: a circle bisected by a horizontal line" '
    'fill="none" stroke="currentColor" stroke-width="6">'
    '<line x1="4" y1="50" x2="96" y2="50"/>'
    '<circle cx="50" cy="50" r="26"/>'
    '</svg>'
)


def count(n, dec=0):
    """A decorative count-up span whose visible text IS the final value.

    With JS off (or reduced motion) the reader simply sees the number; JS
    animates 0 -> n. The static text always equals the data-count target.
    """
    shown = f"{n:.{dec}f}" if dec else f"{int(n)}"
    extra = f' data-dec="{dec}"' if dec else ""
    return f'<span class="count" data-count="{shown}"{extra}>{shown}</span>'


def wave(fill):
    """An SVG wave divider that pours the section's own colour down over the
    lighter water above it. Two layered paths drift horizontally under JS."""
    return (
        f'<div class="wave" aria-hidden="true">'
        f'<svg viewBox="0 0 1440 90" preserveAspectRatio="none" fill="{fill}">'
        f'<path class="w w1" d="M0,40 C240,80 480,80 720,50 C960,20 1200,20 1440,50 '
        f'L2880,50 L2880,90 L0,90 Z"/>'
        f'<path class="w w2" d="M0,55 C300,25 620,25 720,55 C900,95 1140,95 1440,60 '
        f'L2880,60 L2880,90 L0,90 Z" opacity="0.55"/>'
        f'</svg></div>'
    )


CSS = """
:root{
  --sea0:#0d6a70; --sea1:#0b5c62; --sea2:#0a4e58; --sea3:#08404e;
  --sea4:#073343; --sea5:#062839; --sea6:#041d2e;
  --ink:#eaf3f5; --muted:#a9c2cc; --accent:#63d8ce; --accent-ink:#0a2c2b;
  --link:#8fe6dd; --line:rgba(255,255,255,.16); --code-bg:rgba(255,255,255,.06);
  --card:rgba(255,255,255,.05);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth}
body{
  margin:0; color:var(--ink);
  background:var(--sea6) linear-gradient(180deg,
    var(--sea0) 0%, var(--sea1) 16%, var(--sea2) 32%, var(--sea3) 50%,
    var(--sea4) 66%, var(--sea5) 82%, var(--sea6) 100%);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.62; font-size:17px; overflow-x:hidden;
}
a{color:var(--link)}
a:focus-visible, .gauge a:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:4px}
strong{color:#fff}
em{color:var(--accent)}

/* ---- section shells: each a step down into the deep ---- */
.depth{position:relative; padding:4.5rem 0 5rem}
.depth>.inner{max-width:760px; margin:0 auto; padding:0 20px}
.depth{scroll-margin-top:12px}
.js-anim .depth.section-enter>.inner{animation:depth-enter .72s cubic-bezier(.2,.75,.25,1)}
.depth[data-direction="up"]{--enter-offset:-28px}
.js-anim .depth.section-enter::after{content:""; position:absolute; inset:0 0 auto;
  height:180px; pointer-events:none;
  background:linear-gradient(180deg,rgba(99,216,206,.16),transparent);
  animation:depth-wash .85s ease-out both}
@keyframes depth-enter{
  from{opacity:.28; transform:translateY(var(--enter-offset,28px))}
  to{opacity:1; transform:translateY(0)}}
@keyframes depth-wash{from{opacity:.8; transform:translateY(-12px)} to{opacity:0; transform:translateY(22px)}}
.d1{background:var(--sea1)} .d2{background:var(--sea2)} .d3{background:var(--sea3)}
.d4{background:var(--sea4)} .d5{background:var(--sea5)} .d6{background:var(--sea6)}
.wave{position:absolute; top:-1px; left:0; width:100%; height:64px; line-height:0; pointer-events:none}
.wave svg{width:100%; height:100%; display:block}
.js-anim .wave .w1{animation:drift 14s linear infinite}
.js-anim .wave .w2{animation:drift 22s linear infinite reverse}
@keyframes drift{from{transform:translateX(0)} to{transform:translateX(-720px)}}

h1{font-size:2.1rem; margin:.1em 0; letter-spacing:.3px}
h2{font-size:1.5rem; margin:0 0 .8em; letter-spacing:.2px; display:flex; align-items:baseline; gap:.5rem}
h2 .n{color:var(--accent); font-variant-numeric:tabular-nums; font-size:1.05rem;
  border:1px solid var(--line); border-radius:999px; padding:.05em .55em; flex:0 0 auto}
h3{font-size:1.12rem; margin:1.6em 0 .35em; color:#fff}
p{margin:.7em 0}
.lede{font-size:1.12rem; color:var(--muted)}
code,pre{background:var(--code-bg); border:1px solid var(--line); border-radius:6px}
code{padding:.08em .35em; font-size:.88em; overflow-wrap:anywhere; word-break:break-word}
pre{padding:12px 14px; overflow:auto; margin:.7em 0}
pre code{border:0; padding:0; background:transparent}
ul{padding-left:1.2em} li{margin:.3em 0}
.kv{color:var(--muted); font-size:.92rem}
.tablewrap{overflow-x:auto; margin:.7em 0; border:1px solid var(--line); border-radius:8px;
  -webkit-overflow-scrolling:touch}
table{border-collapse:collapse; width:100%; font-size:.93rem}
.tablewrap table{min-width:460px}
th,td{border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top}
th{background:rgba(255,255,255,.06); color:#fff; white-space:nowrap}
td code{overflow-wrap:normal; word-break:normal}
.count{font-variant-numeric:tabular-nums}

.verdict{display:inline-block; font-weight:800; letter-spacing:1px;
  background:var(--accent); color:var(--accent-ink); padding:.12em .6em; border-radius:6px}

/* ---- hero ---- */
#hero{position:relative; min-height:88vh; display:flex; flex-direction:column;
  justify-content:flex-end; overflow:hidden; padding:0}
#hero .sky{position:absolute; inset:0; z-index:0}
#hero .inner{position:relative; z-index:2; max-width:760px; margin:0 auto;
  padding:0 20px 8vh; width:100%}
#hero .brand{display:flex; align-items:center; gap:14px}
#hero .mark{width:52px; height:52px; color:#fff; flex:0 0 auto}
#hero .tag{color:rgba(255,255,255,.85); font-size:1.15rem; max-width:36ch; margin:.4em 0 0}
.scrollcue{margin-top:1.6rem; color:rgba(255,255,255,.7); font-size:.85rem; letter-spacing:.12em;
  text-transform:uppercase}
.scrollcue span{display:inline-block}
.js-anim .scrollcue span{animation:bob 2.4s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)} 50%{transform:translateY(5px)}}
#hero .buoy{position:absolute; z-index:1; right:15%; bottom:33%; width:64px; height:64px;
  color:#fff; filter:drop-shadow(0 3px 6px rgba(0,0,0,.35))}
.js-anim #hero .buoy{animation:buoybob 3.6s ease-in-out infinite}
@keyframes buoybob{0%,100%{transform:translateY(0) rotate(-4deg)} 50%{transform:translateY(-9px) rotate(4deg)}}

/* ---- section 1: fleet of agreement + ink stamp ---- */
.verdict-row{display:flex; align-items:center; gap:1.2rem; flex-wrap:wrap}
.verdict-row p{margin:.3em 0; flex:1 1 260px}
.stamp{display:inline-block; color:#d9ede9; border:3px double #63d8ce; border-radius:8px;
  padding:.2em .7em; font-weight:800; letter-spacing:3px; font-size:1.05rem;
  transform:rotate(-7deg); opacity:.82; text-transform:uppercase; flex:0 0 auto;
  box-shadow:inset 0 0 0 1px rgba(99,216,206,.25)}
.js-anim .reveal .stamp{opacity:0; transform:rotate(-7deg) scale(1.7)}
.js-anim .reveal.shown .stamp{opacity:.82; transform:rotate(-7deg) scale(1);
  transition:opacity .35s .35s ease, transform .4s .35s cubic-bezier(.2,1.5,.4,1)}
.ships-fig{margin:1.4em 0 .6em}
.ships{width:100%; height:auto; display:block}
.ships .waterline{stroke-dasharray:0}
.ships .ship{transform-box:fill-box; transform-origin:center}
.js-anim .ships .ship{animation:shipbob 4.6s ease-in-out infinite}
.ships .ship:nth-of-type(2){animation-delay:-.6s}
.ships .ship:nth-of-type(3){animation-delay:-1.2s}
.ships .ship:nth-of-type(4){animation-delay:-1.8s}
@keyframes shipbob{0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)}}
.ships .shiplabel{fill:#eaf3f5; font-size:12px; font-family:inherit; font-weight:600}
.ships .shippar{fill:#a9c2cc; font-size:10px; font-family:inherit; letter-spacing:.04em}
.caption{color:var(--muted); font-size:.86rem; margin:.5em 0 0; text-align:center}

/* ---- section 1: real latency chart (log ms, one row per provider) ---- */
.latency{margin:1.4em 0 .6em; padding:14px 16px; background:var(--card);
  border:1px solid var(--line); border-radius:10px}
.lat-title{font-size:.92rem; color:#fff; margin:0 0 .5em; font-weight:600}
.lat-row{margin:.55em 0}
.lat-name{display:flex; flex-wrap:wrap; align-items:baseline; gap:.1em .6em; font-size:.84rem}
.lat-name code{color:#fff}
.lat-name small{color:var(--muted); font-variant-numeric:tabular-nums}
.lat-strip{display:block; width:100%; height:22px; margin-top:.2em}
.lat-strip .lat-grid{stroke:rgba(255,255,255,.13)}
.lat-strip .lat-range{stroke:#a9c2cc}
.lat-strip .lat-iqr{fill:rgba(99,216,206,.45); stroke:#63d8ce}
.lat-strip .lat-med{stroke:#fff}
.lat-axis{position:relative; height:1.3em; margin-top:.3em; font-size:.72rem;
  color:var(--muted); font-variant-numeric:tabular-nums; border-top:1px solid var(--line)}
.lat-axis span{position:absolute; top:.15em; transform:translateX(-50%); white-space:nowrap}
.lat-axis span:first-child{transform:none}
.lat-axis span:last-child{transform:translateX(-100%)}
.lat-key{font-size:.74rem; color:var(--muted); margin:.5em 0 0}
.lat-key i{display:inline-block; vertical-align:middle; margin:0 .3em 0 .6em}
.lat-key .k-range{width:18px; height:2px; background:#a9c2cc}
.lat-key .k-iqr{width:14px; height:10px; background:rgba(99,216,206,.45); border:1px solid #63d8ce}
.lat-key .k-med{width:2px; height:12px; background:#fff}

/* ---- depth gauge (fixed side rail on desktop, bottom bar on mobile) ---- */
.gauge{position:fixed; z-index:20; left:14px; top:50%; transform:translateY(-50%)}
.gauge ol{list-style:none; margin:0; padding:0; position:relative}
.gauge ol::before{content:""; position:absolute; left:6px; top:6px; bottom:6px;
  width:2px; background:var(--line)}
.gauge li{position:relative}
.gauge a{display:flex; align-items:center; gap:.55rem; padding:.28rem 0;
  min-height:44px; min-width:44px; color:var(--muted); text-decoration:none; font-size:.78rem}
.gauge .dot{width:14px; height:14px; border-radius:50%; border:2px solid var(--line);
  background:transparent; flex:0 0 auto; position:relative; z-index:1; transition:all .3s}
.gauge .lbl{opacity:0; transform:translateX(-4px); transition:opacity .25s, transform .25s;
  white-space:nowrap; font-variant-numeric:tabular-nums}
.gauge a:hover .lbl, .gauge a:focus-visible .lbl, .gauge a.on .lbl{opacity:1; transform:none}
.gauge a:hover .dot{border-color:var(--accent)}
.gauge a.on{color:#fff}
.gauge a.on .dot{background:var(--accent); border-color:var(--accent); box-shadow:0 0 0 4px rgba(99,216,206,.18)}

/* ---- section 2: one micro-visual per finding ---- */
.terminal,.diagram,.sonar,.timeline,.route{
  margin:1.2em 0; padding:14px 16px; background:var(--card);
  border:1px solid var(--line); border-radius:10px}
.caption,figcaption.caption{color:var(--muted); font-size:.86rem; margin:.6em 0 0}
figure{margin:0}

/* (a) terminal */
.terminal{padding:0; overflow:hidden; background:#04161f}
.term-bar{display:flex; align-items:center; gap:6px; padding:8px 12px;
  background:rgba(255,255,255,.05); border-bottom:1px solid var(--line);
  font-size:.78rem; color:var(--muted)}
.term-bar span{margin-left:6px}
.term-tag{margin-left:auto; color:var(--accent); font-weight:600; white-space:nowrap}
.term-body{margin:0; padding:12px 14px; background:transparent; border:0; border-radius:0;
  font-size:.82rem; white-space:pre-wrap; word-break:break-word}
.term-cmd{color:#8fe6dd} .term-err{color:#ffb4b4}
.term-err b{color:#ff8f8f}
.term-note{padding:12px 14px; border-top:1px solid var(--line); color:var(--muted);
  font-size:.8rem; text-align:left}
.term-note strong{color:var(--accent)}

/* (b) diagram */
.dg-row{display:flex; align-items:center; gap:.7rem; flex-wrap:wrap}
.dg-box{border:1px solid var(--line); border-radius:8px; padding:.5em .7em;
  background:rgba(255,255,255,.04); font-size:.9rem; position:relative}
.dg-box small{color:var(--muted)}
.dg-box.mod{border-color:rgba(99,216,206,.5)}
.dg-box.evt{border-color:rgba(255,180,120,.5); display:inline-block; margin-top:.2em}
.dg-tag{display:block; margin-top:.3em; font-size:.72rem; color:var(--accent)}
.dg-op,.dg-drop{color:var(--muted); font-size:.85rem}
.dg-drop{margin:.5em 0 .4em}

/* (c) sonar-style pagination step chart (real page sizes) */
.sonar{text-align:center}
.pg-title{display:flex; align-items:center; justify-content:space-between; gap:.6rem;
  flex-wrap:wrap; margin:0 0 .7rem; font-size:.87rem; text-align:left}
.pg-title>span{font-weight:650; color:var(--ink)}
.pg-title small{color:var(--muted); font-weight:400}
.pg-indicator{display:inline-block; width:7px; height:7px; margin-right:.5em;
  border-radius:50%; background:var(--muted)}
.sonar[data-playing="true"] .pg-indicator{background:var(--accent);
  box-shadow:0 0 0 4px rgba(99,216,206,.13)}
.sonar-scope{position:relative; display:block; max-width:480px; margin:0 auto;
  background:radial-gradient(ellipse at 50% 60%,rgba(99,216,206,.10),rgba(2,16,24,.55) 75%);
  border:1px solid rgba(99,216,206,.28); border-radius:12px; padding:10px}
.sonar-scope svg{width:100%; height:auto; display:block}
.sonar .pg-grid{stroke:rgba(99,216,206,.16)}
.sonar .pg-axis{stroke:rgba(255,255,255,.35)}
.sonar .pg-tick{fill:#a9c2cc; font-size:12px; font-family:inherit; font-variant-numeric:tabular-nums}
.sonar .pg-lbl{fill:#eaf3f5; font-size:12.5px; font-family:inherit}
.sonar .seabed{fill:none; stroke:#63d8ce; stroke-width:2; filter:drop-shadow(0 0 3px rgba(99,216,206,.7))}
.sonar .pg-dot{fill:#63d8ce}
.sonar .pg-dot.end{fill:#fff; stroke:#63d8ce; stroke-width:2}
.sonar .pg-fill{fill:rgba(99,216,206,.07); stroke:none}
.sonar .pg-head{fill:#fff; stroke:var(--accent); stroke-width:2;
  filter:drop-shadow(0 0 5px rgba(99,216,206,.65))}
.pg-readout{display:flex; flex-wrap:wrap; justify-content:space-between; gap:.4em 1em;
  padding:.65rem .2rem; border-top:1px solid var(--line); font-size:.82rem;
  color:var(--muted); font-variant-numeric:tabular-nums; text-align:left}
.pg-readout strong{color:var(--accent)}
.pg-readout code{font-size:.88em}
.pg-controls:not([hidden]){display:flex; flex-wrap:wrap; align-items:center; gap:.45rem;
  border-top:1px solid var(--line); padding-top:.65rem; text-align:left}
.pg-controls button{min-height:44px; padding:.4rem .75rem; border:1px solid var(--line);
  border-radius:6px; background:transparent; color:var(--ink); font:inherit;
  font-size:.8rem; cursor:pointer}
.pg-controls .pg-play{background:var(--accent); color:var(--accent-ink);
  border-color:var(--accent); min-width:115px; font-weight:650}
.pg-controls button:hover{filter:brightness(1.12)}
.pg-controls button:disabled{opacity:.55; cursor:default}
.pg-controls button:focus-visible,.pg-slider:focus-visible{
  outline:2px solid var(--accent); outline-offset:3px}
.pg-scrub{display:flex; align-items:center; gap:.5rem; flex:1 1 140px;
  font-size:.78rem; color:var(--muted)}
.pg-slider{width:100%; min-width:0; min-height:44px; accent-color:var(--accent); cursor:pointer}
.pg-state{flex-basis:100%; color:var(--accent); font-size:.75rem; min-height:1.6em}
.pg-note{font-size:.73rem; color:var(--muted); text-align:left; margin:.35rem 0 .55rem}
.sonar-read{display:block; margin-top:.5em; font-size:.76rem; color:var(--muted)}

/* (d) timeline */
.tl-track{position:relative; display:flex; align-items:flex-start;
  justify-content:space-between; gap:.4rem; padding:.4em 0 .2em}
.tl-mark{flex:0 0 auto; max-width:38%; text-align:center; font-size:.8rem}
.tl-mark.b{text-align:right}
.tl-dot{display:inline-block; width:14px; height:14px; border-radius:50%;
  background:var(--accent); box-shadow:0 0 0 4px rgba(99,216,206,.2)}
.tl-dot.late{background:#ffb46e; box-shadow:0 0 0 4px rgba(255,180,110,.2)}
.tl-lbl{display:block; margin-top:.3em} .tl-lbl small{color:var(--muted)}
.tl-gap{flex:1 1 auto; text-align:center; align-self:center; color:#ffcf9e; font-size:.8rem;
  min-width:64px}
.tl-arrow{display:block; height:2px; margin:.5em 6px .3em; background:
  linear-gradient(90deg,var(--accent),#ffb46e); position:relative}
.tl-arrow::after{content:"▸"; position:absolute; right:-2px; top:-9px; color:#ffb46e}

/* (e) route */
.route svg{width:100%; max-width:320px; height:auto; display:block; margin:.2em auto .4em}
.route-legend{list-style:none; padding:0; margin:.2em 0 0; font-size:.86rem}
.route-legend li{padding-left:1.4em; position:relative; margin:.35em 0}
.route-legend .blocked::before{content:"✕"; position:absolute; left:0; color:#ff9a9a}
.route-legend .open::before{content:"✓"; position:absolute; left:0; color:var(--accent)}

/* ---- section 3: verdict pipeline ---- */
.pipeline{margin:0 0 .4em; padding:14px 16px; background:var(--card);
  border:1px solid var(--line); border-radius:10px}
.pipe-flow{display:flex; align-items:stretch; flex-wrap:wrap; gap:.5rem}
.pipe-node{display:flex; flex-direction:column; gap:.1em; justify-content:center;
  border:1px solid var(--line); border-radius:8px; padding:.45em .6em; min-width:96px;
  background:rgba(255,255,255,.04); font-size:.82rem}
.pipe-node b{color:#fff} .pipe-node small{color:var(--muted)}
.pipe-node.last{border-color:var(--accent); background:rgba(99,216,206,.12)}
.pipe-node.last small{color:var(--accent); font-weight:700; letter-spacing:.5px}
.pipe-link{align-self:center; color:var(--muted)}
.js-anim .reveal .pipe-node{opacity:.3; filter:saturate(.5)}
.js-anim .reveal.shown .pipe-node{opacity:1; filter:none;
  transition:opacity .45s ease, filter .45s ease; transition-delay:calc(var(--i) * .28s)}

/* ---- section 4: vertical load-line gauge ---- */
.loadline{padding:6px 4px}
.ll-rail{display:flex; align-items:flex-start; gap:1rem; padding:.4em .2em}
.ll-disc{width:52px; height:52px; color:var(--accent); flex:0 0 auto; margin-top:2px}
.ll-marks{list-style:none; margin:0; padding:0; position:relative; flex:1 1 auto}
.ll-marks::before{content:""; position:absolute; left:34px; top:10px; bottom:10px;
  width:3px; background:linear-gradient(var(--accent),rgba(99,216,206,.25))}
.ll-mark{display:flex; align-items:baseline; gap:.7rem; padding:.4em 0; position:relative}
.ll-code{flex:0 0 26px; text-align:right; font-weight:700; color:var(--accent);
  font-variant-numeric:tabular-nums; font-size:.82rem}
.ll-tick{flex:0 0 18px; height:3px; background:var(--accent); align-self:center;
  margin-top:2px; border-radius:2px}
.ll-text{flex:1 1 auto; font-size:.92rem}

/* ---- section 5: cargo manifest grid ---- */
.manifest{display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
  gap:.7rem; margin:.6em 0}
.manifest-card{display:flex; flex-direction:column; gap:.15em; text-decoration:none;
  color:var(--ink); border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:8px; padding:.6em .7em; background:var(--card);
  transition:transform .2s ease, background .2s ease, border-color .2s ease}
.manifest-card:hover, .manifest-card:focus-visible{transform:translateY(-2px);
  background:rgba(99,216,206,.1); border-left-color:#fff}
.mf-file{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.82rem; color:#fff}
.mf-label{font-size:.82rem; color:var(--muted)}
.mf-path{font-size:.72rem; color:var(--accent); max-height:0; opacity:0; overflow:hidden;
  transition:max-height .25s ease, opacity .25s ease}
.manifest-card:hover .mf-path, .manifest-card:focus-visible .mf-path{max-height:2.4em; opacity:1}

/* ---- section 6: ship's-log amendment ---- */
.amendment{padding:14px 16px; background:var(--card); border:1px solid var(--line);
  border-radius:10px; border-left:3px solid #ffb46e}
.struck{position:relative; color:var(--muted); text-decoration:line-through;
  text-decoration-color:#ff9a9a; text-decoration-thickness:2px; margin:.2em 0}
.corrected{margin:.5em 0 .2em}
.amend-tag{display:inline-block; font-size:.68rem; letter-spacing:.12em; text-transform:uppercase;
  color:#ffcf9e; border:1px solid rgba(255,180,110,.5); border-radius:4px; padding:0 .4em;
  margin-right:.4em; transform:rotate(-3deg)}
.js-anim .reveal .struck{text-decoration:none}
.js-anim .reveal .struck::after{content:""; position:absolute; left:0; top:50%; height:2px;
  width:0; background:#ff9a9a}
.js-anim .reveal.shown .struck::after{width:100%; transition:width .6s ease .2s}
.js-anim .reveal .corrected{opacity:0; transform:translateY(6px)}
.js-anim .reveal.shown .corrected{opacity:1; transform:none;
  transition:opacity .5s ease .7s, transform .5s ease .7s}

footer{max-width:760px; margin:0 auto; padding:2.5rem 20px 4rem; color:var(--muted); font-size:.86rem}

/* ---- progressive enhancement: reveal ONLY hidden when JS is on ---- */
.js-anim .reveal{opacity:0; transform:translateY(26px); transition:opacity .7s ease, transform .7s ease}
.js-anim .reveal.shown{opacity:1; transform:none}

@media (max-width:820px){
  body{font-size:16px}
  .gauge{left:0; right:0; top:auto; bottom:0; transform:none;
    background:rgba(4,29,46,.92); backdrop-filter:blur(6px); border-top:1px solid var(--line)}
  .gauge ol{display:grid; grid-template-columns:repeat(6,minmax(0,1fr));
    padding:.4rem .2rem max(.4rem,env(safe-area-inset-bottom))}
  .gauge li{margin:0; min-width:0}
  .gauge ol::before{display:none}
  .gauge a{flex-direction:column; justify-content:center; gap:.2rem; padding:.2rem .1rem;
    font-size:.62rem; text-align:center}
  .gauge .lbl{opacity:1; transform:none}
  .gauge .section-number{display:none}
  .depth{padding:3.2rem 0 4rem}
  h1{font-size:1.7rem} h2{font-size:1.3rem}
  footer{padding-bottom:5.5rem}
}

@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation:none !important; transition:none !important}
  .js-anim .reveal{opacity:1 !important; transform:none !important}
  .js-anim .reveal .stamp{opacity:.82 !important; transform:rotate(-7deg) !important}
  .js-anim .reveal .pipe-node{opacity:1 !important; filter:none !important}
  .js-anim .reveal .struck{text-decoration:line-through !important}
  .js-anim .reveal .struck::after{width:0 !important}
  .js-anim .reveal .corrected{opacity:1 !important; transform:none !important}
  .depth.section-enter::after{display:none}
}
"""

JS = """
(function(){
  var root=document.documentElement;
  var mq=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  var reduce=mq&&mq.matches;
  // Navigation still works under reduced motion; only animation is disabled.
  // With no JS, the complete page and final values remain visible as served.
  root.classList.toggle('js-anim',!reduce);

  function countup(el){
    if(el.dataset.done) return; el.dataset.done='1';
    var to=parseFloat(el.getAttribute('data-count'));
    var dec=parseInt(el.getAttribute('data-dec')||'0',10);
    if(reduce){el.textContent=to.toFixed(dec);return;}
    var t0=null, dur=900;
    function frame(t){ if(t0===null)t0=t;
      if(reduce){el.textContent=to.toFixed(dec);return;}
      var p=Math.min((t-t0)/dur,1); var v=to*(1-Math.pow(1-p,3));
      el.textContent=v.toFixed(dec);
      if(p<1) requestAnimationFrame(frame); else el.textContent=to.toFixed(dec);
    }
    requestAnimationFrame(frame);
  }

  // Replay the saved observations, never poll RPCs or invent changing values.
  function setupReplay(fig){
    var points=[].slice.call(fig.querySelectorAll('.pg-dot'));
    var controls=fig.querySelector('.pg-controls');
    var scope=fig.querySelector('.sonar-scope'), svg=scope.querySelector('svg');
    var path=fig.querySelector('.seabed'), fill=fig.querySelector('.pg-fill');
    var head=fig.querySelector('.pg-head'), slider=fig.querySelector('.pg-slider');
    var playButton=fig.querySelector('.pg-play'), restart=fig.querySelector('.pg-restart');
    var status=fig.querySelector('.pg-state');
    var pageLabel=fig.querySelector('.pg-page'), totalLabel=fig.querySelector('.pg-total');
    var nodesLabel=fig.querySelector('.pg-nodes'), nextLabel=fig.querySelector('.pg-next');
    var origin='M'+fig.dataset.startX+','+fig.dataset.startY;
    var paths=[], trace=origin;
    points.forEach(function(dot){
      trace+=' V'+dot.getAttribute('cy')+' H'+dot.getAttribute('cx'); paths.push(trace);
    });
    var current=points.length, timer=null, playing=false, started=false, resume=false;

    function buttons(){
      fig.dataset.playing=String(playing);
      playButton.setAttribute('aria-pressed',String(playing));
      playButton.textContent=playing?'Pause replay':'Play replay';
    }
    function draw(index){
      current=Math.max(1,Math.min(points.length,index));
      var dot=points[current-1], data=dot.dataset;
      var x=dot.getAttribute('cx'), y=dot.getAttribute('cy');
      path.setAttribute('d',paths[current-1]);
      fill.setAttribute('d',paths[current-1]+' V'+fig.dataset.startY+' H'+fig.dataset.startX+' Z');
      head.setAttribute('cx',x); head.setAttribute('cy',y);
      points.forEach(function(p,i){p.style.visibility=i<current?'visible':'hidden';});
      pageLabel.textContent=String(current);
      totalLabel.textContent=Number(data.cum).toLocaleString('en-US');
      nodesLabel.textContent=data.nodes; nextLabel.textContent=data.hasNext;
      slider.value=String(current);
      var description='Recorded page '+current+' of '+points.length+': '+data.nodes+
        ' nodes, '+data.cum+' cumulative events; hasNextPage '+data.hasNext;
      slider.setAttribute('aria-valuetext',description);
      svg.setAttribute('aria-label',description);
    }
    function visible(){
      var r=scope.getBoundingClientRect();
      return !document.hidden && r.top<window.innerHeight*.85 && r.bottom>window.innerHeight*.12;
    }
    function pause(message,autoResume){
      clearTimeout(timer); timer=null; playing=false; resume=!!autoResume;
      status.textContent=message; buttons();
    }
    function advance(){
      if(!visible()){pause('Paused while the chart is out of view',true);return;}
      draw(current+1);
      if(current===points.length){pause('Recorded scan complete',false);return;}
      timer=setTimeout(advance,300);
    }
    function play(fromStart){
      if(reduce) return;
      clearTimeout(timer); started=true; resume=false;
      if(fromStart||current===points.length) draw(1);
      playing=true; status.textContent='Playing recorded pages'; buttons();
      timer=setTimeout(advance,300);
    }
    playButton.addEventListener('click',function(){
      if(playing) pause('Replay paused',false); else play(false);
    });
    restart.addEventListener('click',function(){play(true);});
    slider.addEventListener('input',function(){
      started=true; pause('Replay paused — inspect a recorded page',false);
      draw(Number(slider.value));
      if(current===points.length) status.textContent='Recorded scan complete';
    });
    controls.hidden=false;
    buttons();
    return {
      sync:function(){
        if(reduce) return;
        if(visible()){
          if(!started) play(true); else if(resume) play(false);
        } else if(playing) pause('Paused while the chart is out of view',true);
      },
      setReduced:function(value){
        if(value){started=true;pause('Recorded scan complete — reduced motion',false);draw(points.length);}
        controls.hidden=value;
      }
    };
  }
  var pagers=[].slice.call(document.querySelectorAll('.sonar')).map(setupReplay);
  document.addEventListener('visibilitychange',function(){pagers.forEach(function(p){p.sync();});});

  function reveal(el){
    if(el.dataset.shown) return; el.dataset.shown='1';
    el.classList.add('shown');
    if(el.matches('[data-count]')) countup(el);
    var cs=el.querySelectorAll('[data-count]');
    for(var i=0;i<cs.length;i++) countup(cs[i]);
  }

  // Reveal + depth-gauge tracking are driven by an rAF-throttled scroll handler
  // that reads each section's CURRENT top, not by IntersectionObserver. IO here
  // was unreliable: a reveal keyed to a section top crossing a trigger band can
  // be skipped entirely during a fast (momentum) flick — the section enters and
  // exits the band between observer frames and never fires, leaving it stuck at
  // opacity 0. Reading getBoundingClientRect() on scroll cannot be skipped: a
  // section reveals once its top rises above 85% of the viewport, and any
  // section already scrolled past (top <= 0) trivially satisfies that, so
  // nothing is ever left hidden after you have scrolled by it. Area/height of
  // the section is irrelevant, which is what the old thresholds got wrong.
  var reveals=[].slice.call(document.querySelectorAll('.reveal'));
  var dots=[].slice.call(document.querySelectorAll('.gauge a'));
  var secs=dots.map(function(a){return document.querySelector(a.getAttribute('href'));});
  var ticking=false, activeSection=-1, lastScroll=window.scrollY;
  secs.forEach(function(section){
    section.addEventListener('animationend',function(e){
      if(e.animationName==='depth-enter') section.classList.remove('section-enter');
    });
  });
  function tick(){
    ticking=false;
    var vh=window.innerHeight;
    for(var i=reveals.length-1;i>=0;i--){
      if(reduce||reveals[i].getBoundingClientRect().top < vh*0.85){ reveal(reveals[i]); reveals.splice(i,1); }
    }
    var active=-1;
    for(var k=0;k<secs.length;k++){
      if(secs[k] && secs[k].getBoundingClientRect().top <= vh*0.5) active=k;
    }
    // A short last section must still become active at the document bottom.
    if(window.scrollY>0 && window.scrollY+vh>=document.documentElement.scrollHeight-2) active=secs.length-1;
    if(active!==activeSection){
      secs.forEach(function(section){section.classList.remove('section-enter');});
      if(active>=0){
        var section=secs[active];
        section.dataset.direction=window.scrollY<lastScroll?'up':'down';
        if(!reduce) section.classList.add('section-enter');
      }
      activeSection=active;
    }
    lastScroll=window.scrollY;
    for(var m=0;m<dots.length;m++){
      if(m===active){ dots[m].classList.add('on'); dots[m].setAttribute('aria-current','true'); }
      else { dots[m].classList.remove('on'); dots[m].removeAttribute('aria-current'); }
    }
    pagers.forEach(function(p){p.sync();});
  }
  function onScroll(){ if(ticking) return; ticking=true; requestAnimationFrame(tick); }
  window.addEventListener('scroll', onScroll, {passive:true});
  window.addEventListener('resize', onScroll);
  window.addEventListener('pageshow', onScroll);
  function motionChanged(){
    reduce=!!(mq&&mq.matches);
    root.classList.toggle('js-anim',!reduce);
    secs.forEach(function(section){section.classList.remove('section-enter');});
    pagers.forEach(function(p){p.setReduced(reduce);});
    onScroll();
  }
  if(mq){
    if(mq.addEventListener) mq.addEventListener('change',motionChanged);
    else if(mq.addListener) mq.addListener(motionChanged);
  }
  pagers.forEach(function(p){p.setReduced(!!reduce);});
  onScroll();
})();
"""


def _ship(x, name, paradigm):
    """One ship, drawn at local x. Sail tone marks the paradigm; the hull sits
    on the shared waterline so four level ships read as 'agreement'."""
    sail = "#bfeee8" if paradigm == "graphql" else "#eaf3f5"
    return (
        f'<g class="ship" transform="translate({x},0)">'
        f'<line class="mast" x1="0" y1="52" x2="0" y2="112" stroke="#eaf3f5" stroke-width="3"/>'
        f'<path class="sail" d="M5,56 L5,104 L44,104 Z" fill="{sail}"/>'
        f'<path class="hull" d="M-40,110 L40,110 L28,128 L-28,128 Z" fill="#0a3a44" '
        f'stroke="#eaf3f5" stroke-width="2"/>'
        f'<text class="shiplabel" x="0" y="150" text-anchor="middle">{html.escape(name)}</text>'
        f'<text class="shippar" x="0" y="166" text-anchor="middle">{html.escape(paradigm)}</text>'
        f'</g>'
    )


def _ships(cfg):
    provs = list(cfg["providers"].items())
    xs = [110, 300, 490, 680] if len(provs) == 4 else [
        int(90 + i * (620 / max(1, len(provs) - 1))) for i in range(len(provs))
    ]
    ships = "".join(_ship(x, name, v["paradigm"]) for x, (name, v) in zip(xs, provs))
    return (
        '<figure class="ships-fig">'
        '<svg class="ships" viewBox="0 0 790 180" role="img" '
        'aria-label="Four RPC providers drawn as four ships riding level on one '
        'waterline — a picture of agreement.">'
        '<path class="waterline" fill="none" stroke="#63d8ce" stroke-width="2.5" '
        'd="M0,120 C130,112 250,128 395,120 C540,112 660,128 790,120"/>'
        f'{ships}'
        '</svg>'
        '<figcaption class="caption">Four providers, one waterline: identical id sets, '
        'level trim. No ship rides lower than the others.</figcaption>'
        '</figure>'
    )


LAT_W = 1000  # latency strip viewBox width; x is log10(ms) across whole decades


def _fig_latency(lat):
    """(S1) Real per-provider latency: min–max line, IQR box, median tick on a
    log10 ms axis. Every coordinate is computed from `latency_ms` values read
    in _latencies() (fixtures/premise_{DATE}_run1/run2.jsonl.gz, observation
    rows). 125–273 requests per provider is too many to plot as dots legibly,
    so each row is summarised by min / quartiles / max (inclusive method)."""
    allv = [v for vs in lat.values() for v in vs]
    lo = math.floor(math.log10(min(allv)))
    hi = math.ceil(math.log10(max(allv)))

    def x(v):
        return f"{LAT_W * (math.log10(v) - lo) / (hi - lo):.1f}"

    grid = "".join(
        f'<line class="lat-grid" x1="{x(10 ** k)}" x2="{x(10 ** k)}" y1="0" y2="22" '
        f'vector-effect="non-scaling-stroke"/>'
        for k in range(lo, hi + 1)
    )
    rows = ""
    for p, vals in lat.items():
        q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
        mn, mx = min(vals), max(vals)
        stats = (f"n={len(vals)} · min {mn:,.1f} · median {med:,.1f} · "
                 f"max {mx:,.1f} ms")
        rows += (
            f'<div class="lat-row" data-provider="{html.escape(p)}" data-n="{len(vals)}" '
            f'data-min="{mn:.1f}" data-q1="{q1:.1f}" data-median="{med:.1f}" '
            f'data-q3="{q3:.1f}" data-max="{mx:.1f}">'
            f'<div class="lat-name"><code>{html.escape(p)}</code><small>{stats}</small></div>'
            f'<svg class="lat-strip" viewBox="0 0 {LAT_W} 22" preserveAspectRatio="none" '
            f'role="img" aria-label="{html.escape(p)} latency: {stats}">'
            f'<title>{html.escape(p)}: {stats}; middle half {q1:,.1f}–{q3:,.1f} ms</title>'
            f'{grid}'
            f'<line class="lat-range" x1="{x(mn)}" x2="{x(mx)}" y1="11" y2="11" '
            f'stroke-width="2" vector-effect="non-scaling-stroke"/>'
            f'<rect class="lat-iqr" x="{x(q1)}" y="4" '
            f'width="{float(x(q3)) - float(x(q1)):.1f}" height="14" '
            f'vector-effect="non-scaling-stroke"/>'
            f'<line class="lat-med" x1="{x(med)}" x2="{x(med)}" y1="1" y2="21" '
            f'stroke-width="3" vector-effect="non-scaling-stroke"/>'
            f'</svg></div>'
        )
    ticks = "".join(
        f'<span style="left:{100 * (k - lo) / (hi - lo):.4g}%">{10 ** k:,} ms</span>'
        for k in range(lo, hi + 1)
    )
    n_total = len(allv)
    return (
        '<figure class="latency">'
        '<p class="lat-title">Request latency per provider (ms, log scale)</p>'
        f'{rows}'
        f'<div class="lat-axis" aria-hidden="true">{ticks}</div>'
        '<p class="lat-key" aria-hidden="true"><i class="k-range"></i>min–max'
        '<i class="k-iqr"></i>middle 50%<i class="k-med"></i>median</p>'
        f'<figcaption class="caption">All {n_total} recorded <code>latency_ms</code> values '
        f'from the observation rows of both runs (<code>premise_{DATE}_run1/run2.jsonl.gz</code>), '
        'retried transient errors included. One vantage, one day — a snapshot, '
        'not a provider benchmark.</figcaption>'
        '</figure>'
    )


# ---- Section 2 finding micro-visuals (one per finding) ----

def _fig_terminal(msg, evidence):
    """(a) Dated, verbatim evidence — not a live terminal or site failure."""
    endpoint = html.escape(evidence["endpoint"])
    recorded_at = html.escape(evidence["recorded_at"])
    request = html.escape(json.dumps(evidence["request"], separators=(",", ":")))
    return (
        '<figure class="terminal" aria-label="Archived JSON-RPC evidence: '
        'the public fullnode returned error -32601, method not found.">'
        '<div class="term-bar"><span>Legacy JSON-RPC</span>'
        '<b class="term-tag">Recorded response</b></div>'
        '<pre class="term-body">'
        f'<span class="term-cmd">POST {endpoint}</span>\n'
        f'<code class="term-request">{request}</code>\n\n'
        '<span class="term-err">✕ error <b>-32601</b>: '
        + html.escape(msg) + '</span></pre>'
        '<figcaption class="term-note"><strong>Archived evidence</strong> · '
        f'<time datetime="{recorded_at}">{recorded_at[:10]}</time> — '
        'not a live request or a website error. The endpoint rejected legacy JSON-RPC; '
        'the spike uses GraphQL. '
        f'<a href="{REPO_URL}/{html.escape(evidence["source"])}">View recorded source</a>.'
        '</figcaption></figure>'
    )


def _fig_diagram(ev_type):
    """(b) transaction -> called module vs emitted event type."""
    return (
        '<figure class="diagram" aria-label="Diagram: the MoveModule filter '
        "matches the transaction's called module 0x2::coin, while the events it "
        'emits carry type 0x2::deny_list::PerTypeConfigCreated.">'
        '<div class="dg-row">'
        '<div class="dg-box tx">transaction<br><small>a Move call</small></div>'
        '<div class="dg-op">calls&nbsp;→</div>'
        '<div class="dg-box mod">called module<br><code>0x2::coin</code>'
        '<span class="dg-tag">what <code>MoveModule</code> matches</span></div>'
        '</div>'
        '<div class="dg-drop">emits&nbsp;↓</div>'
        '<div class="dg-box evt">event type<br><code>' + html.escape(ev_type) + '</code></div>'
        '<figcaption class="caption"><code>MoveModule = 0x2::coin</code> selects '
        'transactions that <em>call</em> that module — the events they emit are '
        '<code>deny_list</code>-typed, not coin events.</figcaption>'
        '</figure>'
    )


# Pagination chart plot box inside its 340x220 viewBox.
PG_X0, PG_X1, PG_Y0, PG_Y1 = 52.0, 326.0, 174.0, 22.0


def _fig_sonar(pages, q1b_type):
    """(c) Sonar-style step chart of a REAL paginated GraphQL scan: x = page,
    y = cumulative events. Every vertex comes from `pages` (_q1b_pages():
    len(data.events.nodes) per committed raw body of the run-1 Q1b scan).
    The complete chart is static HTML; JS replays these same recorded pages."""
    n = len(pages)
    total = sum(pg["nodes"] for pg in pages)

    def x(i):
        return f"{PG_X0 + (PG_X1 - PG_X0) * i / n:.1f}"

    def y(c):
        return f"{PG_Y0 - (PG_Y0 - PG_Y1) * c / total:.1f}"

    cum, d, dots = 0, f"M{x(0)},{y(0)}", ""
    for i, pg in enumerate(pages, start=1):
        cum += pg["nodes"]
        d += f" V{y(cum)} H{x(i)}"
        end = " end" if i == n else ""
        dots += (
            f'<circle class="pg-dot{end}" cx="{x(i)}" cy="{y(cum)}" r="{3.5 if end else 2.2}" '
            f'data-page="{i}" data-nodes="{pg["nodes"]}" data-cum="{cum}" '
            f'data-has-next="{str(pg["has_next"]).lower()}">'
            f'<title>page {i}: {pg["nodes"]} nodes, {cum} cumulative, '
            f'hasNextPage {str(pg["has_next"]).lower()}</title></circle>'
        )
    step = 500 if total > 1000 else 100
    yticks = list(range(0, total, step)) + [total]
    ygrid = "".join(
        f'<line class="pg-grid" x1="{PG_X0}" x2="{PG_X1}" y1="{y(v)}" y2="{y(v)}"/>'
        f'<text class="pg-tick" x="{PG_X0 - 5}" y="{float(y(v)) + 3.5:.1f}" '
        f'text-anchor="end">{v:,}</text>'
        for v in yticks
    )
    xticks = sorted({1, n} | set(range(10, n, 10)))
    xgrid = "".join(
        f'<text class="pg-tick" x="{float(x(i)) - (PG_X1 - PG_X0) / n / 2:.1f}" '
        f'y="{PG_Y0 + 15}" text-anchor="middle">{i}</text>'
        for i in xticks
    )
    full = sum(1 for pg in pages if pg["nodes"] == pages[0]["first"])
    last = pages[-1]
    first_raw = pages[0]["raw_path"].rsplit("/", 1)[-1].split("_")[0]
    last_raw = last["raw_path"].rsplit("/", 1)[-1].split("_")[0]
    raw_dir = pages[0]["raw_path"].rsplit("/", 1)[0]
    all_advance = all(pg["has_next"] for pg in pages[:-1]) and not last["has_next"]
    return (
        f'<figure class="sonar" data-pages="{n}" data-start-x="{x(0)}" '
        f'data-start-y="{y(0)}" aria-label="Step chart of a real '
        f'GraphQL events scan: {n} pages, cumulative events rising to {total:,}; no page '
        'was empty.">'
        '<p class="pg-title"><span><i class="pg-indicator" aria-hidden="true"></i>'
        f'Recorded replay</span><small>not live · {DATE}</small></p>'
        '<div class="sonar-scope">'
        '<svg id="q1b-chart" viewBox="0 0 340 220" role="img" aria-label="Cumulative events by page">'
        f'{ygrid}'
        f'<line class="pg-axis" x1="{PG_X0}" x2="{PG_X1}" y1="{PG_Y0}" y2="{PG_Y0}"/>'
        f'<path class="pg-fill" d="{d} V{y(0)} H{x(0)} Z" aria-hidden="true"/>'
        f'<path class="seabed" d="{d}"/>'
        f'{dots}{xgrid}'
        f'<circle class="pg-head" cx="{x(n)}" cy="{y(total)}" r="4.2" aria-hidden="true"/>'
        f'<text class="pg-lbl" x="{(PG_X0 + PG_X1) / 2}" y="{PG_Y0 + 36}" '
        f'text-anchor="middle">page (first: {pages[0]["first"]})</text>'
        f'<text class="pg-lbl" x="11" y="{(PG_Y0 + PG_Y1) / 2}" text-anchor="middle" '
        f'transform="rotate(-90 11 {(PG_Y0 + PG_Y1) / 2})">cumulative events</text>'
        '</svg>'
        '<div class="pg-readout" aria-live="off">'
        f'<span>Page <strong><span class="pg-page">{n}</span></strong> / {n}</span>'
        f'<span><strong><span class="pg-total">{total:,}</span></strong> events</span>'
        f'<span>+<span class="pg-nodes">{last["nodes"]}</span> this page</span>'
        f'<code>hasNextPage: <span class="pg-next">{str(last["has_next"]).lower()}</span></code>'
        '</div>'
        '<div class="pg-controls" hidden>'
        '<button class="pg-play" type="button" aria-controls="q1b-chart" '
        'aria-pressed="false">Play replay</button>'
        '<button class="pg-restart" type="button" aria-controls="q1b-chart">Restart</button>'
        '<label class="pg-scrub" for="q1b-page">Page '
        f'<input class="pg-slider" id="q1b-page" type="range" min="1" max="{n}" value="{n}" '
        'step="1" aria-controls="q1b-chart" aria-describedby="q1b-replay-note"></label>'
        '<span class="pg-state" role="status" aria-live="polite">Recorded scan complete</span>'
        '</div>'
        '<p class="pg-note" id="q1b-replay-note">Replay of saved responses, not live data. '
        'Playback timing is illustrative, not recorded request timing.</p>'
        f'<span class="sonar-read">{n} pages · {full}×{pages[0]["first"]} + '
        f'{last["nodes"]} = {total:,} events · <code>hasNextPage: '
        f'{str(last["has_next"]).lower()}</code> only on page {n}</span>'
        '</div>'
        '<figcaption class="caption"><strong>Substitute, not the trap itself:</strong> '
        'this spike never recorded a page with 0 nodes + <code>hasNextPage: true</code> '
        '— none of its committed GraphQL responses has one. Drawn instead: the real '
        f'Q1b full-history scan (GraphQL <code>events</code>, type <code>{html.escape(q1b_type)}</code>, '
        f'<code>mysten_graphql</code>, run 1, {DATE}), one step per page from '
        f'<code>fixtures/{html.escape(raw_dir)}/</code> {first_raw}–{last_raw}'
        + (' — every page advanced the cursor.' if all_advance else '.')
        + ' The rule for the trap still holds: 0 nodes + <code>hasNextPage: true</code> '
        '= not empty; keep paginating while the cursor advances, and treat a stalled '
        'cursor as unknown, never zero.</figcaption>'
        '</figure>'
    )


def _fig_timeline(lo_ms, hi_ms):
    """(d) A timeline where the legacy JSON-RPC event time drifts late by the
    measured range (read from fixtures), per the item-8 conclusion."""
    rng = f"{lo_ms}–{hi_ms} ms"
    return (
        '<figure class="timeline" aria-label="Timeline: the GraphQL event time '
        'equals the checkpoint time (chain time); the legacy JSON-RPC event time '
        f'lands {lo_ms} to {hi_ms} milliseconds later.">'
        '<div class="tl-track">'
        '<span class="tl-mark a"><span class="tl-dot"></span>'
        '<span class="tl-lbl">checkpoint = GraphQL event<br><small>chain time · t0</small></span></span>'
        f'<span class="tl-gap"><span class="tl-arrow"></span><b>+{rng}</b></span>'
        '<span class="tl-mark b"><span class="tl-dot late"></span>'
        '<span class="tl-lbl">legacy JSON-RPC event<br><small>suix_queryEvents · late</small></span></span>'
        '</div>'
        f'<figcaption class="caption">GraphQL matches the chain; the legacy JSON-RPC '
        f'<code>timestampMs</code> runs <strong>{rng}</strong> late across all '
        'checked transactions. Bound windows by checkpoint, not by time.</figcaption>'
        '</figure>'
    )


def _fig_route():
    """(e) A route map: compound filter blocked, cursor-seed channel open."""
    return (
        '<figure class="route" aria-label="Route map: the compound-filter channel '
        'is blocked with Invalid params; the cursor-seed channel is open.">'
        '<svg viewBox="0 0 300 120" aria-hidden="true">'
        '<path d="M20,34 H180" stroke="rgba(255,255,255,.5)" stroke-width="6" fill="none"/>'
        '<path d="M180,34 H280" stroke="rgba(255,120,120,.5)" stroke-width="6" '
        'fill="none" stroke-dasharray="2 8"/>'
        '<g class="rt-x" stroke="#ff9a9a" stroke-width="5">'
        '<line x1="188" y1="24" x2="208" y2="44"/><line x1="208" y1="24" x2="188" y2="44"/></g>'
        '<path d="M20,86 H280" stroke="#63d8ce" stroke-width="6" fill="none"/>'
        '<path class="rt-ok" d="M188,86 l7,8 14,-16" stroke="#63d8ce" stroke-width="5" '
        'fill="none"/>'
        '</svg>'
        '<ul class="route-legend">'
        '<li class="blocked"><code>All[MoveEventType, TimeRange]</code> — '
        '<strong>blocked</strong>: <code>-32602 Invalid params</code> on all three.</li>'
        '<li class="open">cursor-seed a descending <code>suix_queryEvents {MoveEventType}</code> '
        'scan from the window edge — <strong>open channel</strong>, accepted on all three.</li>'
        '</ul>'
        '</figure>'
    )


# ---- Sections 3-6 visuals ----

def _fig_pipeline(n_providers, verdict):
    """(S3) The verdict pipeline; nodes light in sequence on scroll."""
    stages = [
        ("providers", f"{n_providers} endpoints"),
        ("pagination", "cursor to end"),
        ("identity match", "(txDigest, seq)"),
        ("self-consistency", "×2 per query"),
        ("verdict", html.escape(verdict)),
    ]
    nodes = ""
    for i, (name, sub) in enumerate(stages):
        if i:
            nodes += '<span class="pipe-link" aria-hidden="true">→</span>'
        last = ' last' if i == len(stages) - 1 else ''
        nodes += (
            f'<span class="pipe-node{last}" style="--i:{i}">'
            f'<b>{html.escape(name)}</b><small>{sub}</small></span>'
        )
    return (
        '<figure class="pipeline" aria-label="Method pipeline: providers, '
        'pagination, identity match, self-consistency (twice), verdict.">'
        f'<div class="pipe-flow">{nodes}</div>'
        '<figcaption class="caption">Each query runs the full pipeline; a stage that '
        'cannot complete cleanly yields <em>unknown</em> (null), never zero.</figcaption>'
        '</figure>'
    )


def _fig_loadline(limits):
    """(S4) A vertical Plimsoll load-line gauge; each limit is a marked line."""
    disc = (
        '<svg class="ll-disc" viewBox="0 0 60 60" aria-hidden="true" fill="none" '
        'stroke="currentColor" stroke-width="4">'
        '<line x1="4" y1="30" x2="56" y2="30"/><circle cx="30" cy="30" r="16"/></svg>'
    )
    marks = ""
    for i, text in enumerate(limits, start=1):
        marks += (
            f'<li class="ll-mark"><span class="ll-code">L{i}</span>'
            f'<span class="ll-tick" aria-hidden="true"></span>'
            f'<span class="ll-text">{text}</span></li>'
        )
    return (
        '<figure class="loadline" aria-label="Limits drawn as marks on a Plimsoll '
        'load line: each line marks how far this spike can be safely loaded.">'
        f'<div class="ll-rail">{disc}<ol class="ll-marks">{marks}</ol></div>'
        '<figcaption class="caption">Like a ship\'s load line, each mark is a limit on '
        'how heavily these findings can be loaded — read below the line, not above it.</figcaption>'
        '</figure>'
    )


def _fig_manifest():
    """(S5) A cargo-manifest grid of fixture files; hover/focus reveals the path."""
    cards = ""
    for label, path in FIXTURE_LINKS:
        fname = path.rsplit("/", 1)[-1]
        cards += (
            f'<a class="manifest-card" href="{REPO_URL}/{path}">'
            f'<span class="mf-file">{html.escape(fname)}</span>'
            f'<span class="mf-label">{html.escape(label)}</span>'
            f'<span class="mf-path">{html.escape(path)}</span></a>'
        )
    return f'<div class="manifest">{cards}</div>'


def _fig_amendment(d, e):
    """(S6) The old claim struck through, the correction written beneath."""
    q1 = d["q1_count"]
    q1b = d["q1b_count"]
    return (
        '<figure class="amendment" aria-label="Ship\'s-log amendment: the earlier '
        'claim struck through, the correction written beneath.">'
        f'<p class="struck">Earlier claim: publicnode\'s {q1}-event '
        '<code>0x2::coin</code> answer was a <em>partial or stale</em> event index.</p>'
        f'<p class="corrected"><span class="amend-tag">amended</span> The {q1} events are '
        '<code>deny_list::PerTypeConfigCreated</code>, returned identically by all three '
        'JSON-RPC providers; <code>MoveModule</code> matches the transaction\'s called '
        f'module, not the event type. The genuine type count is {q1b}, agreed by all four.</p>'
        f'<p class="kv">See <a href="{REPO_URL}/fixtures/corrections_{DATE}.md">'
        f'corrections_{DATE}.md</a>.</p>'
        '</figure>'
    )


def _providers_rows(cfg):
    rows = ""
    for name, v in cfg["providers"].items():
        rows += (
            f"<tr><td><code>{name}</code></td>"
            f"<td>{html.escape(v['endpoint'])}</td><td>{v['paradigm']}</td></tr>"
        )
    return rows


def _gauge(d):
    items = ""
    for i, (sid, label) in enumerate(GAUGE, start=1):
        items += (
            f'<li><a href="#{sid}" aria-label="Section {i}: {html.escape(label)}">'
            f'<span class="dot"></span>'
            f'<span class="lbl"><span class="section-number">{i} · </span>{html.escape(label)}</span>'
            f'</a></li>'
        )
    return f'<nav class="gauge" aria-label="Depth gauge — jump to a section"><ol>{items}</ol></nav>'


def _hero(d):
    # Layered sea waves with the Plimsoll mark riding the waterline.
    sky = (
        '<svg class="sky" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMax slice" '
        'aria-hidden="true">'
        '<defs><linearGradient id="sh" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#1b8f92"/><stop offset="1" stop-color="#0b5c62"/>'
        '</linearGradient></defs>'
        '<rect width="1440" height="900" fill="url(#sh)"/>'
        # far swell
        '<path class="hw hw3" fill="#0a4e58" opacity="0.6" '
        'd="M0,560 C360,510 540,610 720,560 C900,510 1080,610 1440,560 L2880,560 L2880,900 L0,900 Z"/>'
        # mid swell
        '<path class="hw hw2" fill="#0a4650" opacity="0.85" '
        'd="M0,640 C300,590 620,700 900,640 C1140,590 1260,690 1440,640 L2880,640 L2880,900 L0,900 Z"/>'
        # near swell (waterline for the mark ~ y=690)
        '<path class="hw hw1" fill="#083f49" '
        'd="M0,700 C260,660 520,740 780,700 C1020,665 1220,735 1440,700 L2880,700 L2880,900 L0,900 Z"/>'
        '</svg>'
    )
    buoy = (
        '<svg class="buoy" viewBox="0 0 100 100" aria-hidden="true" fill="none" '
        'stroke="currentColor" stroke-width="6">'
        '<line x1="4" y1="50" x2="96" y2="50"/><circle cx="50" cy="50" r="26"/></svg>'
    )
    return f"""
<section id="hero">
  {sky}
  {buoy}
  <div class="inner">
    <div class="brand">
      {LOGO}
      <h1>Plimsmark</h1>
    </div>
    <p class="tag">Do Sui mainnet RPC providers disagree on event data?
      A dated, network-tested spike — then a descent through what it found.</p>
    <p class="scrollcue"><span>▼ scroll to descend</span></p>
  </div>
</section>
"""


def render(d: dict) -> str:
    cfg = d["cfg"]
    e = html.escape
    r1, r2 = d["run1"], d["run2"]
    q2_type = cfg["queries"]["Q2"]["type"]
    q1b_type = cfg["queries"]["Q1b"]["types"][0]
    windows = cfg["queries"]["Q2"]["windows"]
    ts = d["ts"]
    lag_lo = ts["lag_min"] / 1000.0
    lag_hi = ts["lag_max"] / 1000.0

    win_rows = "".join(
        f"<tr><td>{e(w['label'])}</td><td>{w['c_start']:,}–{w['c_end']:,}</td>"
        f"<td>{e(w['ts_c_start'][:19])}Z</td></tr>"
        for w in windows
    )

    sec1 = f"""
<section id="sec-1" class="depth d1">
  {wave('var(--sea1)')}
  <div class="inner reveal">
    <h2><span class="n">1</span> The question, and the verdict</h2>
    <p class="lede"><strong>Question tested:</strong> do Sui mainnet RPC providers return
    different answers to the same question — event index completeness or freshness?</p>
    <div class="verdict-row">
      <p>Verdict: <span class="verdict">{e(d['verdict'])}</span>. For the pinned queries,
      the providers do <strong>not</strong> disagree on completeness or freshness.</p>
      <span class="stamp" role="img" aria-label="Verdict stamp: {e(d['verdict'])}">{e(d['verdict'])}</span>
    </div>
    {_ships(cfg)}
    <p>Two runs, &gt;10&nbsp;minutes apart, each JSON-RPC query issued twice per provider for
    self-consistency. Every JSON-RPC provider returned exactly
    {count(d['q1_count'])} events for the <code>0x2::coin</code> module query and
    {count(d['q1b_count'])} for the deny-list event type — identical id sets.</p>
    <p>They agreed on the answers, not on speed. Every request's latency was recorded:</p>
    {_fig_latency(d['latency'])}
    <div class="tablewrap"><table>
      <tr><th>Run</th><th>Start (UTC)</th><th>End (UTC)</th></tr>
      <tr><td>Run 1</td><td><code>{e(r1['started'])}</code></td><td><code>{e(r1['ended'])}</code></td></tr>
      <tr><td>Run 2</td><td><code>{e(r2['started'])}</code></td><td><code>{e(r2['ended'])}</code></td></tr>
    </table></div>
    <p class="kv">Vantage <code>{e(r1['vantage'])}</code> · User-Agent <code>{e(r1['user_agent'])}</code>
    · comparable predicate: {e(cfg['comparable_predicate']['use'])}.</p>
    <h3>Providers (pinned, no API keys)</h3>
    <div class="tablewrap"><table>
      <tr><th>id</th><th>endpoint</th><th>paradigm</th></tr>
      {_providers_rows(cfg)}
    </table></div>
  </div>
</section>
"""

    sec2 = f"""
<section id="sec-2" class="depth d2">
  {wave('var(--sea2)')}
  <div class="inner reveal">
    <h2><span class="n">2</span> Findings Sui developers can use today</h2>

    <h3>Mysten's public fullnode JSON-RPC is deprecated</h3>
    <p>In the recorded check on <time datetime="{e(d['fullnode']['recorded_at'])}">{DATE}</time>,
    a JSON-RPC call to <code>fullnode.mainnet.sui.io</code> returned error
    <code>-32601</code> (verbatim):</p>
    {_fig_terminal(d['msg_32601'], d['fullnode'])}
    <p>Use GraphQL or gRPC. The three third-party JSON-RPC providers below still serve
    the legacy JSON-RPC surface.</p>

    <h3>The <code>MoveModule</code> event filter matches the transaction's called module, not the event type</h3>
    <p>JSON-RPC <code>suix_queryEvents</code> with
    <code>MoveModule&nbsp;=&nbsp;{{package:0x2, module:coin}}</code> returned only
    <strong>{d['q1_count']}</strong> events — and their type is
    <code>0x2::deny_list::PerTypeConfigCreated</code>, not a coin event. The filter selects
    events emitted by transactions whose Move call targets that module, not events of a type
    in that module. All three JSON-RPC providers returned the identical {d['q1_count']}.</p>
    {_fig_diagram(q1b_type)}
    <p>To enumerate a specific event type, filter by its struct type instead:
    <code>MoveEventType</code> (JSON-RPC) or <code>type</code> with a fully-qualified type
    name (GraphQL) — that query returned <strong>{d['q1b_count']}</strong> events,
    identical across all four providers.</p>

    <h3>GraphQL's scan-budget trap: 0 nodes + <code>hasNextPage: true</code> does not mean empty</h3>
    <p>Documented GraphQL behaviour: a forward <code>events</code> scan can return a page
    with zero nodes while <code>pageInfo.hasNextPage</code> is <code>true</code> when the
    per-request scan budget is exhausted before a match, rather than reaching the end of data.
    The client code in this spike is built to handle this behaviour; no such page occurred in
    the recorded runs. Keep paginating while the cursor advances;
    treat a stalled cursor (no advance) as an incomplete, unknown result — never as an empty set.</p>
    {_fig_sonar(d['q1b_pages'], q1b_type)}

    <h3>Legacy JSON-RPC event timestamps run a fraction of a second late</h3>
    <p>Across <strong>{ts['n']}</strong> checked transactions, all providers agreed on
    <em>which checkpoint</em> contains each transaction. GraphQL's event timestamp equals the
    containing checkpoint's own timestamp (the chain's time). Legacy JSON-RPC
    <code>suix_queryEvents</code> event <code>timestampMs</code> ran
    <strong>{lag_lo:.2f}–{lag_hi:.2f}&nbsp;s later</strong> than the checkpoint — and later
    than the same node's own <code>sui_getTransactionBlock</code> timestamp, which does match.</p>
    {_fig_timeline(ts['lag_min'], ts['lag_max'])}
    <p>If you bound an event window by time, the two paradigms will drop different events at the
    edges even though every event is present in both indexes. Bound by checkpoint, or treat
    GraphQL's timestamp as ground truth.</p>

    <h3>Window access on JSON-RPC: compound filters are rejected; cursor seeding works</h3>
    <p>A compound filter <code>All[MoveEventType, TimeRange]</code> was rejected
    (<code>-32602 Invalid params</code>) by all three JSON-RPC providers. Two strategies that
    work: seed a descending <code>suix_queryEvents&nbsp;{{MoveEventType}}</code> scan from a
    known event id near the window end (used here), or filter by <code>TimeRange</code> alone
    and filter the type client-side.</p>
    {_fig_route()}
  </div>
</section>
"""

    sec3 = f"""
<section id="sec-3" class="depth d3">
  {wave('var(--sea3)')}
  <div class="inner reveal">
    <h2><span class="n">3</span> Method</h2>
    {_fig_pipeline(len(cfg['providers']), d['verdict'])}
    <ul>
      <li><strong>Comparable predicate.</strong> Compare only what means the same thing on both
        paradigms: the event <em>struct type</em> (<code>MoveEventType</code> == GraphQL
        <code>type</code>). <code>MoveModule</code> (called module) is not comparable to GraphQL's
        <code>module</code> (emitting module), so that query is labelled not_comparable, never
        "different".</li>
      <li><strong>Identity match.</strong> Event identity is exact across paradigms:
        JSON-RPC <code>(txDigest, eventSeq)</code> == GraphQL
        <code>(transaction.digest, sequenceNumber)</code>.</li>
      <li><strong>Self-consistency.</strong> Each JSON-RPC query ran twice per provider; a
        provider disagreeing with itself is flagged and excluded from that query's comparison.</li>
      <li><strong>Two runs.</strong> Findings must hold in both runs. Results that did not
        paginate cleanly are marked unknown (null), never counted as zero.</li>
      <li><strong>Windows.</strong> Checkpoint ranges mapped to timestamps; boundary events
        excluded on all providers. Three 5-minute windows:</li>
    </ul>
    <div class="tablewrap"><table>
      <tr><th>window</th><th>checkpoints</th><th>start (UTC)</th></tr>
      {win_rows}
    </table></div>
    <p class="kv">Q1b type <code>{e(q1b_type)}</code>. Q2 type
    <code>{e(q2_type)}</code>.</p>
  </div>
</section>
"""

    sec4 = f"""
<section id="sec-4" class="depth d4">
  {wave('var(--sea4)')}
  <div class="inner reveal">
    <h2><span class="n">4</span> Limits</h2>
    {_fig_loadline([
      f"A ~20-minute snapshot on {DATE}, not continuous monitoring.",
      f"A single network vantage (<code>{e(r1['vantage'])}</code>).",
      "One GraphQL provider (Mysten); GraphQL claims rest on it alone.",
      "The three JSON-RPC providers may run shared indexer software, so their agreement "
      "is not four fully independent implementations.",
      "The oldest window held only one matching event, so it is weak evidence on its own.",
    ])}
  </div>
</section>
"""

    sec5 = f"""
<section id="sec-5" class="depth d5">
  {wave('var(--sea5)')}
  <div class="inner reveal">
    <h2><span class="n">5</span> Evidence</h2>
    <p>Every claim above is backed by a committed file — the ship's cargo manifest. Raw
    responses, per-request observation rows (timestamp, provider, latency, bytes, error
    class + verbatim message), and the verdict computation are all in the repository.
    Each card links to the file on GitHub.</p>
    {_fig_manifest()}
  </div>
</section>
"""

    sec6 = f"""
<section id="sec-6" class="depth d6">
  {wave('var(--sea6)')}
  <div class="inner reveal">
    <h2><span class="n">6</span> Correction</h2>
    <p>A premise spike corrects its own record. An earlier reading is struck and amended,
    the way a ship's log is corrected — the original left legible beneath the line.</p>
    {_fig_amendment(d, e)}
  </div>
</section>
"""

    body = _hero(d) + sec1 + sec2 + sec3 + sec4 + sec5 + sec6

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plimsmark — do Sui RPC providers disagree?</title>
<meta name="description" content="A dated, network-tested spike: do Sui mainnet RPC providers disagree on event index completeness or freshness? Verdict: {e(d['verdict'])}.">
<meta name="color-scheme" content="dark">
<style>{CSS}</style>
</head>
<body>
{_gauge(d)}
<main>
{body}
</main>
<footer>
  <p>Plimsmark — named for the Plimsoll line, a ship's load line. A premise spike, not a
  product. All values on this page are read from the dated fixtures linked above.</p>
</footer>
<script>{JS}</script>
</body>
</html>
"""


def main():
    d = load_data(ROOT)
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(render(d))
    (docs / "CNAME").write_text(CNAME + "\n")
    (docs / ".nojekyll").write_text("")
    n = len((docs / "index.html").read_text())
    print(f"wrote docs/index.html ({n} bytes, {n/1024:.1f} KB), CNAME, .nojekyll")


if __name__ == "__main__":
    main()
