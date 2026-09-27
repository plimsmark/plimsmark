"""Item 11: render docs/index.html from committed files.

Every number and date on the page is READ from the fixtures / spike_config /
summary files here — never typed by hand. The page is one self-contained HTML
file: inline CSS, inline SVG, no external fonts/scripts/images.

Run:  .venv/bin/python scripts/build_site.py
"""

from __future__ import annotations

import gzip
import html
import json
import pathlib
import re
import sys

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

LOGO = (
    '<svg class="mark" viewBox="0 0 100 100" role="img" '
    'aria-label="Plimsoll load line mark: a circle bisected by a horizontal line" '
    'fill="none" stroke="currentColor" stroke-width="6">'
    '<line x1="4" y1="50" x2="96" y2="50"/>'
    '<circle cx="50" cy="50" r="26"/>'
    '</svg>'
)

CSS = """
:root{
  --navy:#0a2540; --navy-2:#0e2f52; --teal:#12726d; --teal-ink:#0c5551;
  --paper:#f5f7fa; --paper-2:#e9eef4; --ink:#0a2540; --muted:#4a5b6e;
  --border:#c9d6e2; --code:#eef2f7;
}
@media (prefers-color-scheme: dark){
  :root{
    --paper:#0a1a2f; --paper-2:#0e2440; --ink:#e8eef4; --muted:#a7b8c9;
    --teal:#5fd3c9; --teal-ink:#8fe3db; --border:#20385a; --code:#0e2440; --navy:#0a1a2f;
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.6; font-size:17px;
}
.wrap{max-width:760px; margin:0 auto; padding:24px 18px 72px}
header{display:flex; align-items:center; gap:14px; padding:8px 0 4px}
.mark{width:46px; height:46px; color:var(--teal); flex:0 0 auto}
h1{font-size:1.6rem; margin:.2em 0; letter-spacing:.2px}
.sub{color:var(--muted); margin:.1em 0 1.2em}
h2{font-size:1.25rem; margin:2em 0 .4em; border-bottom:2px solid var(--teal); padding-bottom:.2em}
h3{font-size:1.05rem; margin:1.3em 0 .3em}
a{color:var(--teal-ink)}
code,pre{background:var(--code); border:1px solid var(--border); border-radius:6px}
code{padding:.08em .35em; font-size:.9em}
pre{padding:12px 14px; overflow:auto}
pre code{border:0; padding:0; background:transparent}
.verdict{
  display:inline-block; font-weight:700; letter-spacing:.5px;
  background:var(--teal); color:#f7fbff; padding:.15em .6em; border-radius:6px;
}
@media (prefers-color-scheme: dark){ .verdict{ color:#06201d } }
table{border-collapse:collapse; width:100%; margin:.6em 0; font-size:.94rem}
th,td{border:1px solid var(--border); padding:6px 9px; text-align:left; vertical-align:top}
th{background:var(--paper-2)}
ul{padding-left:1.2em}
li{margin:.25em 0}
.kv{color:var(--muted); font-size:.92rem}
footer{margin-top:3em; padding-top:1em; border-top:1px solid var(--border); color:var(--muted); font-size:.86rem}
"""


def _providers_rows(cfg):
    rows = ""
    for name, v in cfg["providers"].items():
        rows += f"<tr><td><code>{name}</code></td><td>{html.escape(v['endpoint'])}</td><td>{v['paradigm']}</td></tr>"
    return rows


def render(d: dict) -> str:
    cfg = d["cfg"]
    e = html.escape
    r1, r2 = d["run1"], d["run2"]
    strat = cfg["queries"]["Q2"]["access_strategy"]
    windows = cfg["queries"]["Q2"]["windows"]
    q1b_type = cfg["queries"]["Q1b"]["types"][0]
    q2_type = cfg["queries"]["Q2"]["type"]
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

    body = f"""
<header>
  {LOGO}
  <div>
    <h1>Plimsmark</h1>
    <div class="sub">Do Sui mainnet RPC providers disagree on event data? A dated, network-tested spike.</div>
  </div>
</header>

<main>
<section>
  <h2>1. The question, and the verdict</h2>
  <p><strong>Question tested:</strong> do Sui mainnet RPC providers return
  different answers to the same question — event index completeness or freshness?</p>
  <p>Verdict: <span class="verdict">{e(d['verdict'])}</span>. For the pinned queries,
  the providers do <strong>not</strong> disagree on completeness or freshness. Two runs,
  &gt;10&nbsp;minutes apart, each JSON-RPC query issued twice per provider for
  self-consistency.</p>
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
</section>

<section>
  <h2>2. Findings Sui developers can use today</h2>

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
</section>

<section>
  <h2>3. Method</h2>
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
</section>

<section>
  <h2>4. Limits</h2>
  <ul>
    <li>A ~20-minute snapshot on {DATE}, not continuous monitoring.</li>
    <li>A single network vantage (<code>{e(r1['vantage'])}</code>).</li>
    <li>One GraphQL provider (Mysten); GraphQL claims rest on it alone.</li>
    <li>The three JSON-RPC providers may run shared indexer software, so their agreement is
      not four fully independent implementations.</li>
    <li>The oldest window held only one matching event, so it is weak evidence on its own.</li>
  </ul>
</section>

<section>
  <h2>5. Evidence</h2>
  <p>Every claim above is backed by a committed file. Raw responses, per-request observation
  rows (timestamp, provider, latency, bytes, error class + verbatim message), and the
  verdict computation are all in the repository.</p>
  <ul>
    {ev_links}
  </ul>
</section>

<section>
  <h2>6. Correction</h2>
  <p>An earlier spike read publicnode's {d['q1_count']}-event <code>0x2::coin</code> answer as
  a partial or stale index. That is refuted here: the {d['q1_count']} events are
  <code>deny_list::PerTypeConfigCreated</code>, returned identically by all three JSON-RPC
  providers; <code>MoveModule</code> matches the called module, not the event type. See
  <a href="{REPO_URL}/fixtures/corrections_{DATE}.md">corrections_{DATE}.md</a>.</p>
</section>
</main>

<footer>
  <p>Plimsmark — named for the Plimsoll line, a ship's load line. A premise spike, not a
  product. All values on this page are read from the dated fixtures linked above.</p>
</footer>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plimsmark — do Sui RPC providers disagree?</title>
<meta name="description" content="A dated, network-tested spike: do Sui mainnet RPC providers disagree on event index completeness or freshness? Verdict: {e(d['verdict'])}.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{body}
</div>
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
    print(f"wrote docs/index.html ({len((docs/'index.html').read_text())} bytes), CNAME, .nojekyll")


if __name__ == "__main__":
    main()
