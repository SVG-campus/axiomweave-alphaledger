# AlphaLedger competition runbook

All times are America/New_York. This runbook is paper-only. Stop on any account mismatch, foreign
position/order, live endpoint, missing evidence, secret exposure, second writer, or failed check.

## Before activation — Aug 28–30

1. Run `python .\scripts\verify.py`; require exit 0 and a fresh verification receipt.
2. Publish one reviewed commit and deploy that immutable commit.
3. Verify the public demo signed out; confirm it contains no account ID, credentials, or order path.
4. Run `deploy\gcp\set-paper-secrets.ps1` locally. Enter the paper API key, secret, and the new
   user-visible `PA...` paper account number only in hidden prompts.
5. Run `deploy\gcp\start-observe.ps1`.
6. In redacted logs require: paper host, ACTIVE, $100,000 fresh baseline, Level 3, no positions, no
   open orders, exact account pin, fresh SPY data, and one writer.
7. Verify the preserved Erika clarification: EOD Thursday total equity is the scoring basis and
   Sep 3 expiry exercise/assignment is reflected. Keep the 15:45 ET force-flat policy.
8. At the final activation gate, type the exact acknowledgement only after reading the displayed
   warning: `I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER`.

Activating over the weekend does not trade: the controller remains PREWINDOW until Mon 09:30 and
does not allow a new entry before 10:20.

## Monday Aug 31

- 09:20: verify service health, clock, paper endpoint, exact account, exclusive writer, no orders.
- 09:30–10:20: observe only; record baseline raw equity and reconcile flat status.
- 10:20–14:30: at most one gated attempt. No pass means no order.
- Every minute: reconcile order state, positions, limits, and receipt continuity.
- Exit at +25%, −20%, 45 minutes, risk stop, stale/unknown data, or ownership ambiguity.
- After 14:30: exits and reconciliation only.

## Tuesday–Wednesday

- Repeat the Monday preflight and one-attempt limit.
- Do not modify thresholds from competition observations.
- Treat scheduled macro releases as volatility context, not permission to bypass gates.
- Stop new entries for the day after $500 realized/unrealized daily loss; stop the competition route
  after $1,000 drawdown from the $100,000 baseline.

## Thursday Sep 3

- Treat the portfolio's EOD total equity as the organizer-confirmed scoring basis.
- Follow the same entry window, but never open a position that cannot be closed and reconciled before
  the force-flat boundary.
- 15:30: stop all optional activity; inspect orders and positions.
- 15:45: cancel exact owned pending orders, close exact owned legs, and reconcile flat status.
- 15:45–16:00: continue bounded close/reconciliation only. Any residual is an incident, not a reason
  to improvise.

## Friday Sep 4

- Scored equity is already based on EOD Thursday; do not attempt to change the score Friday morning.
- 09:20: require flat positions/orders and intact journal; capture redacted account status.
- 09:30: record the window-end observation and stop the competition controller.
- Do not submit a Friday trade after the measurement boundary.
- LabLab submission deadline: 08:00 PDT / 11:00 ET. The form should already be complete and tested.

## Incident rules

- **Ambiguous broker response:** do not retry blindly; reconcile by deterministic client ID.
- **Pending order older than three minutes:** cancel only after exact one-to-one order lookup.
- **Close failure:** bounded unique retry IDs 0–9; keep reconciling; do not open new risk.
- **State/journal tamper:** stop writer and preserve files.
- **Service restart:** exact state/account/position reconciliation before resuming.
- **Unexpected cost:** stop or resize infrastructure before the $10 soft GCP budget.
- **Secret exposure:** disable the affected secret/version and rotate through the user's Alpaca/GCP
  controls; never paste the value into an issue or chat.

## Manual owner-only actions

- Provide/rotate Alpaca paper credentials through the hidden local prompt.
- Type the paper-order acknowledgement.
- Approve any public social post, Discord message, video upload, or final LabLab submission at action
  time.
