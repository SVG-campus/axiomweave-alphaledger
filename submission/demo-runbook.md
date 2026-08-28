# Demo runbook

## 1. Install and verify

From PowerShell in the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python .\scripts\verify.py
```

Expected verification: exit code 0, all tests passing, fresh receipt, C1 claim ceiling.

## 2. Start the local dashboard

```powershell
streamlit run .\app.py
```

No Alpaca or OpenAI credentials are needed for the public simulation path.

## 3. Rehearse the golden judge path

1. **Options agent:** select **Valid defined-risk spread** and click **Run
   options evidence cycle**. Confirm CALL DEBIT, $20.00 maximum loss, PASS,
   SIMULATED, and a two-leg Alpaca `mleg` plan.
2. Select **Stale option evidence** and run again. Confirm ABSTAIN, no order
   payload, and both stale-contract reasons.
3. **Evidence ledger:** confirm both decisions and a VERIFIED hash chain.
4. **Evaluation readiness:** show the frozen options manifest, the governed,
   unguarded, cash, and shuffled controls; then point to the six-route GET-only
   Alpaca surface and frozen IEX + indicative bridge check showing PASS/$20.
5. **Replay & controls:** identify the retained equity baseline as a negative
   control—not an options-profit claim.
6. **AxiomWeave packet:** state the C1 mechanics ceiling and C2 organizer evidence that judges use
   EOD Thursday total equity and include Sep 3 expiry exercise/assignment.

## 4. Optional structured OpenAI adviser

This lane is not required for the reproducible video. If explicitly enabled,
provide `OPENAI_API_KEY` and an explicit `ALPHALEDGER_ADVISORY_MODEL` in the
private local environment. The adviser receives the sanitized thesis only,
uses structured output with storage disabled, and may only veto. Missing
configuration, errors, or an abstain recommendation force abstention.

Never put secrets in chat, code, screenshots, Streamlit fields, or deployment
logs.

## 5. Alpaca paper gate after kickoff

Before any broker interaction:

1. Confirm the endpoint and account are paper-only.
2. Keep credentials in a dedicated local secret profile.
3. Fetch account, options level, positions, and open orders read-only.
4. Require zero unreconciled orders and enough buying power for recomputed loss.
5. Confirm the organizer's evaluation method and whether a paper-order clip is
   required.
6. If separately authorized, send at most one one-contract, same-expiration,
   capped-loss vertical within the $25 modeled-loss budget; immediately
   reconcile and record the broker receipt.
7. Return execution to disabled after the clip.

The first authorized account contact should be `python
.\scripts\paper_readiness.py --ack-readonly`; see `docs/paper-readiness.md`.
Only after it passes and the evaluation route is confirmed, the separately
acknowledged `scripts/paper_observe.py` path may fetch stock, contracts, and
chain data, normalize them, and produce a redacted governed receipt. It still
sends no order.

The paper account identifier is not needed in the video. API key and secret are
secrets and should not be pasted into chat.

## 6. Judge-path falsifiers

- A 181-second option quote must abstain.
- A 181-second underlying trade or unknown feed must abstain.
- A future timestamp, symbol mismatch, or pagination token must fail closed.
- Missing delta or implied volatility must abstain.
- A relative bid-ask spread above 35% must abstain.
- Open interest below 100 must abstain.
- A recomputed maximum loss above $25 must abstain.
- Claimed economics that differ from quote-derived economics must abstain.
- Cash or buying power below recomputed maximum loss must abstain.
- Any live broker mode or unreconciled open order must abstain.
- Any ledger mutation must make chain verification fail.
