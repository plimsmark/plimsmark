"""Item 5a-5c: live discovery.

  5a re-verify liveness, verbatim
  5b introspect the GraphQL schema -> fixtures/graphql_introspection_<date>.json
  5c JSON-RPC MoveModule semantics + GraphQL equivalence evidence

Run:  .venv/bin/python scripts/discover.py
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scripts._live import Live, PROVIDERS, dump_rows  # noqa: E402

DATE = "2026-09-27"
FIX = HERE.parent / "fixtures"
FIX.mkdir(exist_ok=True)

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    types {
      kind name
      fields(includeDeprecated: true) {
        name
        args { name type { ...TypeRef } }
        type { ...TypeRef }
      }
      inputFields { name type { ...TypeRef } }
    }
  }
}
fragment TypeRef on __Type {
  kind name
  ofType { kind name ofType { kind name ofType { kind name } } }
}
"""


def section(t):
    print(f"\n{'='*78}\n{t}\n{'-'*78}")


def main():
    live = Live()
    findings = {}

    # --- 5a liveness ---
    section("5a. Liveness (verbatim)")
    liveness = {}
    for name, (url, kind) in PROVIDERS.items():
        if kind == "graphql":
            st, parsed, body, (ec, er) = live.gql(
                "{ chainIdentifier checkpoint { sequenceNumber } }", label="liveness"
            )
        else:
            st, parsed, body, (ec, er) = live.rpc(
                name, "sui_getLatestCheckpointSequenceNumber", []
            )
        snippet = body[:300].decode("utf-8", "replace")
        liveness[name] = {"http": st, "error_class": ec, "error_reason": er, "body": snippet}
        print(f"  {name:16} http={st} class={ec} {snippet[:120]}")
    findings["liveness"] = liveness

    # --- 5b introspection ---
    section("5b. GraphQL introspection")
    st, parsed, body, (ec, er) = live.gql(INTROSPECTION_QUERY, label="introspection")
    if parsed and parsed.get("data"):
        out = FIX / f"graphql_introspection_{DATE}.json"
        out.write_text(json.dumps(parsed, indent=2))
        print(f"  saved {out} ({len(body):,} bytes)")
        types = {t["name"]: t for t in parsed["data"]["__schema"]["types"] if t.get("name")}
        ef = types.get("EventFilter")
        if ef and ef.get("inputFields"):
            print("  EventFilter input fields:")
            for f in ef["inputFields"]:
                tn = _type_name(f["type"])
                print(f"    {f['name']:18} :: {tn}")
        ev = types.get("Event")
        if ev and ev.get("fields"):
            print("  Event fields (identity candidates):")
            for f in ev["fields"]:
                print(f"    {f['name']:22} :: {_type_name(f['type'])}")
    else:
        print(f"  introspection FAILED class={ec} {er}")

    # --- 5c MoveModule semantics ---
    section("5c. JSON-RPC MoveModule 0x2::coin semantics")
    semantics = {}
    for name in ("publicnode", "blockvision", "rpcpool"):
        st, parsed, body, (ec, er) = live.rpc(
            name,
            "suix_queryEvents",
            [{"MoveModule": {"package": "0x2", "module": "coin"}}, None, 50, False],
        )
        if parsed and parsed.get("result"):
            data = parsed["result"]["data"]
            types = sorted({e.get("type") for e in data})
            ts = sorted(int(e["timestampMs"]) for e in data if e.get("timestampMs"))
            span = ""
            if ts:
                fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")
                span = f" oldest={fmt(ts[0])} newest={fmt(ts[-1])}"
            semantics[name] = {
                "count": len(data),
                "hasNextPage": parsed["result"]["hasNextPage"],
                "types": types,
                "span": span.strip(),
            }
            print(f"  {name:16} count={len(data)} hasNextPage={parsed['result']['hasNextPage']}{span}")
            for tp in types:
                print(f"      type: {tp}")
        else:
            semantics[name] = {"error_class": ec, "error_reason": er}
            print(f"  {name:16} class={ec} {er}")
    findings["move_module_semantics"] = semantics

    # GraphQL `module` filter vs `type` filter — is either equivalent to MoveModule?
    section("5c. GraphQL module/type filter probes (equivalence evidence)")
    for label, filt in [
        ("module=0x2::coin", {"module": "0x2::coin"}),
        ("module=0x2", {"module": "0x2"}),
        ("type=0x2::coin", {"type": "0x2::coin"}),
    ]:
        q = ("query($f:EventFilter){events(first:5,filter:$f){"
             "pageInfo{hasNextPage endCursor} nodes{__typename}}}")
        st, parsed, body, (ec, er) = live.gql(q, {"f": filt}, label=f"gql {label}")
        if parsed and parsed.get("data") and parsed["data"].get("events"):
            e = parsed["data"]["events"]
            print(f"  {label:16} -> nodes={len(e['nodes'])} hasNextPage={e['pageInfo']['hasNextPage']}")
        else:
            print(f"  {label:16} -> class={ec} ERR={er}")

    dump_rows(live.rows, str(FIX / f"discovery_{DATE}.rows.jsonl"))
    (FIX / f"discovery_{DATE}.summary.json").write_text(json.dumps(findings, indent=2))
    print(f"\n  wrote {len(live.rows)} observation rows")
    live.close()


def _type_name(t):
    if not t:
        return "?"
    if t.get("name"):
        return t["name"]
    of = t.get("ofType")
    inner = _type_name(of) if of else "?"
    kind = t.get("kind")
    if kind == "NON_NULL":
        return f"{inner}!"
    if kind == "LIST":
        return f"[{inner}]"
    return inner


if __name__ == "__main__":
    main()
