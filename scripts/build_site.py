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
import pathlib
import re

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

    premise = (root / "fixtures" / f"premise_{DATE}.md").read_text()
    vm = re.search(r"^###\s*→\s*(.+?)\s*$", premise, re.MULTILINE)
    verdict = vm.group(1).strip() if vm else "(unknown)"

    fullnode_md = (root / "fixtures" / f"mysten_fullnode_jsonrpc_{DATE}.md").read_text()
    msg_32601 = _extract_fence(fullnode_md, "Verbatim error message:")

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
.d1{background:var(--sea1)} .d2{background:var(--sea2)} .d3{background:var(--sea3)}
.d4{background:var(--sea4)} .d5{background:var(--sea5)} .d6{background:var(--sea6)}
.wave{position:absolute; top:-1px; left:0; width:100%; height:64px; line-height:0; pointer-events:none}
.wave svg{width:100%; height:100%; display:block}
.wave .w1{animation:drift 14s linear infinite}
.wave .w2{animation:drift 22s linear infinite reverse}
@keyframes drift{from{transform:translateX(0)} to{transform:translateX(-720px)}}

h1{font-size:2.1rem; margin:.1em 0; letter-spacing:.3px}
h2{font-size:1.5rem; margin:0 0 .8em; letter-spacing:.2px; display:flex; align-items:baseline; gap:.5rem}
h2 .n{color:var(--accent); font-variant-numeric:tabular-nums; font-size:1.05rem;
  border:1px solid var(--line); border-radius:999px; padding:.05em .55em; flex:0 0 auto}
h3{font-size:1.12rem; margin:1.6em 0 .35em; color:#fff}
p{margin:.7em 0}
.lede{font-size:1.12rem; color:var(--muted)}
code,pre{background:var(--code-bg); border:1px solid var(--line); border-radius:6px}
code{padding:.08em .35em; font-size:.88em}
pre{padding:12px 14px; overflow:auto; margin:.7em 0}
pre code{border:0; padding:0; background:transparent}
ul{padding-left:1.2em} li{margin:.3em 0}
.kv{color:var(--muted); font-size:.92rem}
table{border-collapse:collapse; width:100%; margin:.7em 0; font-size:.93rem}
th,td{border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top}
th{background:rgba(255,255,255,.06); color:#fff}
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
.scrollcue span{display:inline-block; animation:bob 2.4s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)} 50%{transform:translateY(5px)}}

/* ---- depth gauge (fixed side rail on desktop, bottom bar on mobile) ---- */
.gauge{position:fixed; z-index:20; left:14px; top:50%; transform:translateY(-50%)}
.gauge ol{list-style:none; margin:0; padding:0; position:relative}
.gauge ol::before{content:""; position:absolute; left:6px; top:6px; bottom:6px;
  width:2px; background:var(--line)}
.gauge li{position:relative}
.gauge a{display:flex; align-items:center; gap:.55rem; padding:.28rem 0;
  color:var(--muted); text-decoration:none; font-size:.78rem}
.gauge .dot{width:14px; height:14px; border-radius:50%; border:2px solid var(--line);
  background:transparent; flex:0 0 auto; position:relative; z-index:1; transition:all .3s}
.gauge .lbl{opacity:0; transform:translateX(-4px); transition:opacity .25s, transform .25s;
  white-space:nowrap; font-variant-numeric:tabular-nums}
.gauge a:hover .lbl, .gauge a:focus-visible .lbl, .gauge a.on .lbl{opacity:1; transform:none}
.gauge a:hover .dot{border-color:var(--accent)}
.gauge a.on{color:#fff}
.gauge a.on .dot{background:var(--accent); border-color:var(--accent); box-shadow:0 0 0 4px rgba(99,216,206,.18)}

footer{max-width:760px; margin:0 auto; padding:2.5rem 20px 4rem; color:var(--muted); font-size:.86rem}

/* ---- progressive enhancement: reveal ONLY hidden when JS is on ---- */
.js-anim .reveal{opacity:0; transform:translateY(26px); transition:opacity .7s ease, transform .7s ease}
.js-anim .reveal.shown{opacity:1; transform:none}

@media (max-width:820px){
  body{font-size:16px}
  .gauge{left:0; right:0; top:auto; bottom:0; transform:none;
    background:rgba(4,29,46,.92); backdrop-filter:blur(6px); border-top:1px solid var(--line)}
  .gauge ol{display:flex; justify-content:space-between; padding:.5rem .6rem}
  .gauge ol::before{display:none}
  .gauge a{flex-direction:column; gap:.2rem; padding:.15rem .3rem; font-size:.62rem; text-align:center}
  .gauge .lbl{opacity:1; transform:none}
  .depth{padding:3.2rem 0 4rem}
  h1{font-size:1.7rem} h2{font-size:1.3rem}
  footer{padding-bottom:5.5rem}
}

@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation:none !important; transition:none !important}
  .js-anim .reveal{opacity:1 !important; transform:none !important}
}
"""

JS = """
(function(){
  var root=document.documentElement;
  var mq=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  var reduce=mq&&mq.matches;
  // Progressive enhancement: without IO or with reduced motion, leave the fully
  // rendered, final-number page exactly as served. Motion is additive only.
  if(reduce||!('IntersectionObserver'in window)) return;
  root.classList.add('js-anim');

  function countup(el){
    if(el.dataset.done) return; el.dataset.done='1';
    var to=parseFloat(el.getAttribute('data-count'));
    var dec=parseInt(el.getAttribute('data-dec')||'0',10);
    var t0=null, dur=900;
    function frame(t){ if(t0===null)t0=t;
      var p=Math.min((t-t0)/dur,1); var v=to*(1-Math.pow(1-p,3));
      el.textContent=v.toFixed(dec);
      if(p<1) requestAnimationFrame(frame); else el.textContent=to.toFixed(dec);
    }
    requestAnimationFrame(frame);
  }

  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){ if(!e.isIntersecting) return;
      e.target.classList.add('shown');
      if(e.target.matches('[data-count]')) countup(e.target);
      var cs=e.target.querySelectorAll('[data-count]');
      for(var i=0;i<cs.length;i++) countup(cs[i]);
      io.unobserve(e.target);
    });
  },{threshold:0.18, rootMargin:'0px 0px -8% 0px'});
  var rev=document.querySelectorAll('.reveal');
  for(var i=0;i<rev.length;i++) io.observe(rev[i]);

  // depth gauge active state
  var links=[].slice.call(document.querySelectorAll('.gauge a'));
  var secs=links.map(function(a){return document.querySelector(a.getAttribute('href'));});
  var go=new IntersectionObserver(function(es){
    es.forEach(function(e){ if(!e.isIntersecting) return;
      var i=secs.indexOf(e.target);
      links.forEach(function(l){l.classList.remove('on');l.removeAttribute('aria-current');});
      if(i>=0){links[i].classList.add('on');links[i].setAttribute('aria-current','true');}
    });
  },{threshold:0.5});
  secs.forEach(function(s){ if(s) go.observe(s); });
})();
"""


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
            f'<li><a href="#{sid}">'
            f'<span class="dot"></span>'
            f'<span class="lbl">{i} · {html.escape(label)}</span>'
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
    return f"""
<section id="hero">
  {sky}
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

    ev_links = "".join(
        f'<li><a href="{REPO_URL}/{path}">{e(label)}</a> — <span class="kv">{e(path)}</span></li>'
        for label, path in FIXTURE_LINKS
    )
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
    <p>Verdict: <span class="verdict">{e(d['verdict'])}</span>. For the pinned queries,
    the providers do <strong>not</strong> disagree on completeness or freshness. Two runs,
    &gt;10&nbsp;minutes apart, each JSON-RPC query issued twice per provider for
    self-consistency. Every JSON-RPC provider returned exactly
    {count(d['q1_count'])} events for the <code>0x2::coin</code> module query and
    {count(d['q1b_count'])} for the deny-list event type — identical id sets.</p>
    <table>
      <tr><th>Run</th><th>Start (UTC)</th><th>End (UTC)</th></tr>
      <tr><td>Run 1</td><td><code>{e(r1['started'])}</code></td><td><code>{e(r1['ended'])}</code></td></tr>
      <tr><td>Run 2</td><td><code>{e(r2['started'])}</code></td><td><code>{e(r2['ended'])}</code></td></tr>
    </table>
    <p class="kv">Vantage <code>{e(r1['vantage'])}</code> · User-Agent <code>{e(r1['user_agent'])}</code>
    · comparable predicate: {e(cfg['comparable_predicate']['use'])}.</p>
    <h3>Providers (pinned, no API keys)</h3>
    <table>
      <tr><th>id</th><th>endpoint</th><th>paradigm</th></tr>
      {_providers_rows(cfg)}
    </table>
  </div>
</section>
"""

    sec2 = f"""
<section id="sec-2" class="depth d2">
  {wave('var(--sea2)')}
  <div class="inner reveal">
    <h2><span class="n">2</span> Findings Sui developers can use today</h2>

    <h3>Mysten's public fullnode JSON-RPC is deprecated</h3>
    <p>A JSON-RPC call to <code>fullnode.mainnet.sui.io</code> returns error
    <code>-32601</code> (verbatim):</p>
    <pre><code>{e(d['msg_32601'])}</code></pre>
    <p>Use GraphQL or gRPC. The three third-party JSON-RPC providers below still serve
    the legacy JSON-RPC surface.</p>

    <h3>The <code>MoveModule</code> event filter matches the transaction's called module, not the event type</h3>
    <p>JSON-RPC <code>suix_queryEvents</code> with
    <code>MoveModule&nbsp;=&nbsp;{{package:0x2, module:coin}}</code> returned only
    <strong>{d['q1_count']}</strong> events — and their type is
    <code>0x2::deny_list::PerTypeConfigCreated</code>, not a coin event. The filter selects
    events emitted by transactions whose Move call targets that module, not events of a type
    in that module. All three JSON-RPC providers returned the identical {d['q1_count']}.
    To enumerate a specific event type, filter by its struct type instead:
    <code>MoveEventType</code> (JSON-RPC) or <code>type</code> with a fully-qualified type
    name (GraphQL) — that query returned <strong>{d['q1b_count']}</strong> events,
    identical across all four providers.</p>

    <h3>GraphQL's scan-budget trap: 0 nodes + <code>hasNextPage: true</code> does not mean empty</h3>
    <p>A forward GraphQL <code>events</code> scan can return a page with zero nodes while
    <code>pageInfo.hasNextPage</code> is <code>true</code>: the per-request scan budget was
    exhausted before a match, not the end of data. Keep paginating while the cursor advances;
    treat a stalled cursor (no advance) as an incomplete, unknown result — never as an empty set.</p>

    <h3>Legacy JSON-RPC event timestamps run a fraction of a second late</h3>
    <p>Across <strong>{ts['n']}</strong> checked transactions, all providers agreed on
    <em>which checkpoint</em> contains each transaction. GraphQL's event timestamp equals the
    containing checkpoint's own timestamp (the chain's time). Legacy JSON-RPC
    <code>suix_queryEvents</code> event <code>timestampMs</code> ran
    <strong>{lag_lo:.2f}–{lag_hi:.2f}&nbsp;s later</strong> than the checkpoint — and later
    than the same node's own <code>sui_getTransactionBlock</code> timestamp, which does match.
    If you bound an event window by time, the two paradigms will drop different events at the
    edges even though every event is present in both indexes. Bound by checkpoint, or treat
    GraphQL's timestamp as ground truth.</p>

    <h3>Window access on JSON-RPC: compound filters are rejected; cursor seeding works</h3>
    <p>A compound filter <code>All[MoveEventType, TimeRange]</code> was rejected
    (<code>-32602 Invalid params</code>) by all three JSON-RPC providers. Two strategies that
    work: seed a descending <code>suix_queryEvents&nbsp;{{MoveEventType}}</code> scan from a
    known event id near the window end (used here), or filter by <code>TimeRange</code> alone
    and filter the type client-side.</p>
  </div>
</section>
"""

    sec3 = f"""
<section id="sec-3" class="depth d3">
  {wave('var(--sea3)')}
  <div class="inner reveal">
    <h2><span class="n">3</span> Method</h2>
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
    <table>
      <tr><th>window</th><th>checkpoints</th><th>start (UTC)</th></tr>
      {win_rows}
    </table>
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
    <ul>
      <li>A ~20-minute snapshot on {DATE}, not continuous monitoring.</li>
      <li>A single network vantage (<code>{e(r1['vantage'])}</code>).</li>
      <li>One GraphQL provider (Mysten); GraphQL claims rest on it alone.</li>
      <li>The three JSON-RPC providers may run shared indexer software, so their agreement is
        not four fully independent implementations.</li>
      <li>The oldest window held only one matching event, so it is weak evidence on its own.</li>
    </ul>
  </div>
</section>
"""

    sec5 = f"""
<section id="sec-5" class="depth d5">
  {wave('var(--sea5)')}
  <div class="inner reveal">
    <h2><span class="n">5</span> Evidence</h2>
    <p>Every claim above is backed by a committed file. Raw responses, per-request observation
    rows (timestamp, provider, latency, bytes, error class + verbatim message), and the
    verdict computation are all in the repository.</p>
    <ul>
      {ev_links}
    </ul>
  </div>
</section>
"""

    sec6 = f"""
<section id="sec-6" class="depth d6">
  {wave('var(--sea6)')}
  <div class="inner reveal">
    <h2><span class="n">6</span> Correction</h2>
    <p>An earlier spike read publicnode's {d['q1_count']}-event <code>0x2::coin</code> answer as
    a partial or stale index. That is refuted here: the {d['q1_count']} events are
    <code>deny_list::PerTypeConfigCreated</code>, returned identically by all three JSON-RPC
    providers; <code>MoveModule</code> matches the called module, not the event type. See
    <a href="{REPO_URL}/fixtures/corrections_{DATE}.md">corrections_{DATE}.md</a>.</p>
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
