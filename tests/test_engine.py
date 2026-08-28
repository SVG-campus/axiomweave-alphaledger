from __future__ import annotations

import unittest

from alphaledger.critic import SkepticalCritic
from alphaledger.demo import build_snapshot
from alphaledger.engine import GovernedTradingEngine
from alphaledger.models import AccountState, MarketSnapshot, RiskPolicy


def bullish_snapshot(**overrides: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "symbol": "SPY",
        "observed_at": "2026-08-24T12:00:00+00:00",
        "last_price": 100.0,
        "short_ma": 101.0,
        "long_ma": 100.0,
        "realized_volatility": 0.01,
        "data_age_seconds": 10,
        "source_refs": ("source://bars", "policy://v1"),
    }
    values.update(overrides)
    return MarketSnapshot(**values)  # type: ignore[arg-type]


def account(**overrides: object) -> AccountState:
    values: dict[str, object] = {
        "equity": 500.0,
        "cash": 500.0,
        "buying_power": 500.0,
        "daily_pnl": 0.0,
        "positions": {},
        "open_orders": 0,
        "broker_mode": "simulation",
    }
    values.update(overrides)
    return AccountState(**values)  # type: ignore[arg-type]


class GovernedEngineTests(unittest.TestCase):
    def test_default_demo_snapshot_clears_the_valid_candidate_threshold(self) -> None:
        snapshot = build_snapshot()
        self.assertGreaterEqual((snapshot.short_ma / snapshot.long_ma) - 1.0, 0.0025)

    def test_default_demo_cycle_is_approved_without_exceeding_notional(self) -> None:
        result = GovernedTradingEngine().run_cycle(build_snapshot(), account())
        self.assertTrue(result.risk.approved)
        self.assertLessEqual(result.risk.projected_new_notional, 25.0)
        self.assertEqual(result.receipt.status, "simulated")

    def test_valid_candidate_is_simulated_and_recorded(self) -> None:
        engine = GovernedTradingEngine()
        result = engine.run_cycle(bullish_snapshot(), account())

        self.assertTrue(result.critic.passed)
        self.assertTrue(result.risk.approved)
        self.assertEqual(result.receipt.status, "simulated")
        self.assertEqual(len(engine.ledger.entries), 1)
        self.assertTrue(engine.ledger.verify()[0])

    def test_stale_data_forces_abstention(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(data_age_seconds=999), account())

        self.assertFalse(result.risk.approved)
        self.assertEqual(result.receipt.status, "abstained")
        self.assertIn("Market evidence is stale.", result.risk.reasons)

    def test_daily_loss_stop_forces_abstention(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(), account(daily_pnl=-10.0))

        self.assertFalse(result.risk.approved)
        self.assertIn("Daily-loss stop is active.", result.risk.reasons)

    def test_open_order_reconciliation_blocks_new_order(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(), account(open_orders=1))

        self.assertFalse(result.risk.approved)
        self.assertIn("Unreconciled open orders block new execution.", result.risk.reasons)

    def test_incomplete_evidence_manifest_fails_closed(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(source_refs=("source://bars",)), account())

        self.assertFalse(result.risk.approved)
        self.assertIn("Evidence manifest is incomplete.", result.risk.reasons)

    def test_nonpaper_broker_mode_fails_closed(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(), account(broker_mode="live"))

        self.assertFalse(result.risk.approved)
        self.assertIn("Broker mode is neither simulation nor paper.", result.risk.reasons)

    def test_policy_cannot_disable_paper_only(self) -> None:
        result = GovernedTradingEngine().run_cycle(bullish_snapshot(), account(), RiskPolicy(paper_only=False))

        self.assertFalse(result.risk.approved)
        self.assertIn("Policy is not locked to paper-only mode.", result.risk.reasons)

    def test_duplicate_evidence_is_rejected_by_critic(self) -> None:
        snapshot = bullish_snapshot(source_refs=("same", "same"))
        thesis = GovernedTradingEngine().proposer.propose(snapshot, account())
        verdict = SkepticalCritic().review(thesis, snapshot)

        self.assertFalse(verdict.passed)
        self.assertIn("Evidence manifest contains duplicate references.", verdict.reasons)


if __name__ == "__main__":
    unittest.main()
