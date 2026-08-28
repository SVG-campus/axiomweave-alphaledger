from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .alpaca_readonly import PaperReadinessReceipt, ReadOnlyResponse


NEW_YORK = ZoneInfo("America/New_York")


class CompetitionPhase(str, Enum):
    PRE_WINDOW = "pre_window"
    ENTRY_ALLOWED = "entry_allowed"
    EXIT_ONLY = "exit_only"
    CLOSED_SESSION = "closed_session"
    FORCE_FLAT = "force_flat"
    COMPLETE = "complete"


@dataclass(frozen=True)
class CompetitionWindow:
    start_utc: datetime = datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc)
    end_utc: datetime = datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc)
    force_flat_utc: datetime = datetime(2026, 9, 3, 19, 45, tzinfo=timezone.utc)
    eligible_sessions: tuple[date, ...] = (
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    )
    market_open: time = time(9, 30)
    first_entry: time = time(10, 20)
    last_entry: time = time(14, 30)
    market_close: time = time(16, 0)
    blackout_windows: tuple[tuple[datetime, datetime, str], ...] = (
        (
            datetime(2026, 9, 1, 9, 50, tzinfo=NEW_YORK),
            datetime(2026, 9, 1, 10, 20, tzinfo=NEW_YORK),
            "JOLTS release window",
        ),
        (
            datetime(2026, 9, 2, 9, 50, tzinfo=NEW_YORK),
            datetime(2026, 9, 2, 10, 20, tzinfo=NEW_YORK),
            "metro employment release window",
        ),
    )

    def phase_at(self, instant: datetime) -> CompetitionPhase:
        now = _aware_utc(instant)
        if now < self.start_utc:
            return CompetitionPhase.PRE_WINDOW
        if now >= self.end_utc:
            return CompetitionPhase.COMPLETE
        if now >= self.force_flat_utc:
            return CompetitionPhase.FORCE_FLAT
        local = now.astimezone(NEW_YORK)
        if local.date() not in self.eligible_sessions:
            return CompetitionPhase.CLOSED_SESSION
        if local.time() < self.market_open or local.time() >= self.market_close:
            return CompetitionPhase.CLOSED_SESSION
        if self.blackout_reason(now) is not None:
            return CompetitionPhase.EXIT_ONLY
        if self.first_entry <= local.time() <= self.last_entry:
            return CompetitionPhase.ENTRY_ALLOWED
        return CompetitionPhase.EXIT_ONLY

    def blackout_reason(self, instant: datetime) -> str | None:
        now = _aware_utc(instant)
        for start, end, reason in self.blackout_windows:
            if start.astimezone(timezone.utc) <= now < end.astimezone(timezone.utc):
                return reason
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_utc": self.start_utc.isoformat(),
            "end_utc": self.end_utc.isoformat(),
            "force_flat_utc": self.force_flat_utc.isoformat(),
            "eligible_sessions": [value.isoformat() for value in self.eligible_sessions],
            "market_timezone": str(NEW_YORK),
            "first_entry": self.first_entry.isoformat(),
            "last_entry": self.last_entry.isoformat(),
        }


@dataclass(frozen=True)
class CompetitionRiskPolicy:
    baseline_equity_usd: float = 100000.0
    baseline_tolerance_usd: float = 0.01
    max_loss_per_plan_usd: float = 250.0
    max_open_plans: int = 1
    max_aggregate_open_loss_usd: float = 250.0
    max_daily_drawdown_usd: float = 500.0
    max_total_drawdown_usd: float = 1000.0
    max_entries_per_session: int = 1
    max_contracts_per_plan: int = 5
    signal_threshold: float = 0.45
    take_profit_fraction: float = 0.25
    stop_loss_fraction: float = 0.20
    max_hold_hours: float = 0.75
    allowed_underlyings: tuple[str, ...] = ("SPY",)
    max_bar_age_seconds: int = 420

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateDecision:
    approved: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_clean_competition_account(
    receipt: PaperReadinessReceipt,
    policy: CompetitionRiskPolicy | None = None,
) -> GateDecision:
    frozen = policy or CompetitionRiskPolicy()
    reasons: list[str] = []
    if not receipt.ready_for_defined_risk_observation:
        reasons.append("Base paper-readiness reconciliation did not pass.")
    if abs(receipt.equity - frozen.baseline_equity_usd) > frozen.baseline_tolerance_usd:
        reasons.append("Account equity is not the required fresh $100,000 baseline.")
    if abs(receipt.cash - frozen.baseline_equity_usd) > frozen.baseline_tolerance_usd:
        reasons.append("Account cash is not the required fresh $100,000 baseline.")
    if receipt.positions_count != 0:
        reasons.append("Competition account has a pre-existing position.")
    if receipt.open_orders_count != 0:
        reasons.append("Competition account has a pre-existing open order.")
    if receipt.trading_blocked:
        reasons.append("Competition account is blocked from trading.")
    if receipt.options_approved_level < 3 or receipt.options_trading_level < 3:
        reasons.append("Competition account does not have options level 3.")
    return GateDecision(
        approved=len(reasons) == 0,
        reasons=tuple(reasons) if reasons else ("Fresh competition account gate passed.",),
    )


@dataclass(frozen=True)
class StockBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass(frozen=True)
class MomentumSignal:
    direction: str
    score: float
    fast_ema: float
    slow_ema: float
    session_vwap: float
    return_30m: float
    range_position: float
    observed_at: str
    evidence_refs: tuple[str, ...]
    falsifier: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_stock_bars(response: ReadOnlyResponse, symbol: str) -> tuple[StockBar, ...]:
    payload = response.payload
    if not isinstance(payload, dict):
        raise RuntimeError("Alpaca stock-bars response must be a JSON object")
    next_token = payload.get("next_page_token")
    if next_token not in {None, ""}:
        raise RuntimeError("Stock-bar pagination is incomplete; fail closed")
    bars_by_symbol = payload.get("bars")
    if not isinstance(bars_by_symbol, dict):
        raise RuntimeError("Alpaca stock-bars response is missing its bars object")
    rows = bars_by_symbol.get(symbol.upper())
    if not isinstance(rows, list):
        raise RuntimeError("Alpaca stock-bars response is missing the requested symbol")
    result: list[StockBar] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Alpaca stock bar must be a JSON object")
        try:
            stamp = datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
            values = [float(row[key]) for key in ("o", "h", "l", "c", "v")]
            raw_vwap = row.get("vw", row["c"])
            vwap = float(raw_vwap)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Alpaca stock bar is malformed") from exc
        if stamp.tzinfo is None:
            raise RuntimeError("Alpaca stock bar timestamp must be timezone-aware")
        if not all(math.isfinite(value) for value in (*values, vwap)):
            raise RuntimeError("Alpaca stock bar contains a non-finite value")
        result.append(StockBar(stamp.astimezone(timezone.utc), *values, vwap))
    return tuple(result)


def compute_momentum_signal(
    bars: Iterable[StockBar],
    *,
    as_of: datetime,
    policy: CompetitionRiskPolicy | None = None,
    source_refs: tuple[str, ...] = (),
) -> MomentumSignal:
    frozen = policy or CompetitionRiskPolicy()
    values = tuple(bars)
    if len(values) < 25:
        raise ValueError("At least 25 ordered bars are required")
    stamps = [bar.timestamp for bar in values]
    if any(stamp.tzinfo is None for stamp in stamps):
        raise ValueError("Every bar timestamp must be timezone-aware")
    if any(a >= b for a, b in zip(stamps, stamps[1:])):
        raise ValueError("Bars must be strictly increasing and unique")
    now = _aware_utc(as_of)
    if stamps[-1] > now:
        raise ValueError("The newest bar is from the future")
    age_seconds = (now - stamps[-1]).total_seconds()
    if age_seconds > frozen.max_bar_age_seconds:
        raise ValueError("The newest bar is stale")
    for bar in values:
        if (
            min(bar.open, bar.high, bar.low, bar.close, bar.vwap) <= 0
            or bar.volume < 0
            or not all(
                math.isfinite(value)
                for value in (bar.open, bar.high, bar.low, bar.close, bar.volume, bar.vwap)
            )
        ):
            raise ValueError("A bar contains invalid market values")
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise ValueError("A bar violates OHLC ordering")

    closes = [bar.close for bar in values]
    fast = _ema(closes, 8)
    slow = _ema(closes, 21)
    current_session = stamps[-1].astimezone(NEW_YORK).date()
    session_bars = [bar for bar in values if bar.timestamp.astimezone(NEW_YORK).date() == current_session]
    if len(session_bars) < 4:
        raise ValueError("At least four current-session bars are required")
    volume_sum = sum(bar.volume for bar in session_bars)
    session_vwap = (
        sum(bar.vwap * bar.volume for bar in session_bars) / volume_sum
        if volume_sum > 0
        else sum(bar.vwap for bar in session_bars) / len(session_bars)
    )
    lookback = min(7, len(closes) - 1)
    return_30m = closes[-1] / closes[-1 - lookback] - 1.0
    recent = values[-20:]
    recent_high = max(bar.high for bar in recent)
    recent_low = min(bar.low for bar in recent)
    range_position = (
        0.0
        if recent_high <= recent_low
        else 2.0 * (closes[-1] - recent_low) / (recent_high - recent_low) - 1.0
    )
    trend_component = _clip((fast / slow - 1.0) / 0.0015)
    vwap_component = _clip((closes[-1] / session_vwap - 1.0) / 0.0020)
    momentum_component = _clip(return_30m / 0.0030)
    range_component = _clip(range_position)
    score = round(
        0.35 * trend_component
        + 0.25 * vwap_component
        + 0.25 * momentum_component
        + 0.15 * range_component,
        6,
    )
    if score >= frozen.signal_threshold:
        direction = "bullish"
    elif score <= -frozen.signal_threshold:
        direction = "bearish"
    else:
        direction = "neutral"
    return MomentumSignal(
        direction=direction,
        score=score,
        fast_ema=round(fast, 6),
        slow_ema=round(slow, 6),
        session_vwap=round(session_vwap, 6),
        return_30m=round(return_30m, 8),
        range_position=round(range_position, 6),
        observed_at=stamps[-1].isoformat(),
        evidence_refs=tuple(dict.fromkeys(source_refs)),
        falsifier=(
            "No entry if the composite magnitude falls below threshold, inputs are stale or malformed, "
            "or the competition/account/risk gate is not independently satisfied."
        ),
    )


def evaluate_entry_gate(
    *,
    instant: datetime,
    window: CompetitionWindow,
    policy: CompetitionRiskPolicy,
    signal: MomentumSignal,
    current_equity: float,
    daily_pnl: float,
    open_plans: int,
    aggregate_open_max_loss: float,
    entries_this_session: int,
) -> GateDecision:
    reasons: list[str] = []
    phase = window.phase_at(instant)
    if phase is not CompetitionPhase.ENTRY_ALLOWED:
        reasons.append(f"Competition clock is {phase.value}, not entry_allowed.")
    if signal.direction not in {"bullish", "bearish"}:
        reasons.append("Signal selected the cash/neutral baseline.")
    if abs(signal.score) < policy.signal_threshold:
        reasons.append("Signal magnitude is below the frozen entry threshold.")
    if not math.isfinite(current_equity) or current_equity <= 0:
        reasons.append("Current account equity is invalid.")
    if daily_pnl <= -policy.max_daily_drawdown_usd:
        reasons.append("Daily drawdown stop is active.")
    if current_equity <= policy.baseline_equity_usd - policy.max_total_drawdown_usd:
        reasons.append("Total drawdown stop is active.")
    if open_plans >= policy.max_open_plans:
        reasons.append("Maximum concurrent plans are already open.")
    if aggregate_open_max_loss + policy.max_loss_per_plan_usd > policy.max_aggregate_open_loss_usd:
        reasons.append("A new plan would breach aggregate maximum loss.")
    if entries_this_session >= policy.max_entries_per_session:
        reasons.append("Session entry count is exhausted.")
    return GateDecision(
        approved=len(reasons) == 0,
        reasons=tuple(reasons) if reasons else ("All competition entry gates passed.",),
    )


@dataclass(frozen=True)
class ExitDecision:
    should_close: bool
    reason: str
    return_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_exit(
    *,
    entry_debit_per_share: float,
    current_close_credit_per_share: float,
    opened_at: datetime,
    instant: datetime,
    window: CompetitionWindow,
    policy: CompetitionRiskPolicy,
) -> ExitDecision:
    if entry_debit_per_share <= 0 or not math.isfinite(entry_debit_per_share):
        raise ValueError("Entry debit must be finite and positive")
    if current_close_credit_per_share < 0 or not math.isfinite(current_close_credit_per_share):
        raise ValueError("Close credit must be finite and non-negative")
    now = _aware_utc(instant)
    opened = _aware_utc(opened_at)
    if opened > now:
        raise ValueError("Opened timestamp cannot be in the future")
    return_fraction = current_close_credit_per_share / entry_debit_per_share - 1.0
    phase = window.phase_at(now)
    if phase in {CompetitionPhase.FORCE_FLAT, CompetitionPhase.COMPLETE}:
        reason = "competition_force_flat"
        should_close = True
    elif return_fraction >= policy.take_profit_fraction:
        reason = "take_profit"
        should_close = True
    elif return_fraction <= -policy.stop_loss_fraction:
        reason = "stop_loss"
        should_close = True
    elif now - opened >= timedelta(hours=policy.max_hold_hours):
        reason = "maximum_holding_time"
        should_close = True
    else:
        reason = "hold"
        should_close = False
    return ExitDecision(should_close, reason, round(return_fraction, 6))


def natural_close_credit(contracts: dict[str, Any], long_symbol: str, short_symbol: str) -> float:
    """Compute a conservative close credit: sell long at bid, buy short at ask."""

    try:
        long_quote = contracts[long_symbol]
        short_quote = contracts[short_symbol]
        credit = float(long_quote["bid_price"]) - float(short_quote["ask_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Close quotes are incomplete") from exc
    if not math.isfinite(credit):
        raise ValueError("Close credit is non-finite")
    return round(max(0.0, credit), 4)


def _ema(values: list[float], span: int) -> float:
    alpha = 2.0 / (span + 1.0)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
    return current


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)
