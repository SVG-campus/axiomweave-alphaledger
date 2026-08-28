from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from alphaledger.alpaca_readonly import PaperReadinessReceipt, ReadOnlyResponse
from alphaledger.competition import (
    CompetitionPhase,
    CompetitionRiskPolicy,
    CompetitionWindow,
    StockBar,
    compute_momentum_signal,
    evaluate_clean_competition_account,
    evaluate_entry_gate,
    evaluate_exit,
    natural_close_credit,
    normalize_stock_bars,
)


def _receipt() -> PaperReadinessReceipt:
    return PaperReadinessReceipt(
        observed_at="2026-08-31T13:25:00+00:00",
        ready_for_defined_risk_observation=True,
        reasons=("passed",),
        account_status="ACTIVE",
        equity=100000.0,
        cash=100000.0,
        buying_power=200000.0,
        daily_pnl=0.0,
        options_approved_level=3,
        options_trading_level=3,
        positions_count=0,
        open_orders_count=0,
        trading_blocked=False,
        request_ids=("redacted",),
        source_refs=("account", "positions", "orders"),
        account_ref_sha256="a" * 64,
    )


def _bars(step: float) -> tuple[StockBar, ...]:
    start = datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc)
    bars: list[StockBar] = []
    for index in range(30):
        close = 100.0 + step * index
        open_price = close - step * 0.4
        high = max(open_price, close) + 0.08
        low = min(open_price, close) - 0.08
        bars.append(
            StockBar(
                timestamp=start + timedelta(minutes=5 * index),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000.0 + index,
                vwap=(open_price + close) / 2.0,
            )
        )
    return tuple(bars)


class CompetitionTests(unittest.TestCase):
    def test_clock_has_four_entry_sessions_and_no_friday_session(self) -> None:
        window = CompetitionWindow()
        self.assertEqual(
            window.phase_at(datetime(2026, 8, 31, 13, 29, tzinfo=timezone.utc)),
            CompetitionPhase.PRE_WINDOW,
        )
        self.assertEqual(
            window.phase_at(datetime(2026, 8, 31, 14, 20, tzinfo=timezone.utc)),
            CompetitionPhase.ENTRY_ALLOWED,
        )
        self.assertEqual(
            window.phase_at(datetime(2026, 9, 1, 13, 55, tzinfo=timezone.utc)),
            CompetitionPhase.EXIT_ONLY,
        )
        self.assertEqual(
            window.phase_at(datetime(2026, 9, 3, 19, 45, tzinfo=timezone.utc)),
            CompetitionPhase.FORCE_FLAT,
        )
        self.assertEqual(
            window.phase_at(datetime(2026, 9, 4, 13, 29, tzinfo=timezone.utc)),
            CompetitionPhase.FORCE_FLAT,
        )
        self.assertEqual(
            window.phase_at(datetime(2026, 9, 4, 13, 30, tzinfo=timezone.utc)),
            CompetitionPhase.COMPLETE,
        )

    def test_clean_account_gate_requires_exact_new_baseline(self) -> None:
        self.assertTrue(evaluate_clean_competition_account(_receipt()).approved)
        dirty = replace(_receipt(), equity=99999.0, positions_count=1)
        decision = evaluate_clean_competition_account(dirty)
        self.assertFalse(decision.approved)
        self.assertTrue(any("$100,000" in reason for reason in decision.reasons))
        self.assertTrue(any("pre-existing position" in reason for reason in decision.reasons))

    def test_signal_distinguishes_bull_bear_and_neutral(self) -> None:
        as_of = datetime(2026, 8, 31, 15, 56, tzinfo=timezone.utc)
        bull = compute_momentum_signal(_bars(0.12), as_of=as_of)
        bear = compute_momentum_signal(_bars(-0.12), as_of=as_of)
        neutral = compute_momentum_signal(_bars(0.0), as_of=as_of)
        self.assertEqual(bull.direction, "bullish")
        self.assertEqual(bear.direction, "bearish")
        self.assertEqual(neutral.direction, "neutral")

    def test_signal_fails_closed_on_unsorted_or_stale_bars(self) -> None:
        as_of = datetime(2026, 8, 31, 15, 56, tzinfo=timezone.utc)
        values = list(_bars(0.1))
        values[-1], values[-2] = values[-2], values[-1]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            compute_momentum_signal(values, as_of=as_of)
        with self.assertRaisesRegex(ValueError, "stale"):
            compute_momentum_signal(
                _bars(0.1),
                as_of=as_of + timedelta(hours=1),
            )

    def test_entry_gate_honors_clock_and_drawdown(self) -> None:
        window = CompetitionWindow()
        policy = CompetitionRiskPolicy()
        now = datetime(2026, 8, 31, 15, 56, tzinfo=timezone.utc)
        signal = compute_momentum_signal(_bars(0.12), as_of=now)
        passed = evaluate_entry_gate(
            instant=now,
            window=window,
            policy=policy,
            signal=signal,
            current_equity=100000.0,
            daily_pnl=0.0,
            open_plans=0,
            aggregate_open_max_loss=0.0,
            entries_this_session=0,
        )
        self.assertTrue(passed.approved)
        stopped = evaluate_entry_gate(
            instant=now,
            window=window,
            policy=policy,
            signal=signal,
            current_equity=98999.0,
            daily_pnl=-1001.0,
            open_plans=0,
            aggregate_open_max_loss=0.0,
            entries_this_session=0,
        )
        self.assertFalse(stopped.approved)
        self.assertTrue(any("Daily drawdown" in reason for reason in stopped.reasons))

    def test_exit_policy_takes_profit_and_forces_thursday_flatten(self) -> None:
        window = CompetitionWindow()
        policy = CompetitionRiskPolicy()
        opened = datetime(2026, 8, 31, 15, 0, tzinfo=timezone.utc)
        profit = evaluate_exit(
            entry_debit_per_share=1.0,
            current_close_credit_per_share=1.6,
            opened_at=opened,
            instant=opened + timedelta(hours=1),
            window=window,
            policy=policy,
        )
        self.assertTrue(profit.should_close)
        self.assertEqual(profit.reason, "take_profit")
        force = evaluate_exit(
            entry_debit_per_share=1.0,
            current_close_credit_per_share=1.0,
            opened_at=opened,
            instant=datetime(2026, 9, 3, 19, 45, tzinfo=timezone.utc),
            window=window,
            policy=policy,
        )
        self.assertTrue(force.should_close)
        self.assertEqual(force.reason, "competition_force_flat")

    def test_alpaca_bar_normalization_and_close_credit_are_bounded(self) -> None:
        payload = {
            "bars": {
                "SPY": [
                    {"t": "2026-08-31T13:30:00Z", "o": 600, "h": 601, "l": 599, "c": 600.5, "v": 1000, "vw": 600.2}
                ]
            },
            "next_page_token": None,
        }
        response = ReadOnlyResponse(
            endpoint="https://data.alpaca.markets/v2/stocks/bars",
            observed_at="2026-08-31T13:31:00+00:00",
            request_id="request-bars",
            payload_sha256="hash",
            record_count=1,
            payload=payload,
        )
        normalized = normalize_stock_bars(response, "SPY")
        self.assertEqual(normalized[0].close, 600.5)
        self.assertEqual(
            natural_close_credit(
                {
                    "long": {"bid_price": 1.25},
                    "short": {"ask_price": 0.40},
                },
                "long",
                "short",
            ),
            0.85,
        )


if __name__ == "__main__":
    unittest.main()
