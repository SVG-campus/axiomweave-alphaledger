# Resource synchronization after every material change

Keep one verified state across code, public demo, evidence, slides, narration, and submission drafts.
The source of truth for measured account results is `evidence/public-operation-status.json` with an
explicit observation timestamp. It is a published snapshot, not a continuously connected account.

1. Preserve the failure and before-state evidence. Record first occurrence, detection, diagnosis,
   repair, restart, verified recovery, impact, and uncertainty; never rewrite historical receipts.
2. Verify the repair, exact deployed source, account identity, one writer, and journal continuity.
3. Update the redacted public status JSON and incident receipt. No API secrets, account identifiers,
   order identifiers, raw private state, or private screenshots may enter the public package.
4. Update affected README/runbook/write-up, form copy, narration, and social drafts. Link the same
   incident and snapshot rather than duplicating unqualified live-performance claims.
5. Update the current PPTX and PDF, speaker-note sources, and `submission/PRESENTATION_STATUS.md`.
   Preserve earlier deck revisions as historical artifacts. Recheck every slide and test count.
6. Run `python scripts/verify.py`. Review the diff and public-safe release manifest, publish the
   reviewed commit, and refresh the named demo. Do not restart the trader for documentation-only edits.
7. Check public URLs and screenshot the updated public view. Distinguish local updates from actual
   publication; mark anything that failed to publish as pending.
8. An uploaded video or submitted form is not changed by editing a script. Flag re-recording or
   re-uploading when its claims are stale. Do not post social messages, upload video, or click final
   submission without the owner's action-time approval.

## What is not changed by ordinary maintenance

The frozen strategy, account, $250 plan-loss cap, one-attempt-per-day limit, drawdown stops, and
competition clock are not adjusted to fit observed contest outcomes. A strategy amendment needs
a separately documented comparison, downside tradeoff, and owner decision. No benchmark currently
supports calling this a proven best strategy, maximizing profit, or increasing the risk budget.

## Thursday final packet

Reconcile the organizer-scored Thursday EOD equity; preserve the exact timestamp and source.
Update P&L, attempts, fills/exits, refusal/error counts, unresolved exposure, and incident timeline.
Refresh slide/script results only after reconciliation. Do not substitute a mid-day snapshot for
the final scoring observation. Retain the no-trade baseline if no candidate passed.
