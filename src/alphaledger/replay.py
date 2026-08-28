from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReplayMetric:
    name: str
    total_return: float
    max_drawdown: float
    turnover_events: int

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        worst = min(worst, (value / peak) - 1.0)
    return worst


def _metric(name: str, equity: list[float], turnover_events: int) -> ReplayMetric:
    return ReplayMetric(
        name=name,
        total_return=(equity[-1] / equity[0]) - 1.0,
        max_drawdown=_max_drawdown(equity),
        turnover_events=turnover_events,
    )


def replay_controls(prices: list[float], *, seed: int = 20260824) -> list[ReplayMetric]:
    if len(prices) < 25 or any(price <= 0 or not math.isfinite(price) for price in prices):
        raise ValueError("Replay requires at least 25 finite positive prices")

    returns = [1.0] + [prices[i] / prices[i - 1] for i in range(1, len(prices))]
    hold_equity = [100.0]
    for gross_return in returns[1:]:
        hold_equity.append(hold_equity[-1] * gross_return)

    cash_equity = [100.0] * len(prices)

    momentum_equity = [100.0]
    invested = False
    turnover = 0
    for index in range(1, len(prices)):
        if index >= 20:
            short_ma = sum(prices[index - 4 : index + 1]) / 5
            long_ma = sum(prices[index - 19 : index + 1]) / 20
            next_invested = ((short_ma / long_ma) - 1.0) >= 0.0025
        else:
            next_invested = False
        if next_invested != invested:
            turnover += 1
        invested = next_invested
        momentum_equity.append(momentum_equity[-1] * (returns[index] if invested else 1.0))

    shuffled = returns[1:].copy()
    random.Random(seed).shuffle(shuffled)
    shuffled_equity = [100.0]
    for gross_return in shuffled:
        shuffled_equity.append(shuffled_equity[-1] * gross_return)

    return [
        _metric("governed momentum replay", momentum_equity, turnover),
        _metric("buy-and-hold baseline", hold_equity, 1),
        _metric("cash/abstain control", cash_equity, 0),
        _metric("shuffled-return negative control", shuffled_equity, 0),
    ]
