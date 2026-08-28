from __future__ import annotations

from .models import AccountState, CriticVerdict, MarketSnapshot, RiskDecision, RiskPolicy, TradeThesis


class DeterministicRiskGate:
    """Fail-closed policy. No model or agent can override these checks."""

    def evaluate(
        self,
        thesis: TradeThesis,
        snapshot: MarketSnapshot,
        account: AccountState,
        policy: RiskPolicy,
        critic: CriticVerdict,
    ) -> RiskDecision:
        reasons: list[str] = []
        new_notional = abs(thesis.quantity * snapshot.last_price) if thesis.side == "buy" else 0.0
        current_gross = account.gross_exposure({snapshot.symbol: snapshot.last_price})
        projected_gross = current_gross + new_notional
        daily_loss_pct = max(0.0, -account.daily_pnl / account.equity) if account.equity > 0 else 1.0

        if not policy.paper_only:
            reasons.append("Policy is not locked to paper-only mode.")
        if account.broker_mode not in {"simulation", "paper"}:
            reasons.append("Broker mode is neither simulation nor paper.")
        if thesis.symbol not in policy.allowed_symbols:
            reasons.append("Symbol is outside the frozen allowlist.")
        if thesis.side == "hold":
            reasons.append("Abstention candidate intentionally produces no order.")
        if thesis.side not in {"buy", "sell", "hold"}:
            reasons.append("Unsupported order side.")
        if thesis.side in {"buy", "sell"} and thesis.quantity <= 0:
            reasons.append("Order quantity must be positive.")
        if new_notional > policy.max_new_notional + 1e-6:
            reasons.append("New notional exceeds the per-order budget.")
        if projected_gross > policy.max_gross_exposure + 1e-6:
            reasons.append("Projected gross exposure exceeds the aggregate budget.")
        if new_notional > account.buying_power + 1e-6:
            reasons.append("Candidate exceeds available buying power.")
        if daily_loss_pct >= policy.max_daily_loss_pct:
            reasons.append("Daily-loss stop is active.")
        if snapshot.data_age_seconds > policy.max_data_age_seconds:
            reasons.append("Market evidence is stale.")
        if snapshot.realized_volatility > policy.max_realized_volatility:
            reasons.append("Realized volatility exceeds the policy ceiling.")
        if len(thesis.evidence_refs) < policy.min_evidence_refs:
            reasons.append("Evidence manifest is incomplete.")
        if not thesis.invalidation_condition.strip():
            reasons.append("Thesis lacks an observable invalidation condition.")
        if account.open_orders > policy.max_open_orders:
            reasons.append("Unreconciled open orders block new execution.")
        if not critic.passed:
            reasons.append("Independent critic rejected the candidate.")

        return RiskDecision(
            approved=len(reasons) == 0,
            reasons=tuple(reasons) if reasons else ("All deterministic risk gates passed.",),
            projected_new_notional=round(new_notional, 6),
            projected_gross_exposure=round(projected_gross, 6),
            daily_loss_pct=round(daily_loss_pct, 8),
        )
