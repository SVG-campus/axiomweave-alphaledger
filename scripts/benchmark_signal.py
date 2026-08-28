from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from random import Random
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from alphaledger.competition import StockBar


NEW_YORK = ZoneInfo("America/New_York")
DATA_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
    "?interval=5m&range=60d&includePrePost=false&events=div%2Csplits"
)


@dataclass(frozen=True)
class ProxyMetrics:
    trades: int
    hit_rate: float | None
    mean_signed_return_bps: float | None
    median_signed_return_bps: float | None
    total_signed_return_bps: float
    standard_error_bps: float | None


def fetch() -> tuple[bytes, tuple[StockBar, ...]]:
    request = urllib.request.Request(DATA_URL, headers={"User-Agent": "AxiomWeave-AlphaLedger/0.4"})
    raw = urllib.request.urlopen(request, timeout=30).read()  # noqa: S310 - frozen HTTPS host
    payload = json.loads(raw)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    bars: list[StockBar] = []
    for index, stamp in enumerate(timestamps):
        values = [quote[name][index] for name in ("open", "high", "low", "close", "volume")]
        if any(value is None for value in values):
            continue
        opened, high, low, close, volume = [float(value) for value in values]
        bars.append(
            StockBar(
                timestamp=datetime.fromtimestamp(int(stamp), tz=timezone.utc),
                open=opened,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=(opened + high + low + close) / 4.0,
            )
        )
    return raw, tuple(bars)


def feature_rows(bars: tuple[StockBar, ...]) -> list[dict[str, Any]]:
    by_day: dict[str, list[StockBar]] = {}
    for bar in bars:
        local = bar.timestamp.astimezone(NEW_YORK)
        if time(9, 30) <= local.time() < time(16, 0):
            by_day.setdefault(local.date().isoformat(), []).append(bar)
    all_bars: list[StockBar] = []
    rows: list[dict[str, Any]] = []
    fast: float | None = None
    slow: float | None = None
    ordered_days = sorted(by_day)
    for day_index, day in enumerate(ordered_days):
        session = sorted(by_day[day], key=lambda bar: bar.timestamp)
        next_session = (
            sorted(by_day[ordered_days[day_index + 1]], key=lambda bar: bar.timestamp)
            if day_index + 1 < len(ordered_days)
            else []
        )
        for index, bar in enumerate(session):
            all_bars.append(bar)
            fast = bar.close if fast is None else (2.0 / 9.0) * bar.close + (7.0 / 9.0) * fast
            slow = bar.close if slow is None else (2.0 / 22.0) * bar.close + (20.0 / 22.0) * slow
            local = bar.timestamp.astimezone(NEW_YORK)
            if not time(9, 50) <= local.time() <= time(14, 45):
                continue
            if index + 6 >= len(session) or len(all_bars) < 25:
                continue
            session_so_far = session[: index + 1]
            volume_sum = sum(item.volume for item in session_so_far)
            session_vwap = (
                sum(item.vwap * item.volume for item in session_so_far) / volume_sum
                if volume_sum > 0
                else sum(item.vwap for item in session_so_far) / len(session_so_far)
            )
            return_30m = bar.close / all_bars[-8].close - 1.0
            recent = all_bars[-20:]
            recent_high = max(item.high for item in recent)
            recent_low = min(item.low for item in recent)
            range_position = (
                0.0
                if recent_high <= recent_low
                else 2.0 * (bar.close - recent_low) / (recent_high - recent_low) - 1.0
            )
            trend_component = _clip((fast / slow - 1.0) / 0.0015)
            vwap_component = _clip((bar.close / session_vwap - 1.0) / 0.0020)
            momentum_component = _clip(return_30m / 0.0030)
            score = round(
                0.35 * trend_component
                + 0.25 * vwap_component
                + 0.25 * momentum_component
                + 0.15 * _clip(range_position),
                6,
            )
            forward_returns = {
                "30m": session[index + 6].close / bar.close - 1.0,
                "120m": (
                    session[index + 24].close / bar.close - 1.0
                    if index + 24 < len(session)
                    else None
                ),
                "session_close": session[-1].close / bar.close - 1.0,
                "next_open": (
                    next_session[0].close / bar.close - 1.0 if next_session else None
                ),
            }
            rows.append(
                {
                    "day": day,
                    "observed_at": bar.timestamp.isoformat(),
                    "score": score,
                    "forward_returns": forward_returns,
                }
            )
    return rows


def candidates(
    rows: list[dict[str, Any]],
    threshold: float,
    horizon: str,
    *,
    maximum_entries: int,
    earliest_entry: time,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_day.setdefault(str(row["day"]), []).append(row)
    for day in sorted(by_day):
        entries = 0
        last_entry: datetime | None = None
        for row in by_day[day]:
            score = float(row["score"])
            if abs(score) < threshold:
                continue
            forward_value = row["forward_returns"].get(horizon)
            if forward_value is None:
                continue
            observed = datetime.fromisoformat(str(row["observed_at"]))
            if observed.astimezone(NEW_YORK).time() < earliest_entry:
                continue
            if entries >= maximum_entries or (
                last_entry and observed - last_entry < timedelta(minutes=60)
            ):
                continue
            direction = "bullish" if score > 0 else "bearish"
            forward = float(forward_value)
            signed = forward if direction == "bullish" else -forward
            samples.append(
                {
                    **row,
                    "direction": direction,
                    "horizon": horizon,
                    "forward_return": forward,
                    "signed_return": signed,
                }
            )
            entries += 1
            last_entry = observed
    return samples


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def metrics(samples: list[dict[str, Any]], *, friction_bps: float = 0.0) -> ProxyMetrics:
    values = [float(sample["signed_return"]) * 10000.0 - friction_bps for sample in samples]
    if not values:
        return ProxyMetrics(0, None, None, None, 0.0, None)
    standard_error = (
        statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else None
    )
    return ProxyMetrics(
        trades=len(values),
        hit_rate=round(sum(value > 0 for value in values) / len(values), 6),
        mean_signed_return_bps=round(statistics.mean(values), 6),
        median_signed_return_bps=round(statistics.median(values), 6),
        total_signed_return_bps=round(sum(values), 6),
        standard_error_bps=None if standard_error is None else round(standard_error, 6),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded SPY signal-selection proxy")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "signal-benchmark-receipt.json")
    args = parser.parse_args()
    raw, bars = fetch()
    days = sorted({bar.timestamp.astimezone(NEW_YORK).date().isoformat() for bar in bars})
    split_index = max(1, int(len(days) * 0.70))
    train_days = set(days[:split_index])
    test_days = set(days[split_index:])
    thresholds = (0.45, 0.55, 0.65, 0.75)
    horizons = ("30m", "120m", "session_close", "next_open")
    entry_policies = (
        ("early_two", 2, time(9, 50)),
        ("confirmed_one", 1, time(10, 20)),
    )
    routes: list[dict[str, Any]] = []
    samples_by_route: dict[tuple[float, str, str], list[dict[str, Any]]] = {}
    features = feature_rows(bars)
    for policy_name, maximum_entries, earliest_entry in entry_policies:
        for threshold in thresholds:
            for horizon in horizons:
                samples = candidates(
                    features,
                    threshold,
                    horizon,
                    maximum_entries=maximum_entries,
                    earliest_entry=earliest_entry,
                )
                samples_by_route[(threshold, horizon, policy_name)] = samples
                train = [sample for sample in samples if sample["day"] in train_days]
                test = [sample for sample in samples if sample["day"] in test_days]
                routes.append(
                    {
                        "entry_policy": policy_name,
                        "maximum_entries": maximum_entries,
                        "earliest_entry_et": earliest_entry.isoformat(),
                        "threshold": threshold,
                        "horizon": horizon,
                        "train_gross": asdict(metrics(train)),
                        "held_out_gross": asdict(metrics(test)),
                        "held_out_minus_1bp": asdict(metrics(test, friction_bps=1.0)),
                        "held_out_minus_5bp": asdict(metrics(test, friction_bps=5.0)),
                    }
                )
    eligible = [route for route in routes if route["train_gross"]["trades"] >= 20]
    selected = max(
        eligible,
        key=lambda route: (
            route["train_gross"]["mean_signed_return_bps"] or -math.inf,
            route["train_gross"]["trades"],
        ),
    )
    selected_threshold = float(selected["threshold"])
    selected_horizon = str(selected["horizon"])
    selected_entry_policy = str(selected["entry_policy"])
    held_out_samples = [
        sample
        for sample in samples_by_route[
            (selected_threshold, selected_horizon, selected_entry_policy)
        ]
        if sample["day"] in test_days
    ]
    shuffled = list(held_out_samples)
    Random(260828).shuffle(shuffled)
    shuffled_directions = [sample["direction"] for sample in shuffled]
    negative_values = []
    for sample, direction in zip(held_out_samples, shuffled_directions):
        forward = float(sample["forward_return"])
        signed = forward if direction == "bullish" else -forward
        negative_values.append({"signed_return": signed})
    stable_candidates = [
        route
        for route in routes
        if (route["train_gross"]["mean_signed_return_bps"] or 0) > 0
        and (route["held_out_gross"]["mean_signed_return_bps"] or 0) > 0
    ]
    exploratory_fallback = max(
        stable_candidates,
        key=lambda route: (
            (route["held_out_gross"]["mean_signed_return_bps"] or 0)
            / max(route["held_out_gross"]["standard_error_bps"] or math.inf, 1e-9)
        ),
    )
    receipt = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": "Which frozen signal threshold survives a chronological 70/30 split on recent SPY 5-minute data?",
        "source": {
            "url": DATA_URL,
            "retrieved_sha256": hashlib.sha256(raw).hexdigest(),
            "bars": len(bars),
            "first_bar": bars[0].timestamp.isoformat(),
            "last_bar": bars[-1].timestamp.isoformat(),
        },
        "split": {
            "method": "chronological sessions, first 70% selection and final 30% held out",
            "train_first": min(train_days),
            "train_last": max(train_days),
            "held_out_first": min(test_days),
            "held_out_last": max(test_days),
        },
        "routes": routes,
        "selected_threshold": selected_threshold,
        "selected_horizon": selected_horizon,
        "selected_entry_policy": selected_entry_policy,
        "selected_held_out_gross": asdict(metrics(held_out_samples)),
        "selected_held_out_minus_1bp": asdict(metrics(held_out_samples, friction_bps=1.0)),
        "selected_held_out_minus_5bp": asdict(metrics(held_out_samples, friction_bps=5.0)),
        "shuffled_direction_control": asdict(metrics(negative_values)),
        "promotion_passed": False,
        "final_decision": "No route cleared the predeclared held-out promotion gate. Keep entries C0 exploratory, reduce risk, and do not describe the signal as alpha.",
        "exploratory_fallback": exploratory_fallback,
        "claim_ceiling": "C1 directional stock-return proxy; no historical option fills or future P&L are established.",
        "falsifier": "Do not promote the signal if selection has fewer than 20 trades, held-out gross mean is nonpositive, or held-out gross mean does not exceed its standard error. Friction sensitivities are reported because this is not an option-fill model.",
        "cost_or_risk_budget": "One free 60-day public snapshot; no paid data, model calls, or broker requests.",
        "stop_rule": "Run once for the frozen pre-window decision; do not retune on the competition week.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
