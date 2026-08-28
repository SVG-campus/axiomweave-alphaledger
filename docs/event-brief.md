# Alpaca AI Trading Agents Hackathon — current event brief

Retrieved from the authenticated LabLab event and submission pages on **2026-08-28**.
Dynamic counts, links, and prize text must be checked again immediately before submission.

## About and challenge

- Online event: **28 August–4 September 2026**.
- Submission deadline shown by the active event: **4 September, 8:00 a.m. PDT**.
- Build an autonomous AI trading agent using Alpaca's Trading API.
- The project must use the **Alpaca MCP server or Alpaca CLI**.
- Every strategy must incorporate **options**.
- Trading is in Alpaca's **paper environment**, not a live-money account.
- The final competition account must be **brand new** and begin at exactly **$100,000**. A reused account is ineligible.
- The project needs a one-page explanation of its AI logic, risk gates, and Alpaca infrastructure.

## Organizer-defined P&L window

Erika, posting from the authenticated Alpaca organizer account in the event Discord, wrote:

> We start measuring P&L Mon Aug 31 -9:30 a.m. ET to Sep 4 9:30 am ET make sure to open a new account

When asked whether Thursday-expiry settlement would be included or whether the result was a raw snapshot, Erika replied:

> hi raw equity snapshot

The screenshots and hashes are preserved in `evidence/competition-window-decision.json`.
These are C2 authenticated organizer observations. They establish the time window and raw-equity
scoring language, but do not yet establish how Alpaca will mark an open option before the Friday
options session or whether Thursday exercise, assignment, or cash settlement will have posted.

AlphaLedger therefore permits new entries Monday through Thursday and defaults to force-flat on
**Thursday 3 September at 3:45 p.m. ET**. It keeps enforcing/reconciling flat status through the
Friday cutoff. A hold-through-cutoff override is disabled unless the organizer answers the open
valuation question unambiguously.

## Prizes

The active detailed event page showed **$6,000 cash plus $300 in credits**:

- 1st: **$2,500 cash + $300 Featherless credits**.
- 2nd: **$1,500 cash**.
- 3rd: **$1,000 cash**.
- Social engagement: **two $500 winners**, plus one month of Alpaca Algo Trader Plus for each
  winning team member.

The hero uses a rounded **$6,000 prize pool** label while the itemized package totals **$6,300**
when credits are included. Submission copy should avoid claiming a single total beyond the
itemized organizer text.

## Judging criteria

The current event-specific criteria are:

1. **P&L Performance** — performance in the new $100,000 paper account during the official window.
2. **Technology Implementation** — effective Alpaca and AI integration.
3. **Creativity & Originality** — differentiation and demonstrated novelty.
4. **Presentation & Execution** — a clear story and working judge path.
5. **Social quality and engagement** — relevant to the separate social awards.

No organizer source establishes a formula, weights, or tie-break order. AlphaLedger treats each
criterion as material without inventing percentages.

## Required submission package

- Project title.
- Short description: active form requires **50–255 characters**.
- Long description: active form requires **600–2,000 characters**; general guidance also asks for
  at least 100 words.
- Categories, event track, and technologies.
- One to five social links.
- Cover image: PNG/JPG, **16:9**.
- Video presentation: **MP4, five minutes or less, under 300 MB** under general guidance.
- Slide presentation: **PDF**.
- Public GitHub repository.
- Deployed demo platform and application URL.
- Alpaca paper account ID.
- One-page AI/risk/infrastructure write-up.

The general LabLab guide recommends an 8–10 slide deck and a video shaped approximately as:
problem (0:00–0:30), working demo (0:30–2:30), business value (2:30–4:00), and team/roadmap
(4:00–5:00).

## Teams, eligibility, and conduct

- Teams contain **one to six** people.
- Every member must register independently and join the team.
- Prize recipients must be 18 or older and satisfy the event's geographic, sanctions, sponsor,
  employee, contractor, family, and household restrictions.
- Participants are responsible for taxes and requested prize documentation.
- Work must be original and compatible with the event's open-source/MIT terms.
- Plagiarism, unethical behavior, gaming, vote manipulation, and disallowed automation may
  disqualify a project.
- A manual late submission is possible only for a valid reason and with prior organizer or mentor
  approval; the general limit is six hours after the event.

The submission guide contains a generic IBM Bob report sentence. It applies only when IBM Bob was
used. AlphaLedger did not use IBM Bob, so it must not create or claim that report.

## Event schedule and community

- Active build and submission phase: **28 August–4 September 2026**.
- Official P&L measurement: **31 August 9:30 a.m. ET–4 September 9:30 a.m. ET**.
- New entry sessions available to regular options trading: Monday–Thursday only.
- Official and community surfaces shown by the event include LabLab Discord, X, LinkedIn,
  Instagram, YouTube, Twitch, and website; Alpaca X, LinkedIn, GitHub, Slack, Forum, and website.

The event page's speakers area is dynamic and has shown duplicated entries. Names and session
roles should be cited only from the final live event view, not used as product claims.

## Sources

- [Event](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon)
- [LabLab guide](https://lablab.ai/guide)
- [Submission guidance](https://lablab.ai/delivering-your-hackathon-solution)
- [Hackathon rules](https://lablab.ai/hackathon-rules)
- [How to win](https://lablab.ai/guide/how-to-win-an-ai-hackathon)
- [Hackathon guidelines](https://lablab.ai/ai-articles/hackathon-guidelines)
- [Alpaca CLI](https://docs.alpaca.markets/us/docs/alpacas-cli)
- [Alpaca Level 3 multi-leg options](https://docs.alpaca.markets/us/docs/options-level-3-trading)
