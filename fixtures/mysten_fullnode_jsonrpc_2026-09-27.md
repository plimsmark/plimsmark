# Mysten public fullnode JSON-RPC — re-verified 2026-09-27

First-party re-verification of the Mysten public fullnode JSON-RPC deprecation
(the pinned spike providers do not include it, so this was captured separately).
Vantage `local-dev`, UA `plimmark-sui-spike/0.1`. Verbatim; re-verify, it goes stale.

- Endpoint: `https://fullnode.mainnet.sui.io`
- Request: `{"jsonrpc":"2.0","id":1,"method":"sui_getLatestCheckpointSequenceNumber","params":[]}`
- UTC: 2026-09-27T11:31:22.231205+00:00
- HTTP status: 200
- JSON-RPC error code: `-32601`

Verbatim error message:

```
Method not found. JSON-RPC on public fullnodes has been deprecated. Please migrate to gRPC or GraphQL endpoints. See https://docs.sui.io/develop/accessing-data/json-rpc-migration for more information.
```

Full verbatim response body:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found. JSON-RPC on public fullnodes has been deprecated. Please migrate to gRPC or GraphQL endpoints. See https://docs.sui.io/develop/accessing-data/json-rpc-migration for more information."
  },
  "id": null
}
```

**Conclusion:** the public fullnode JSON-RPC surface returns `-32601` (method not
found) — it is deprecated in favour of GraphQL/gRPC. This matches the earlier
reference observation (`reference/observed_2026-09-27-sui.md` §1) and is now
first-party dated evidence.
