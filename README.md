# plimmark — Sui RPC provider disagreement spike

**This is a PREMISE SPIKE, not a product.** No service, database, scheduler,
dashboard, or deploy config. The deliverables are a small probe library,
network-free tests, dated verbatim fixtures, and a verdict.

## Premise under test

> Sui mainnet RPC providers return DIFFERENT answers to the SAME question
> (event index completeness and/or freshness).

We are **testing** this, not proving it. If all providers agree, the correct
outcome is **REFUTED**, and a clean REFUTED is a successful spike.

## Providers (pinned, no API keys)

| id | endpoint | paradigm |
|----|----------|----------|
| `mysten_graphql` | https://graphql.mainnet.sui.io/graphql | GraphQL |
| `publicnode` | https://sui-rpc.publicnode.com | JSON-RPC |
| `blockvision` | https://sui-mainnet-endpoint.blockvision.org | JSON-RPC |
| `rpcpool` | https://mainnet.sui.rpcpool.com | JSON-RPC |

If a provider is dead or demands a key, we record it verbatim as a definitive
failure and continue. We never substitute another provider.

## Comparability rules

- Compare only predicates verified to mean the same thing on both paradigms.
  Prefer `MoveEventType` (event struct type), which is unambiguous. JSON-RPC
  `MoveModule` matches the module of the transaction's Move call, which may NOT
  equal any GraphQL module filter. If equivalence is not established by
  evidence, label the comparison `not_comparable`, never "different".
- Event identity: JSON-RPC id = `(txDigest, eventSeq)`. Find the GraphQL
  equivalent by introspection. If no exact match exists, compare on
  `(txDigest, event type, occurrence index within tx)` and say so in the
  summary.
- Windows are checkpoint ranges `[c_start, c_end)`, mapped to timestamps via
  `mysten_graphql` (binary search on checkpoint timestamp). Windows end
  `>= 1 hour` before run start, so freshness lag cannot masquerade as missing
  data.
- Boundary guard: on ALL providers, exclude events whose timestamp equals
  `ts(c_start)` or `ts(c_end)` (checkpoints can share a millisecond). Report
  excluded counts per provider.

## Key discipline

- `NULL is not 0.` A query whose pagination did not finish cleanly has
  completeness = `null` (unknown), never a count. Unknown results are excluded
  from comparison and reported as unknown.
- Never rely on remembered GraphQL schema; it has changed across versions.
  Introspect live and save the result verbatim.
- Failure classes, each with the verbatim raw message kept: `definitive`
  (method not found, unsupported filter, invalid params, "no longer available",
  key required), `transient` (timeout, connection error, 429, 5xx), `ours`
  (request we built wrong, our parse error), `scan_budget` (GraphQL: 0 nodes +
  hasNextPage true with no advancing cursor), `cap_reached` (our own
  page/byte/request cap).

## VERDICT CRITERIA

- **COMPLETENESS FINDING:** on a comparable query/window, a complete provider is
  missing event IDs that another complete provider returns, in BOTH runs, with
  both providers self-consistent within each run.
- **FRESHNESS FINDING:** a provider's index lag exceeds 5 minutes, or its
  checkpoint lag exceeds 1,000 checkpoints vs the max observed, in >=2 of 3
  samples in BOTH runs.
- **PROVEN (completeness):** >=1 completeness finding.
- **PROVEN (freshness only):** no completeness finding, >=1 freshness finding.
  Report as the weaker basis.
- **REFUTED:** every comparable query/window is agree in both runs and there is
  no freshness finding.
- **INCONCLUSIVE:** anything else. State exactly what blocked the verdict and
  the cheapest next probe.
- Differences that exist only on `not_comparable` queries, only in one run, or
  only on incomplete/unknown results never count toward PROVEN.

## Layout

```
probe/          probe library (network-free core + client/transport seams)
tests/          network-free tests (conftest.py blocks all sockets)
fixtures/       dated verbatim fixtures (introspection, semantics, run data)
reference/      earlier spike's dated observations — RE-VERIFY, do not import
```

## Running

```bash
.venv/bin/python -m pytest        # network-free test suite
```

## Public report

A static, self-contained report of the spike lives in `docs/` and is published at
**https://plimsmark.com** via GitHub Pages. It is a single HTML file — inline CSS,
inline SVG, inline vanilla JavaScript, and **no external fonts, scripts, images,
or network requests**. Its industrial-editorial visual system uses navy/cyan,
large left-aligned chapter titles, and original generated particle/wireframe
layers. The Limits and Evidence chapters shift to a light paper palette.
A fixed depth gauge (side rail on desktop, bottom bar on mobile) tracks all six
sections; the Plimsoll load-line mark remains the logo. The supplied reference
video informs composition and motion only: no third-party video, logo, image,
or font files are embedded. Decorative meshes are labelled as visual metaphors,
not measurements. The shell lives in `scripts/report_theme.py`.

Every number, date, and claim is **read from the dated fixtures** by
`scripts/build_site.py` (tested network-free in `tests/test_build_site.py`), never
typed by hand; the decorative count-ups animate toward values already present as
static text. The page is built as **progressive enhancement** — with JavaScript
disabled, or with `prefers-reduced-motion: reduce`, every section, visual, and
final number is fully visible and the animation is off. It is responsive down to
375&nbsp;px, uses semantic headings and keyboard-reachable links, and stays well
under 250&nbsp;KB.

The Section 2 error panel is explicitly **archived evidence**, with the request
and timestamp read from its fixture, not a live website error. The pagination
chart replays the recorded pages: the step trace, event counts, and `hasNextPage`
state advance together. Play/pause, restart, and a keyboard-accessible page
slider are available with JavaScript; the replay pauses off-screen. Playback
speed is illustrative, **not live data or recorded request timing**. The hero and
six chapter openings use short sticky scenes: scroll position controls mesh
rotation, layer separation, scale, and text parallax in both directions. Each
report block reveals as it enters the viewport; whole sections are never hidden.
There is no wheel/touch interception or scroll lock. Pinning uses the actual
scene height; scenes taller than the viewport scroll normally instead. Copy
parallax stops before the fixed header, and a desktop gutter protects text from
the section rail. Reduced-motion and no-JS modes remove pinning and motion while
preserving the full report and navigation, with an independent high-contrast
navigation background when JavaScript is unavailable.

Regenerate it with:

```bash
.venv/bin/python scripts/build_site.py   # -> docs/index.html (+ CNAME, .nojekyll)
```

Browser verification (Mac with Google Chrome installed; separate from the
socket-blocked pytest suite):

```bash
uv run --no-project --with playwright --python .venv/bin/python python scripts/check_site_browser.py
```

The browser check loads the local HTML and blocks HTTP(S). It covers every replay
page, pause/restart/seek and keyboard controls, the hero and all six scroll scenes
at multiple progress points and in reverse, real wheel input, per-block reveals,
fast scrolling, a 375 px viewport, reduced motion (including changes during
playback), and JavaScript disabled. Pass `--browser webkit` for an installed
Playwright WebKit build (Safari-engine coverage). The first `uv` run may download
Playwright; the checks themselves never call an RPC provider.

