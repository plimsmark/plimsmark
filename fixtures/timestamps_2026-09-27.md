# Timestamp ground truth — 2026-09-27

Run 2 showed GraphQL and legacy JSON-RPC reporting different timestamps for the
same event (GraphQL earlier). This establishes which one matches the chain.

- Vantage `local-dev`, UA `plimmark-sui-spike/0.1`. Every value below is verbatim
  from a live response on 2026-09-27; raw rows in
  `ground_truth_2026-09-27.rows.jsonl`, structured data in
  `ground_truth_2026-09-27.data.json`. Re-verify; these go stale.
- Field names re-checked against the live schema and live responses, not memory:
  GraphQL `transactionEffects(digest).checkpoint{sequenceNumber timestamp}`,
  `.events{nodes{sequenceNumber timestamp}}`, `checkpoint(sequenceNumber){timestamp}`;
  JSON-RPC `suix_queryEvents [{Transaction:<digest>}]` (event `timestampMs`),
  `sui_getTransactionBlock` (`timestampMs`, `checkpoint`), `sui_getCheckpoint`
  (`timestampMs`).

## Method

The edge set was **re-derived live** from `premise_2026-09-27_run2.jsonl.gz`: the
Q2 recent_1h events present on GraphQL but outside the JSON-RPC ts-window
(GraphQL 603 − JSON-RPC 582 = 21 events across **7 transactions**), plus the
`oldest_available` event's transaction `99R6bU7…`. Total **8 transactions**. No
IDs were hardcoded.

For each tx: (a) GraphQL event timestamp + containing checkpoint (seq + ts);
(b) each JSON-RPC provider's `suix_queryEvents` event `timestampMs` and
`sui_getTransactionBlock` `checkpoint` + `timestampMs`; (c) that checkpoint's own
timestamp fetched independently by sequence number on both paradigms.

## Per-transaction results (verbatim ms)

`cp` = containing checkpoint. `Δ` = JSON-RPC `suix_queryEvents` event ts − cp ts.

| tx (first 12) | cp seq | cp ts (ms) | GraphQL event ts | JSON-RPC `sui_getTransactionBlock` tx ts | JSON-RPC `suix_queryEvents` event ts (publicnode / blockvision / rpcpool) | Δ range (ms) |
|---|---|---|---|---|---|---|
| 2BVReXAbkLfX | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | 1790499790962 / …933 / …934 | +639…+668 |
| 33WLVTiGMtkB | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …962 / …934 / …934 | +640…+668 |
| 6WsJhzAgaQ2A | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …963 / …934 / …935 | +640…+669 |
| 8LTUeFrp7vFp | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …962 / …933 / …934 | +639…+668 |
| 9NPnNq41hwZj | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …962 / …933 / …934 | +639…+668 |
| E6U9R76xsme4 | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …962 / …937 / …935 | +641…+668 |
| HXRxTUp934ME | 327453834 | 1790499790294 | 1790499790294 | 1790499790294 (all 3) | …962 / …933 / …934 | +639…+668 |
| 99R6bU7AgKUe | 273221834 | 1778194391512 | 1778194391512 | 1778194391512 (all 3) | 1778194392276 / …305 / …263 | +751…+793 |

Checkpoint `327453834` timestamp = `2026-09-27T09:03:10.294Z`; checkpoint
`273221834` timestamp = `2026-05-07T22:53:11.512Z`. The checkpoint's own timestamp
fetched independently by sequence number agrees across paradigms — GraphQL,
publicnode, and rpcpool all returned the same ms. (blockvision `sui_getCheckpoint`
returned no body on 3 of 8 calls during the run due to `429` rate-limiting; on
retry it returns the identical timestamp, so this is transient, not disagreement.)

## Conclusion

For all **8/8** transactions:

1. **Both paradigms agree on WHICH checkpoint contains the transaction** (GraphQL
   `transactionEffects.checkpoint.sequenceNumber` == every JSON-RPC provider's
   `sui_getTransactionBlock.checkpoint`).
2. **GraphQL's event timestamp equals the containing checkpoint's own timestamp**
   (8/8) — GraphQL matches the chain.
3. **JSON-RPC `suix_queryEvents` event `timestampMs` is 639–793 ms LATER than the
   containing checkpoint's timestamp** (24/24 provider×tx) — it matches neither
   the checkpoint nor GraphQL.
4. The **same** JSON-RPC provider's `sui_getTransactionBlock` transaction
   `timestampMs` **equals the checkpoint timestamp** (24/24). So the offset is
   internal to the legacy `suix_queryEvents` event records, not a chain-level
   disagreement about when the transaction executed.

**Ground truth = the containing checkpoint's timestamp = GraphQL's event
timestamp.** The result is not mixed: GraphQL is correct on every transaction;
legacy JSON-RPC `suix_queryEvents` event timestamps run a fraction of a second
late (here 0.64–0.79 s) and disagree with the same node's own transaction
timestamp. This is why a *timestamp-bounded* window drops a different edge set on
each paradigm even though the events exist in both indexes (see
`premise_2026-09-27.md` §6). It is a timestamp-representation defect in the
deprecated JSON-RPC event API, not an index completeness or freshness difference.
