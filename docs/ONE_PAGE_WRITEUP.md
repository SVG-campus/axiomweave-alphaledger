# AlphaLedger — AI logic, risk management, and Alpaca infrastructure

## System objective

AlphaLedger is an abstention-first options agent for Alpaca paper trading. Its competition objective
is to participate in the organizer-defined Aug 31–Sep 4 P&L window while keeping the maximum loss
of every plan known before submission. Its broader objective is decision provenance: every proposed
trade, refusal, broker action, and reconciliation becomes a replayable receipt.

## AI logic

The agent observes fresh SPY bars and typed Alpaca option evidence, then constructs a directional
same-expiration call or put debit spread. A limited signal policy chooses whether the direction is
eligible; it does not bypass the risk system. An optional structured AI critic can identify
contradictions, missing evidence, or reasons to abstain. The critic is deliberately veto-only: it
cannot authorize an order, enlarge a position, change the clock, select a live endpoint, or override
deterministic policy.

The signal remains C0 exploratory. A frozen 60-day five-minute search found a least-weak held-out
proxy, but its mean did not exceed its standard error and it failed a five-basis-point stress. A
separate two-year hourly search chose a route on validation that lost on untouched test data. No
signal was promoted. These negative results are retained as evidence and bound the project's claims.

## Deterministic risk management

Only one-to-one capped-loss SPY debit spreads are eligible. Before any paper order, AlphaLedger
independently recomputes debit, width, maximum loss, maximum profit, and breakeven from the quoted
legs. It rejects stale or future timestamps, unknown feeds, missing Greeks, wide markets, low open
interest, mixed call/put types, malformed OCC symbols, inconsistent ratios, and economics that do
not match the quotes.

The frozen competition policy permits one open plan and one entry per session, with new entries only
Mon–Thu from 10:20–14:30 ET. Maximum plan loss and aggregate open risk are $250; the daily loss stop
is $500; the total drawdown stop is $1,000; the maximum hold is 45 minutes; take-profit and stop-loss
triggers are +25% and −20% of premium. The controller force-closes and reconciles positions by Thu
Sep 3 at 15:45 ET. The organizer confirmed a raw-equity snapshot Fri at 09:30 ET but has not yet
specified pre-open option marking or Thursday-expiry settlement, so holding through the cutoff is
disabled.

## Alpaca infrastructure

AlphaLedger uses Alpaca's official CLI and documented `mleg` order shape in the paper environment.
The controller pins a SHA-256 digest of the exact new account ID and requires an ACTIVE account,
exactly $100,000 fresh equity/cash, Level 3 options permission, and no starting positions or orders.
Every later cycle reconciles the exact option symbols, signed quantities, and deterministic client
order IDs owned by AlphaLedger. A process lock enforces one writer. State writes are atomic; the
receipt journal is hash linked. Paper submissions, cancellations, and closes use bounded retries and
fail closed on ambiguous broker state. Live hosts and live-mode environment flags are rejected.

The deployment separates a credential-free public Streamlit demo from a non-login runner service on
an isolated Google Cloud VM. Credentials and the private account identifier are entered through a
local hidden-input script into three dedicated Secret Manager secrets. The runner starts disabled,
then may enter GET-only observe mode. Paper-order mode requires the exact human acknowledgement
`I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER`; the competition clock still prevents weekend entries.

## Evidence ceiling

Passing local verification establishes C1 deterministic mechanics and falsifiers, not profitability
or production safety. Authenticated organizer screenshots support the C2 timing observation.
Profitability, fills, Friday option values, and winning probability remain C0. No authenticated
broker request or paper order was sent during development or verification.
