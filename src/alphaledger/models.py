from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Side = Literal["buy", "sell", "hold"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    observed_at: str
    last_price: float
    short_ma: float
    long_ma: float
    realized_volatility: float
    data_age_seconds: int
    source_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountState:
    equity: float
    cash: float
    buying_power: float
    daily_pnl: float
    positions: dict[str, float] = field(default_factory=dict)
    open_orders: int = 0
    broker_mode: str = "simulation"

    def gross_exposure(self, prices: dict[str, float]) -> float:
        return sum(abs(quantity * prices.get(symbol, 0.0)) for symbol, quantity in self.positions.items())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeThesis:
    thesis_id: str
    created_at: str
    symbol: str
    side: Side
    quantity: float
    rationale: str
    evidence_refs: tuple[str, ...]
    invalidation_condition: str
    expected_horizon: str
    confidence_label: Literal["low", "bounded", "high"] = "bounded"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CriticVerdict:
    passed: bool
    reasons: tuple[str, ...]
    negative_control: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskPolicy:
    paper_only: bool = True
    allowed_symbols: tuple[str, ...] = ("SPY",)
    max_new_notional: float = 25.0
    max_gross_exposure: float = 50.0
    max_daily_loss_pct: float = 0.015
    max_data_age_seconds: int = 180
    max_realized_volatility: float = 0.045
    min_evidence_refs: int = 2
    max_open_orders: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    projected_new_notional: float
    projected_gross_exposure: float
    daily_loss_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionReceipt:
    receipt_id: str
    created_at: str
    status: Literal["abstained", "simulated", "paper_submitted", "rejected"]
    thesis_id: str
    symbol: str
    side: Side
    quantity: float
    fill_price: float | None
    broker_mode: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedCycleResult:
    snapshot: MarketSnapshot
    thesis: TradeThesis
    critic: CriticVerdict
    risk: RiskDecision
    receipt: ExecutionReceipt
    ledger_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "thesis": self.thesis.to_dict(),
            "critic": self.critic.to_dict(),
            "risk": self.risk.to_dict(),
            "receipt": self.receipt.to_dict(),
            "ledger_hash": self.ledger_hash,
        }
