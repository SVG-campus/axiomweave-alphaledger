# AxiomWeave AlphaLedger

**Proof before profit.** AlphaLedger is an abstention-first, defined-risk options agent built for
the 2026 Alpaca AI Trading Agents Hackathon. It converts each proposed SPY call or put debit
spread—and every refusal—into a replayable evidence receipt.

![AlphaLedger cover](assets/alphaledger-cover.png)

[Live demo](http://34.27.11.180) ·
[Public repository](https://github.com/SVG-campus/axiomweave-alphaledger)

## What judges can test

1. Run a valid capped-loss spread and inspect the quote-derived economics and Alpaca `mleg` plan.
2. Change one fact—freshness, Greeks, liquidity, loss, account mode, or order state—and watch the
   system abstain.
3. Verify that passes and refusals share one SHA-256 hash chain.
4. Open **Competition control** to see the official clock, frozen capital limits, and the signal
   promotion refusal.

The public Streamlit app never receives Alpaca credentials and cannot send an order.

```powershell
cd path\to\axiomweave-alphaledger
python .\scripts\verify.py
streamlit run app.py
```

## Competition controller

The private runner is a single-writer state machine around the official organizer window:

- P&L measurement: **Mon Aug 31, 09:30 ET–Fri Sep 4, 09:30 ET**.
- New-entry window: **Mon–Thu, 10:20–14:30 ET**.
- Default force-flat: **Thu Sep 3, 15:45 ET**.
- Underlying: SPY; one open plan; one entry per day.
- Maximum plan and aggregate open loss: **$250**.
- Daily stop: **$500**; total drawdown stop: **$1,000**.
- Take profit: **+25%**; stop loss: **−20%**; maximum hold: **45 minutes**.

Before any submission, the runner pins the exact new paper account, requires a $100,000 fresh
baseline, Level 3 options permission, zero positions/orders, paper endpoints, and exclusive writer
ownership. It submits only same-expiration 1:1 call or put debit spreads through the official
Alpaca CLI. Pending and closing orders are reconciled by deterministic client IDs.

The organizer confirmed a Friday 09:30 ET **raw-equity snapshot** but has not yet clarified how an
open option is marked before the Friday options session or whether Thursday exercise/assignment
settlement will have posted. The hold-through-cutoff override therefore remains disabled.

## Signal evidence—promotion refused

Two bounded historical searches were frozen:

- A 60-day SPY five-minute study found a least-weak held-out directional proxy, but its mean did
  not exceed its standard error and it failed a five-basis-point stress.
- A two-year hourly regime search selected mean reversion on validation and then lost on the
  untouched test.

No route cleared the promotion gate. The one small daily attempt remains **C0 exploratory**—not
proven alpha. The purpose of the system is disciplined opportunity plus bounded downside, not a
promise of profit.

## Architecture

```text
Official clock + exact paper account + positions/orders
                         |
Fresh SPY bars + typed option-chain evidence
                         |
Directional spread proposal <--- optional AI critic (veto only)
                         |
Deterministic risk/economics gate
             | PASS                         | FAIL
             v                              v
Official Alpaca CLI paper order          ABSTAIN
             \______________________________/
                         |
Reconciliation + hash-linked receipt journal
```

AI never holds execution authority. It can surface concerns or veto; only deterministic policy can
permit a plan. Unknown feeds, stale quotes, missing Greeks, wide markets, insufficient open
interest, malformed contracts, account mismatch, foreign positions, a second writer, live hosts,
or an invalid clock phase all fail closed.

## Evidence status

- **C1:** local deterministic mechanics, negative controls, replay integrity, app rendering, and
  broker-command construction after `scripts/verify.py` passes.
- **C2:** organizer timing and raw-equity wording preserved as authenticated screenshot hashes.
- **C0:** profitability, future fills, mark quality, competition rank, and production safety.

No broker request or order was sent while building or verifying this repository.

## Deployment and private activation

The GCP package creates only new `alphaledger-*` resources in the designated project: a small
isolated VM, custom network, separate no-login runner, public credential-free demo, and three
Secret Manager entries. The runner starts disabled. See [the deployment guide](deploy/gcp/README.md)
and [competition runbook](docs/COMPETITION_RUNBOOK.md).

Never paste API keys into chat, source, screenshots, logs, or the public app. The local hidden-input
script is the only prepared secret-ingestion route. Paper order submission additionally requires:

`I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER`

## Judge package

- [Event and rule brief](docs/event-brief.md)
- [One-page AI, risk, and Alpaca infrastructure write-up](docs/ONE_PAGE_WRITEUP.md)
- [Competition runbook](docs/COMPETITION_RUNBOOK.md)
- [Submission walkthrough](docs/SUBMISSION_WALKTHROUGH.md)
- [Submission copy](submission/submission-copy.md)
- [Video script](submission/video-script.md)
- [Social copy](submission/social-posts.md)

Educational hackathon software only; not investment advice. Paper trading is a simulation and does
not reproduce every feature of live markets. MIT licensed.
