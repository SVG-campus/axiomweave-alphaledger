from __future__ import annotations

from .models import CriticVerdict, MarketSnapshot, TradeThesis


class SkepticalCritic:
    """Independent mechanical critic with explicit negative-control checks."""

    def review(self, thesis: TradeThesis, snapshot: MarketSnapshot) -> CriticVerdict:
        reasons: list[str] = []
        if thesis.side == "hold":
            reasons.append("Proposer selected the abstention baseline.")
        if not thesis.invalidation_condition.strip():
            reasons.append("No observable invalidation condition was supplied.")
        if snapshot.short_ma <= 0 or snapshot.long_ma <= 0:
            reasons.append("Moving-average evidence is malformed.")
        if snapshot.realized_volatility > 0.045:
            reasons.append("Volatility exceeds the frozen critic threshold.")
        if len(set(thesis.evidence_refs)) != len(thesis.evidence_refs):
            reasons.append("Evidence manifest contains duplicate references.")

        passed = len(reasons) == 0
        return CriticVerdict(
            passed=passed,
            reasons=tuple(reasons) if reasons else ("Candidate survived the frozen skeptical checks.",),
            negative_control="cash/hold baseline; shuffled-return replay is evaluated separately",
        )
