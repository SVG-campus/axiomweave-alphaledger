# August 31 options-data incident

Status: repaired and verified. All times below are August 31, 2026, Pacific daylight time;
add three hours for Eastern. This was an options-data availability incident, not an account loss.

## What happened

The options-contract catalog contained more than 1,000 records. The reader requested one page,
but the normalizer correctly rejected the returned continuation token because the catalog was
incomplete. The runner stayed active and recorded abstentions instead of submitting an order.

## Measured timeline

| Event | Pacific time |
|---|---|
| First logged options-evidence failure | 07:21:58 |
| Hourly monitor detected repeated failures | 07:33:59 |
| Exact pagination cause reproduced read-only | 07:35:11 |
| Authorized repair work observed beginning | 07:45:46 |
| 102 local tests passed | 07:50:05 |
| Complete 1,041-contract, two-page probe passed | 07:55:23 |
| Named runner stopped after flat-account reconciliation | 07:57:25 |
| Named runner restarted on the repaired commit | 07:57:44 |
| First post-restart controller receipt | 07:57:45 |
| Account, service, and log continuity verified | 07:58:38 |

First observed failure to verified recovery: **36 minutes 40 seconds**. Detection to verification:
**24 minutes 39 seconds**. The deliberate service pause for deployment and VM tests was **19.44
seconds**. These are measured intervals, not a claim that every cycle in the interval would have
traded. Some signals were legitimately neutral. Exact UTC timestamps are retained in the JSON receipt.

## Repair and verification

- Deployed code commit: `d657f2f8a4ba141c683b7b513001bcfc9b32759c`.
- Retrieve every contracts/snapshots page with unchanged request filters.
- Reject loops, malformed pages/tokens, duplicate symbols, failed requests, and incomplete results.
- Bound each options dataset to 10 pages, 10,000 records, and a 20-second acceptance budget.
- Bind original page hashes and the merged dataset in the evidence hash.
- 102/102 local tests passed. On Linux, 101 passed and the Windows-only test was skipped.
- Original state and journal were backed up and preserved. The earlier journal anchor still matched.
- Strategy, risk limits, clock, executor, account, credentials, and paper-enable flag were unchanged.

Two diagnostic-harness errors were also retained: an import-order error before network access and
a neutral-signal proposal check after successful normalization. Neither altered the running controller.

## Impact and limits

At 07:58:38 Pacific, equity was **$100,000**, daily P&L **$0**, with **zero orders, positions, or open
orders**. The first post-restart cycle abstained because its signal was below threshold. Recovery
does not mean a trade must occur. We cannot infer the value of missed opportunities or claim that
this repair improves the signal's profitability.

## Prevention and resource synchronization

The regression suite now exercises both paginated datasets and adverse pagination cases. Hourly
checks must distinguish legitimate neutral/risk refusals from repeated infrastructure failures.
Material incidents and changes must update the public-safe status snapshot, this incident record,
README/runbook, presentation, narration, and submission copy. Preserve historical receipts; never
rewrite old results to make them look current. A changed slide does not automatically update an
already-recorded video, uploaded social post, or submitted form; those require a new owner-reviewed
recording/upload/submission.

Sources: [incident receipt](../evidence/incidents/2026-08-31-options-pagination.json),
[public status snapshot](../evidence/public-operation-status.json),
[Alpaca contracts pagination](https://docs.alpaca.markets/us/reference/get-options-contracts),
[Alpaca snapshots pagination](https://docs.alpaca.markets/us/reference/optionchain).
