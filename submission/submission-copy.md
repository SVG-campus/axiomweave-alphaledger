# LabLab submission copy

## Team

**Team name:** AxiomWeave AlphaLedger

**Team description:** We are building an abstention-first Alpaca options agent that turns every
trade—or refusal—into a replayable risk and evidence receipt. We welcome teammates who can sharpen
options execution, product storytelling, or judge outreach.

## Project form

**Project title:** AxiomWeave AlphaLedger

**Track:** Options Alpha Agents

**Short description — 220 characters:**

AlphaLedger is an abstention-first Alpaca options agent. It proposes capped-loss SPY debit spreads,
lets AI veto but never authorize, independently gates risk, and records every trade or refusal in a
hash-linked receipt.

**Long description — use as one block:**

AxiomWeave AlphaLedger is an evidence-gated options agent built for Alpaca paper trading. During the
official Aug 31–Sep 4 measurement window, one deterministic controller observes SPY, proposes a
same-expiration call or put debit spread, and independently recomputes its debit, width, maximum
loss, breakeven, liquidity, and quote freshness. An optional structured AI critic can surface risks
or veto a proposal, but it can never authorize a trade.

Only a one-to-one capped-loss structure that passes the clock, paper-account, feed, Greeks,
liquidity, position, order, capital, and drawdown gates can become an official Alpaca CLI multi-leg
paper order. Every pass, refusal, submission, cancellation, fill, and reconciliation is written to
a hash-linked receipt journal. Judges can change one falsifiable fact—such as quote age, missing
Greeks, market width, maximum loss, account identity, or broker mode—and watch the agent fail
closed.

The competition policy allows one $250-risk attempt per day, one open plan, a $500 daily stop, a
$1,000 total drawdown stop, a 45-minute maximum hold, and a Thursday 3:45 p.m. ET force-flat rule.
We tested bounded five-minute and two-year hourly signal families, but neither cleared its frozen
held-out promotion gate. We therefore label the opportunity route C0 exploratory rather than claim
proven alpha. Local tests establish C1 deterministic mechanics; organizer screenshots establish
the C2 timing observation. They do not establish profit, future fills, or competition rank.

The credential-free Streamlit demo exposes the decision path, falsifiers, benchmark refusal, and
evidence chain without any broker capability. A separate isolated GCP runner pins the exact fresh
$100,000 paper account, uses Alpaca's official CLI, and requires an explicit human acknowledgement
before paper-order mode can start. AlphaLedger's wedge is decision provenance for autonomous
finance: proof before profit.

## Technologies

- Python
- Streamlit
- Alpaca Trading API
- Alpaca CLI
- Alpaca Paper Trading
- Options / multi-leg orders
- Google Cloud Compute Engine
- Google Secret Manager
- systemd and Nginx
- SHA-256 evidence receipts
- OpenAI Structured Outputs (optional veto-only critic)

## Categories

- AI Agents
- Finance / Fintech
- Options Trading
- Risk Management
- Explainable AI
- Developer Tools

## Submission links

- Public GitHub: <https://github.com/SVG-campus/axiomweave-alphaledger>
- Deployed demo: <http://34.27.11.180>
- YouTube video: **TBD**
- Team page: <https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon/axiomweave-alphaledger>
- Paper account ID: enter only in the private submission field; never in the repository or video.

## Judging map

- **P&L Performance:** bounded one-attempt-per-day route, deterministic exits, hard drawdown stops,
  and clock-aware force-flat behavior.
- **Technology Implementation:** official Alpaca CLI, multi-leg paper orders, strict normalization,
  exact-account reconciliation, isolated single writer, and hash-linked receipts.
- **Creativity & Originality:** AI can veto but never authorize; abstention is a first-class output;
  failed promotion evidence remains visible.
- **Presentation & Execution:** one-variable pass-to-refusal demo, working public dashboard, concise
  deck/video, and falsifiable claim ceilings.

## Claim boundary

Say: **“C1 deterministic mechanics, C2 organizer timing evidence, and a C0 exploratory signal.”**

Do not say: guaranteed, profitable, proven alpha, safest, compliant, production-ready, or certain
to win.
