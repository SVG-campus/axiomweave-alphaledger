from __future__ import annotations

import hashlib
import json
import math
import statistics
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
NEW_YORK = ZoneInfo("America/New_York")
DATA_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
    "?interval=60m&range=2y&includePrePost=false&events=div%2Csplits"
)


@dataclass(frozen=True)
class Metrics:
    trades: int
    hit_rate: float | None
    mean_bps: float | None
    median_bps: float | None
    standard_error_bps: float | None


def _metrics(values: list[float], friction_bps: float = 0.0) -> Metrics:
    adjusted = [value * 10000.0 - friction_bps for value in values]
    if not adjusted:
        return Metrics(0, None, None, None, None)
    error = statistics.stdev(adjusted) / math.sqrt(len(adjusted)) if len(adjusted) > 1 else None
    return Metrics(
        trades=len(adjusted),
        hit_rate=round(sum(value > 0 for value in adjusted) / len(adjusted), 6),
        mean_bps=round(statistics.mean(adjusted), 6),
        median_bps=round(statistics.median(adjusted), 6),
        standard_error_bps=None if error is None else round(error, 6),
    )


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def fetch() -> tuple[bytes, list[dict[str, Any]]]:
    request = urllib.request.Request(DATA_URL, headers={"User-Agent": "AxiomWeave-AlphaLedger/0.4"})
    raw = urllib.request.urlopen(request, timeout=30).read()  # noqa: S310 - frozen HTTPS host
    result = json.loads(raw)["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    rows: list[dict[str, Any]] = []
    for index, stamp in enumerate(result["timestamp"]):
        values = [quote[name][index] for name in ("open", "high", "low", "close", "volume")]
        if any(value is None for value in values):
            continue
        opened, high, low, close, volume = [float(value) for value in values]
        observed = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        local = observed.astimezone(NEW_YORK)
        if time(9, 30) <= local.time() < time(16, 0):
            rows.append(
                {
                    "observed": observed,
                    "day": local.date().isoformat(),
                    "open": opened,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "vwap_proxy": (opened + high + low + close) / 4.0,
                }
            )
    return raw, rows


def build_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_day.setdefault(row["day"], []).append(row)
    days = sorted(by_day)
    history: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    fast: float | None = None
    slow: float | None = None
    for day_index, day in enumerate(days):
        session = sorted(by_day[day], key=lambda item: item["observed"])
        next_session = (
            sorted(by_day[days[day_index + 1]], key=lambda item: item["observed"])
            if day_index + 1 < len(days)
            else []
        )
        for index, row in enumerate(session):
            history.append(row)
            close = row["close"]
            fast = close if fast is None else (2.0 / 9.0) * close + (7.0 / 9.0) * fast
            slow = close if slow is None else (2.0 / 22.0) * close + (20.0 / 22.0) * slow
            local_time = row["observed"].astimezone(NEW_YORK).time()
            if local_time < time(10, 30) or len(history) < 25:
                continue
            session_so_far = session[: index + 1]
            volume_sum = sum(item["volume"] for item in session_so_far)
            vwap = sum(item["vwap_proxy"] * item["volume"] for item in session_so_far) / volume_sum
            recent = history[-20:]
            high = max(item["high"] for item in recent)
            low = min(item["low"] for item in recent)
            range_position = 0.0 if high <= low else 2 * (close - low) / (high - low) - 1
            return_7h = close / history[-8]["close"] - 1.0
            score = round(
                0.35 * _clip((fast / slow - 1.0) / 0.0030)
                + 0.25 * _clip((close / vwap - 1.0) / 0.0030)
                + 0.25 * _clip(return_7h / 0.0080)
                + 0.15 * _clip(range_position),
                6,
            )
            forwards = {
                "one_hour": (
                    session[index + 1]["close"] / close - 1.0
                    if index + 1 < len(session)
                    else None
                ),
                "session_close": session[-1]["close"] / close - 1.0,
                "next_open": next_session[0]["close"] / close - 1.0 if next_session else None,
            }
            features.append({**row, "score": score, "forwards": forwards})
    return features


def route_values(
    features: list[dict[str, Any]],
    *,
    family: str,
    threshold: float,
    horizon: str,
) -> list[dict[str, Any]]:
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in features:
        by_day.setdefault(row["day"], []).append(row)
    samples: list[dict[str, Any]] = []
    for day in sorted(by_day):
        for row in by_day[day]:
            score = float(row["score"])
            forward = row["forwards"].get(horizon)
            if abs(score) < threshold or forward is None:
                continue
            direction = 1.0 if score > 0 else -1.0
            if family == "mean_reversion":
                direction *= -1.0
            samples.append(
                {
                    "day": day,
                    "observed_at": row["observed"].isoformat(),
                    "signed_return": direction * float(forward),
                }
            )
            break
    return samples


def main() -> int:
    raw, rows = fetch()
    features = build_features(rows)
    days = sorted({row["day"] for row in features})
    train_end = int(len(days) * 0.60)
    validation_end = int(len(days) * 0.80)
    train_days = set(days[:train_end])
    validation_days = set(days[train_end:validation_end])
    test_days = set(days[validation_end:])
    routes: list[dict[str, Any]] = []
    samples_by_key: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for family in ("momentum", "mean_reversion"):
        for threshold in (0.45, 0.60, 0.75):
            for horizon in ("one_hour", "session_close", "next_open"):
                samples = route_values(
                    features,
                    family=family,
                    threshold=threshold,
                    horizon=horizon,
                )
                samples_by_key[(family, threshold, horizon)] = samples
                train = [sample["signed_return"] for sample in samples if sample["day"] in train_days]
                validation = [
                    sample["signed_return"] for sample in samples if sample["day"] in validation_days
                ]
                routes.append(
                    {
                        "family": family,
                        "threshold": threshold,
                        "horizon": horizon,
                        "train_gross": asdict(_metrics(train)),
                        "validation_gross": asdict(_metrics(validation)),
                    }
                )
    promoted = [
        route
        for route in routes
        if route["train_gross"]["trades"] >= 100
        and (route["train_gross"]["mean_bps"] or 0) > 0
        and (route["validation_gross"]["mean_bps"] or 0) > 0
        and (route["validation_gross"]["mean_bps"] or 0)
        > (route["validation_gross"]["standard_error_bps"] or math.inf)
    ]
    selected = (
        max(promoted, key=lambda route: route["validation_gross"]["mean_bps"])
        if promoted
        else None
    )
    test_metrics = None
    test_minus_1bp = None
    test_minus_5bp = None
    if selected:
        key = (selected["family"], float(selected["threshold"]), selected["horizon"])
        test = [
            sample["signed_return"] for sample in samples_by_key[key] if sample["day"] in test_days
        ]
        test_metrics = asdict(_metrics(test))
        test_minus_1bp = asdict(_metrics(test, 1.0))
        test_minus_5bp = asdict(_metrics(test, 5.0))
    test_passed = bool(
        test_metrics
        and (test_metrics["mean_bps"] or 0) > 0
        and (test_metrics["mean_bps"] or 0) > (test_metrics["standard_error_bps"] or math.inf)
    )
    receipt = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": "Does a predeclared hourly SPY momentum or mean-reversion route survive train, validation, and untouched test periods?",
        "source": {
            "url": DATA_URL,
            "retrieved_sha256": hashlib.sha256(raw).hexdigest(),
            "bars": len(rows),
            "first": rows[0]["observed"].isoformat(),
            "last": rows[-1]["observed"].isoformat(),
        },
        "split": {
            "train": [min(train_days), max(train_days)],
            "validation": [min(validation_days), max(validation_days)],
            "untouched_test": [min(test_days), max(test_days)],
        },
        "routes_before_test": routes,
        "selected_route": selected,
        "untouched_test_gross": test_metrics,
        "untouched_test_minus_1bp": test_minus_1bp,
        "untouched_test_minus_5bp": test_minus_5bp,
        "promotion_passed_after_untouched_test": test_passed,
        "final_decision": (
            "Promote the selected hourly route."
            if test_passed
            else "Do not promote an hourly route; the validation candidate failed the untouched test."
        ),
        "claim_ceiling": "C1 directional underlying proxy only; no historical option fills or future returns.",
        "falsifier": "Promotion requires at least 100 train trades, positive train and validation means, and validation mean above its standard error.",
        "stop_rule": "This is the final pre-window route-family expansion. If no route promotes, retain the strategy as C0 exploratory and reduce risk rather than searching more variants.",
    }
    output = ROOT / "evidence" / "hourly-regime-benchmark-receipt.json"
    output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
