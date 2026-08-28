# Source manifest and claim ledger

| ID | Source | Supports | Grade | Ceiling / caution |
|---|---|---|---|---|
| S1 | Authenticated LabLab event page, 2026-08-28 | challenge, options requirement, new $100k account, criteria, prizes, submission fields | C2 | Dynamic platform observation; recheck before submit |
| S2 | `evidence/organizer-pnl-window-discord.png` + SHA-256 in decision JSON | Mon Aug 31 09:30 ET–Fri Sep 4 09:30 ET P&L window; new account | C2 | Authenticated organizer observation, not an API contract |
| S3 | `evidence/organizer-raw-equity-snapshot-discord.png` + SHA-256 in decision JSON | final result described as raw equity snapshot | C2 | Does not resolve pre-open option marks or Thursday settlement |
| S4 | [LabLab submission guidance](https://lablab.ai/delivering-your-hackathon-solution) | required artifacts and form workflow | C2 | General guidance can be overridden by event form |
| S5 | [LabLab hackathon rules](https://lablab.ai/hackathon-rules) | teams, conduct, prize/eligibility boundary | C2 | Legal eligibility remains the participant's responsibility |
| S6 | [LabLab how-to-win guide](https://lablab.ai/guide/how-to-win-an-ai-hackathon) | pitch structure, working demo, rubric alignment | C2 | Advice, not a winning guarantee |
| S7 | [Official Alpaca CLI docs](https://docs.alpaca.markets/us/docs/alpacas-cli) | CLI requirement route and paper behavior | C2 | CLI is an execution surface; our local adapter remains separately locked |
| S8 | [Official Alpaca multi-leg docs](https://docs.alpaca.markets/us/docs/options-level-3-trading) | `mleg` order shape and Level 3 requirement | C2 | Broker acceptance/fills still require authenticated paper observation |
| S9 | Local `scripts/verify.py` receipt | deterministic mechanics and negative controls | C1 | Does not establish broker connectivity, alpha, profit, or future safety |
| S10 | Current event team pages, 2026-08-28 | competitor wording patterns | C2 for page text | Dynamic, incomplete, and not evidence of product quality |

## Frozen claims

- **C2:** The official scoring window and raw-equity language are organizer observations preserved
  with screenshot hashes.
- **C1:** AlphaLedger's deterministic clock, normalizers, risk gates, locked official-CLI adapter,
  state ownership, and replay controls execute locally under tests.
- **C0:** Expected profit, likelihood of winning, true options alpha, future fill quality, Friday
  option marking, and Thursday-expiry settlement behavior remain unproven.

## Falsifiers and stop rules

- A rule or organizer clarification conflicts with the frozen window.
- The account is not the pinned brand-new $100,000 paper account.
- Observed positions do not exactly equal the controller-owned legs.
- A second writer, live environment, stale/malformed evidence, unknown order state, missing Greek,
  wide market, loss limit, or unsupported shape reaches execution.
- Any test, secret scan, signed-out judge path, PDF render, or final artifact-link check fails.

On any falsifier: abstain or halt, reconcile, preserve a redacted receipt, and do not broaden
authority to live trading, unrelated cloud resources, public posting, or submission.
