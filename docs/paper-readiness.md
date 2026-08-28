# Dedicated Alpaca paper-readiness gate

The active-phase track brief and organizer window have been captured. The public
demo and video still need no Alpaca credentials.

## What the gate does

`scripts/paper_readiness.py` can make exactly three authenticated GET requests:

1. `https://paper-api.alpaca.markets/v2/account`
2. `https://paper-api.alpaca.markets/v2/positions`
3. `https://paper-api.alpaca.markets/v2/orders?status=open`

The observer exposes no generic request method, rejects the live trading host,
rejects redirects, and has no POST, PATCH, PUT, DELETE, cancel, exercise, or
order-submission method.

The printed receipt omits API credentials and account ID. It reports only the
paper status, capital fields, options levels, position/order counts, blocked
state, request IDs, and source endpoints.

## When to run it

Run only after the new competition account exists and before paper-order activation.

From a private local PowerShell window:

```powershell
cd path\to\axiomweave-alphaledger
python .\scripts\paper_readiness.py --ack-readonly
```

If private environment variables are absent, the script asks for the paper key
ID and a hidden paper secret. It does not write either value to a file. Do not
paste them into chat, source code, screenshots, the video, a browser field, or
a public deployment.

## Pass conditions

- Account status is `ACTIVE`.
- No trading/account/user suspension is active.
- Options approved and trading levels are at least 3.
- Equity and buying power are positive; cash is non-negative.
- Positions and open orders are empty.

Any nonpass is retained as evidence. A passing GET-only receipt permits further
paper observation; it does not authorize an order.

## Optional six-GET observation bridge

After the three-request readiness gate passes, `scripts/paper_observe.py` can add exactly three market-data
GETs: the SPY stock snapshot, active call-contract catalog, and option-chain
snapshot. It strictly normalizes the three payloads, preserves the stock and
options feed labels, rejects pagination and future timestamps, then runs the
same deterministic policy used by the public demo. It still has no order-send
method.

Choose the expiration and strike window only after viewing the kickoff rules
and current SPY price. Example shape—not a recommendation to run before then:

```powershell
python .\scripts\paper_observe.py `
  --ack-six-get-readonly `
  --expiration-gte 2026-09-04 `
  --expiration-lte 2026-10-09 `
  --strike-gte 550 `
  --strike-lte 650 `
  --stock-feed iex `
  --options-feed indicative
```

Use `opra` or `sip` only if the dedicated account is entitled to those feeds.
The redacted output includes payload hashes and the governed decision, not raw
payloads, account ID, or credentials. A PASS is a simulated order plan and
does not authorize sending it.
