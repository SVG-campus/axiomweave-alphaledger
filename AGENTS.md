# AlphaLedger agent instructions

This repository is a hackathon prototype for Alpaca paper trading. It is not a
profitability claim, investment recommendation, or live-trading authorization.

- Keep all broker actions paper-only and default-off.
- Never add live credentials, live endpoints, or a live-order path.
- Preserve abstentions, rejected decisions, failures, and negative controls in
  the evidence ledger.
- Deterministic risk policy has final authority over any model or agent output.
- Treat passing tests as mechanics evidence only (C1), not financial evidence.
- Do not deploy, publish, connect accounts, or submit forms without explicit
  user authorization.
- Run `python scripts/verify.py` after material changes.
