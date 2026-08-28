from __future__ import annotations

import hashlib
import json
import math

from .models import AccountState, MarketSnapshot, TradeThesis, utc_now_iso


class BoundedMomentumProposer:
    """A transparent baseline proposer; it can propose, never authorize."""

    def __init__(self, minimum_edge: float = 0.0025, target_notional: float = 25.0) -> None:
        self.minimum_edge = minimum_edge
        self.target_notional = target_notional

    def propose(self, snapshot: MarketSnapshot, account: AccountState) -> TradeThesis:
        edge = (snapshot.short_ma / snapshot.long_ma) - 1.0
        held_quantity = account.positions.get(snapshot.symbol, 0.0)

        if edge >= self.minimum_edge:
            side = "buy"
            quantity = math.floor((self.target_notional / snapshot.last_price) * 1_000_000) / 1_000_000
            rationale = (
                f"Short moving average exceeds the long moving average by {edge:.3%}; "
                "candidate is bounded to the fixed new-notional budget."
            )
        elif edge <= -self.minimum_edge and held_quantity > 0:
            side = "sell"
            quantity = round(held_quantity, 6)
            rationale = (
                f"Short moving average trails the long moving average by {abs(edge):.3%}; "
                "candidate exits the existing long position without opening a short."
            )
        else:
            side = "hold"
            quantity = 0.0
            rationale = f"Observed edge {edge:.3%} does not clear the frozen {self.minimum_edge:.3%} threshold."

        stable = json.dumps(
            {"snapshot": snapshot.to_dict(), "side": side, "quantity": quantity},
            sort_keys=True,
            separators=(",", ":"),
        )
        thesis_id = "thesis-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:12]
        return TradeThesis(
            thesis_id=thesis_id,
            created_at=utc_now_iso(),
            symbol=snapshot.symbol,
            side=side,
            quantity=quantity,
            rationale=rationale,
            evidence_refs=snapshot.source_refs,
            invalidation_condition=(
                "Abstain or exit if the moving-average edge reverses, evidence becomes stale, "
                "or any deterministic risk gate fails."
            ),
            expected_horizon="one to five market sessions",
        )
