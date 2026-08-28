from __future__ import annotations

import math
from datetime import datetime, timezone

from .models import AccountState, MarketSnapshot


def demo_prices(length: int = 90) -> list[float]:
    """Fixed synthetic path with no network, credentials, or hidden randomness."""
    prices: list[float] = []
    for index in range(length):
        trend = 0.055 * index
        cycle = 1.25 * math.sin(index / 5.0) + 0.45 * math.sin(index / 2.3)
        drawdown = -4.5 if 45 <= index <= 54 else 0.0
        late_acceleration = 0.14 * max(0, index - 65)
        prices.append(round(100.0 + trend + cycle + drawdown + late_acceleration, 4))
    return prices


def moving_average(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Need at least {window} values")
    return sum(values[-window:]) / window


def realized_volatility(values: list[float], window: int = 20) -> float:
    recent = values[-(window + 1) :]
    returns = [(recent[i] / recent[i - 1]) - 1.0 for i in range(1, len(recent))]
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((item - mean) ** 2 for item in returns) / len(returns)
    return math.sqrt(variance)


def build_snapshot(prices: list[float] | None = None, *, stale: bool = False) -> MarketSnapshot:
    values = prices or demo_prices()
    return MarketSnapshot(
        symbol="SPY",
        observed_at=datetime.now(timezone.utc).isoformat(),
        last_price=values[-1],
        short_ma=round(moving_average(values, 5), 6),
        long_ma=round(moving_average(values, 20), 6),
        realized_volatility=round(realized_volatility(values), 8),
        data_age_seconds=900 if stale else 12,
        source_refs=(
            "demo://synthetic-bars/frozen-seedless-path-v1",
            "policy://bounded-momentum-v1",
        ),
    )


def build_account(*, daily_pnl: float = 0.0, open_orders: int = 0) -> AccountState:
    return AccountState(
        equity=500.0,
        cash=500.0,
        buying_power=500.0,
        daily_pnl=daily_pnl,
        positions={},
        open_orders=open_orders,
        broker_mode="simulation",
    )
