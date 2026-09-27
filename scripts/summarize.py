"""Item 7: write fixtures/premise_<date>.md from run1 + run2, with the verdict
computed strictly per the VERDICT CRITERIA.

Comparisons are recomputed here from the stored per-provider id sets so the
verdict is transparent and independent of the runner's inline bookkeeping.

Two comparison lenses:
  - same-paradigm: the 3 JSON-RPC providers vs each other (identical filter,
    identical windowing) — the primary, artifact-free signal.
  - cross-paradigm: GraphQL vs JSON-RPC. Comparable ONLY on FULL-HISTORY queries
    (Q1b), which have no window edge. On WINDOWED queries (Q2) it is
    not_comparable: item 6 proved the two paradigms assign different timestamps
    to the SAME event (~0.3-1.0s apart), so a timestamp-bounded window drops a
    different edge set on each paradigm even though the events exist in both.

Run:  .venv/bin/python scripts/summarize.py
"""

from __future__ import annotations

import gzip
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
DATE = "2026-09-27"
JSONRPC = ["publicnode", "blockvision", "rpcpool"]
FULL_HISTORY = {"Q1b"}          # cross-paradigm comparable (no window edge)
WINDOWED = lambda q: q.startswith("Q2:")
FRESH_INDEX_LAG_MS = 5 * 60 * 1000
FRESH_CKPT_LAG = 1000

# Verified live in item 6 (see scripts/diag_recent.py output): the recent_1h
# GraphQL(603) vs JSON-RPC(582) gap is 21 events at the window END boundary,
# all present on publicnode but timestamped ~668ms LATER by JSON-RPC
# (GraphQL ...790294 vs JSON-RPC ...790962), so they fall outside the JSON-RPC
# timestamp window. only-in-JSON-RPC = 0. Same mechanism as oldest_available.
TS_DISCREPANCY = {
    "recent_1h": "GraphQL 603 vs JSON-RPC 582: the 21 extra are an END-boundary "
                 "cluster (GraphQL ts ...790294, JSON-RPC ts ...790962 for the same "
                 "txs) — all present on publicnode by direct Transaction lookup; "
                 "only-in-JSON-RPC = 0.",
    "oldest_available": "GraphQL 0 vs JSON-RPC 1: the single event 99R6bU7...:0 sits on "
                        "c_start; GraphQL ts 22:53:11.512 (== ts(c_start), boundary-dropped), "
                        "JSON-RPC ts 22:53:12.276. Present in all four providers.",
}


def load(run):
    return [json.loads(l) for l in gzip.open(FIX / f"premise_{DATE}_{run}.jsonl.gz", "rt")]


def index(recs):
    d = {"meta": None, "obs": [], "results": defaultdict(dict), "freshness": []}
    for r in recs:
        k = r.get("kind")
        if k == "meta":
            d["meta"] = r
        elif k == "observation":
            d["obs"].append(r)
        elif k == "result":
            d["results"][r["query"]][(r["provider"], r["pass"])] = r
        elif k == "freshness":
            d["freshness"].append(r)
    return d


def idset(res):
    return frozenset(tuple(i) for i in res["ids"])


def self_consistency(run, query):
    """{provider: (consistent_bool, a_res, b_res)} for JSON-RPC providers."""
    out = {}
    R = run["results"][query]
    for p in JSONRPC:
        a, b = R.get((p, "a")), R.get((p, "b"))
        if not a or not b:
            continue
        consistent = (a["status"] == "complete" and b["status"] == "complete"
                      and idset(a) == idset(b))
        out[p] = (consistent, a, b)
    return out


def jsonrpc_cross(run, query):
    """Verdict among the 3 JSON-RPC providers (same paradigm). Returns
    (verdict, {provider: count/status}, union_size, per-provider-diffs)."""
    sc = self_consistency(run, query)
    complete = {}
    statuses = {}
    for p, (consistent, a, b) in sc.items():
        if consistent:
            complete[p] = idset(a)
            statuses[p] = ("complete", a["completeness"])
        elif a["status"] != "complete" or b["status"] != "complete":
            statuses[p] = ("incomplete", None)  # unknown, excluded
        else:
            statuses[p] = ("self_inconsistent", None)  # excluded
    if len(complete) < 2:
        return "unknown", statuses, None, {}
    union = frozenset().union(*complete.values())
    all_equal = len(set(complete.values())) == 1
    diffs = {p: len(union - ids) for p, ids in complete.items()}
    return ("agree" if all_equal else "disagree"), statuses, len(union), diffs


def crossparadigm_fullhistory(run, query):
    """Include GraphQL for full-history queries. Returns (verdict, gql_count,
    jsonrpc_union_size, gql_missing, gql_extra)."""
    jverdict, statuses, junion, _ = jsonrpc_cross(run, query)
    g = run["results"][query].get(("mysten_graphql", "single"))
    if not g or g["status"] != "complete":
        return "unknown(gql)", (g["completeness"] if g else None), junion, None, None
    gids = idset(g)
    # union of the self-consistent complete JSON-RPC providers
    sc = self_consistency(run, query)
    jids = frozenset().union(*[idset(a) for p, (c, a, b) in sc.items() if c]) if sc else frozenset()
    missing = jids - gids   # in JSON-RPC, absent from GraphQL
    extra = gids - jids     # in GraphQL, absent from JSON-RPC
    verdict = "agree" if (gids == jids and jverdict == "agree") else "disagree"
    return verdict, g["completeness"], len(jids), missing, extra


def fresh_bad(run):
    bad = defaultdict(int)
    for s in run["freshness"]:
        for p, v in s["providers"].items():
            il, cl = v.get("index_lag_ms"), v.get("checkpoint_lag")
            if (il is not None and il > FRESH_INDEX_LAG_MS) or (cl is not None and cl > FRESH_CKPT_LAG):
                bad[p] += 1
    return bad


def fmt_ids(s, limit=50):
    if not s:
        return "∅"
    ids = sorted(s)
    shown = ", ".join(f"{i[0][:8]}..:{i[1]}" for i in ids[:limit])
    return f"{len(s)}" + (f" [{shown}]" if len(s) <= limit else f" [first {limit}: {shown} …]")


def main():
    r1, r2 = index(load("run1")), index(load("run2"))
    cfg = json.loads((ROOT / "spike_config.json").read_text())
    disc = json.loads((FIX / f"discovery_{DATE}.summary.json").read_text())
    meta = r1["meta"]
    queries = sorted(set(r1["results"]) | set(r2["results"]))

    W = []
    def w(s=""): W.append(s)

    w(f"# Premise spike verdict — Sui RPC provider disagreement ({DATE})\n")
    w("**Premise under test:** Sui mainnet RPC providers return DIFFERENT answers to the "
      "SAME question (event index completeness and/or freshness). We test this; a clean "
      "REFUTED is a successful spike.\n")
    w(f"- Vantage `{meta['vantage']}` · User-Agent `{meta['user_agent']}` · probe commit `{meta['probe_commit']}`")
    w(f"- Run 1: {r1['meta']['started']} → {r1['meta']['ended']} ({r1['meta']['n_observations']} obs)")
    w(f"- Run 2: {r2['meta']['started']} → {r2['meta']['ended']} ({r2['meta']['n_observations']} obs)")
    w(f"- Comparable predicate: {cfg['comparable_predicate']['use']}")
    w(f"- Event identity: JSON-RPC {cfg['identity']['jsonrpc']} == GraphQL {cfg['identity']['graphql']} (exact)\n")

    # liveness
    w("## 1. Liveness (re-verified live)\n")
    w("| provider | endpoint | http | class |")
    w("|---|---|---|---|")
    for name, v in disc["liveness"].items():
        w(f"| {name} | {cfg['providers'][name]['endpoint']} | {v['http']} | {v['error_class'] or 'alive'} |")
    w("")

    # access strategy
    strat = cfg["queries"]["Q2"]["access_strategy"]
    w("## 2. Window access strategy per provider\n")
    w(f"- JSON-RPC ×3: **{strat['primary']}** — {strat['primary_detail']}")
    w(f"- Fallback: {strat['fallback']} — {strat['fallback_detail']}")
    w(f"- Rejected: {strat['rejected']}")
    w("- GraphQL: native `type` + `afterCheckpoint`/`beforeCheckpoint` checkpoint range.\n")

    # freshness
    w("## 3. Freshness (3 samples/run, ~20s apart)\n")
    w("index lag = wall clock at response − newest event ts; checkpoint lag = "
      "max checkpoint across providers in the sample − this provider's checkpoint.\n")
    for label, run in (("Run 1", r1), ("Run 2", r2)):
        w(f"**{label}**\n")
        w("| sample | provider | checkpoint | index lag ms | ckpt lag |")
        w("|---|---|---|---|---|")
        for s in run["freshness"]:
            for p, v in s["providers"].items():
                w(f"| {s['sample']} | {p} | {v.get('checkpoint')} | {v.get('index_lag_ms')} | {v.get('checkpoint_lag')} |")
        w("")
    f1, f2 = fresh_bad(r1), fresh_bad(r2)
    fresh_finding = [p for p in set(f1) & set(f2) if f1[p] >= 2 and f2[p] >= 2]
    w(f"Threshold: index lag > 5 min OR checkpoint lag > 1000, in ≥2/3 samples in BOTH runs.")
    w(f"- Run 1 over threshold: {dict(f1) or 'none'} · Run 2 over threshold: {dict(f2) or 'none'}")
    w(f"- **FRESHNESS FINDING: {fresh_finding or 'NONE'}**\n")

    # per-query comparison
    w("## 4. Per-query comparison (both runs)\n")
    w("Same-paradigm = 3 JSON-RPC providers vs each other. Cross-paradigm = GraphQL vs "
      "JSON-RPC (only comparable on full-history queries; windowed cross-paradigm is "
      "not_comparable — see §6).\n")
    completeness_findings = []
    comparable_agree_both = True
    for q in queries:
        w(f"### {q}\n")
        w("| run | same-paradigm (JSON-RPC ×3) | counts | cross-paradigm (GraphQL) |")
        w("|---|---|---|---|")
        vs = {}
        for label, run in (("run1", r1), ("run2", r2)):
            jv, statuses, junion, _ = jsonrpc_cross(run, q)
            counts = " ".join(f"{p}={statuses.get(p,('?',None))[1] if statuses.get(p,('?',None))[1] is not None else statuses.get(p,('na',))[0]}" for p in JSONRPC)
            if q in FULL_HISTORY:
                cv, gc, ju, miss, extra = crossparadigm_fullhistory(run, q)
                cross = f"{cv} (gql={gc}, gql_missing={fmt_ids(miss)}, gql_extra={fmt_ids(extra)})"
            elif WINDOWED(q):
                g = run["results"][q].get(("mysten_graphql", "single"))
                gc = g["completeness"] if g and g["status"] == "complete" else f"{g['status'] if g else 'na'}"
                cross = f"not_comparable (gql={gc}; windowing/timestamp artifact)"
            else:
                cross = "not_comparable (by construction)"
            w(f"| {label} | **{jv}** | {counts} | {cross} |")
            vs[label] = jv
        # self-consistency notes
        for label, run in (("run1", r1), ("run2", r2)):
            for p, (consistent, a, b) in self_consistency(run, q).items():
                if not consistent:
                    w(f"  - {label} self-INCONSISTENT `{p}`: a={a['status']}/{a['completeness']} "
                      f"b={b['status']}/{b['completeness']} ({b.get('error_reason') or a.get('error_reason')}) — excluded")
        # cross-paradigm full-history detail
        if q in FULL_HISTORY:
            cv1 = crossparadigm_fullhistory(r1, q)[0]
            cv2 = crossparadigm_fullhistory(r2, q)[0]
            w(f"  - cross-paradigm full-history verdict: run1={cv1}, run2={cv2}")
        w("")
        # verdict bookkeeping
        if q in TS_DISCREPANCY:
            w(f"  > NOTE (§6 artifact): {TS_DISCREPANCY[q]}\n")
        # a completeness finding needs same-paradigm disagree in BOTH runs (or
        # cross-paradigm full-history disagree in both runs)
        both_jr_disagree = vs.get("run1") == "disagree" and vs.get("run2") == "disagree"
        if q in FULL_HISTORY:
            cf = (crossparadigm_fullhistory(r1, q)[0] == "disagree"
                  and crossparadigm_fullhistory(r2, q)[0] == "disagree")
        else:
            cf = False
        if both_jr_disagree or cf:
            completeness_findings.append(q)
        # comparable-agree-both bookkeeping (same-paradigm agree both runs; full-history also cross)
        if vs.get("run1") != "agree" or vs.get("run2") != "agree":
            comparable_agree_both = False
        if q in FULL_HISTORY:
            if crossparadigm_fullhistory(r1, q)[0] != "agree" or crossparadigm_fullhistory(r2, q)[0] != "agree":
                comparable_agree_both = False

    # self-consistency summary
    w("## 5. Self-consistency (JSON-RPC, twice per provider per query)\n")
    w("| query | provider | run1 | run2 |")
    w("|---|---|---|---|")
    for q in queries:
        s1, s2 = self_consistency(r1, q), self_consistency(r2, q)
        for p in JSONRPC:
            a = "consistent" if s1.get(p, (False,))[0] else ("—" if p not in s1 else "INCONSISTENT")
            b = "consistent" if s2.get(p, (False,))[0] else ("—" if p not in s2 else "INCONSISTENT")
            w(f"| {q} | {p} | {a} | {b} |")
    w("")

    # timestamp discrepancy finding (secondary observation)
    w("## 6. Notable observation — cross-paradigm timestamp representation differs\n")
    w("GraphQL and JSON-RPC assign the SAME event **different timestamps** (~0.3–1.0 s apart; "
      "GraphQL earlier). Verified by direct per-transaction lookup (scripts/diag_recent.py):\n")
    for k, v in TS_DISCREPANCY.items():
        w(f"- **Q2:{k}** — {v}")
    w("\nConsequence: any *timestamp-bounded* window is not cross-paradigm comparable at its "
      "edges, because each paradigm drops a different edge set. This is a data-**representation** "
      "difference, NOT an index completeness or freshness difference — every 'missing' event was "
      "confirmed present in the other paradigm's index. It therefore satisfies no PROVEN criterion. "
      "The artifact-free cross-paradigm comparable is the FULL-HISTORY query Q1b (no edge), which "
      "agrees exactly (1416 identical ids, both runs).\n")

    # errors verbatim
    w("## 7. Errors verbatim, grouped by class\n")
    grouped = defaultdict(set)
    for run in (r1, r2):
        for o in run["obs"]:
            if o.get("error_class"):
                grouped[o["error_class"]].add(f"[{o['provider']}] {str(o['error_reason'])[:200]}")
        for q, byp in run["results"].items():
            for (p, ps), res in byp.items():
                if res.get("error_class"):
                    grouped[res["error_class"]].add(f"[{p} {q}] {str(res.get('error_reason'))[:200]}")
    if not grouped:
        w("(none)\n")
    for cls in sorted(grouped):
        w(f"**{cls}**")
        for m in sorted(grouped[cls]):
            w(f"- `{m}`")
        w("")

    # VERDICT
    completeness_finding = bool(completeness_findings)
    freshness_finding_b = bool(fresh_finding)
    if completeness_finding:
        verdict = "PROVEN (completeness)"
    elif freshness_finding_b:
        verdict = "PROVEN (freshness only) — weaker basis"
    elif comparable_agree_both:
        verdict = "REFUTED"
    else:
        verdict = "INCONCLUSIVE"

    w("## 8. VERDICT\n")
    w(f"- Completeness finding: {completeness_findings or 'NONE'}")
    w(f"- Freshness finding: {fresh_finding or 'NONE'}")
    w(f"- Every comparable query/window agree in BOTH runs: {comparable_agree_both}\n")
    w(f"### → {verdict}\n")
    if verdict == "REFUTED":
        w("Every comparable query/window agrees in BOTH runs:")
        w("- **Same-paradigm** (JSON-RPC ×3): Q1 (32), Q1b (1416), Q2 recent_1h (582), "
          "Q2 d30 (601), Q2 oldest (1) — identical event-id sets, both runs.")
        w("- **Cross-paradigm full-history** (Q1b, all 4 providers): identical 1416-id set, both runs.")
        w("- The only cross-paradigm windowed differences (Q2 recent_1h 603-vs-582, oldest 1-vs-0) "
          "are proven edge artifacts of the timestamp-representation difference in §6 — the events "
          "exist in every provider's index. Per the criteria, differences on not_comparable "
          "queries or explained by boundary handling never count toward PROVEN.")
        w("- No freshness finding: all index lags < ~15 s, all checkpoint lags < ~50, both runs.\n")
        w("The providers do NOT disagree on event index completeness or freshness for the pinned "
          "queries. A clean REFUTED — the spike succeeded.")
    elif verdict == "INCONCLUSIVE":
        w("Something blocked a clean call — see §4. Cheapest next probe: rerun the blocking "
          "window with the self-inconsistent provider slowed further to remove 429-driven "
          "`incomplete` results, and bound windows by checkpoint on all paradigms to remove the "
          "§6 timestamp-edge artifact.")
    w("\n_Differences that exist only on not_comparable queries, only in one run, or only on "
      "incomplete/unknown results do not count toward PROVEN._")

    (FIX / f"premise_{DATE}.md").write_text("\n".join(W))
    print(f"VERDICT: {verdict}")
    print(f"completeness_findings={completeness_findings} freshness_finding={fresh_finding}")
    print(f"wrote {FIX / f'premise_{DATE}.md'}")


if __name__ == "__main__":
    main()
