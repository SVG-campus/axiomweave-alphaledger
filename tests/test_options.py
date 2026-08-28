from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from alphaledger.advisory import OpenAIOptionsAdvisory
from alphaledger.options import (
    AdvisoryMemo,
    DeterministicOptionsRiskGate,
    GovernedOptionsEngine,
    OptionsRiskPolicy,
    TemplateOptionsAdvisory,
    UnavailableOptionsAdvisory,
    DefinedRiskOptionsProposer,
    OptionChainSnapshot,
    build_alpaca_mleg_payload,
    build_alpaca_mleg_close_payload,
)
from alphaledger.options_demo import build_options_account, build_options_chain


class OptionsAgentTests(unittest.TestCase):
    def test_valid_defined_risk_spread_produces_simulated_mleg_plan(self) -> None:
        engine = GovernedOptionsEngine()
        result = engine.run_cycle(build_options_chain(), build_options_account())

        self.assertTrue(result.risk.approved)
        self.assertEqual(result.thesis.strategy, "bull_call_debit_spread")
        self.assertEqual(result.thesis.max_loss_dollars, 20.0)
        self.assertEqual(result.thesis.max_profit_dollars, 80.0)
        self.assertEqual(result.receipt.status, "simulated_plan")
        self.assertEqual(result.receipt.order_payload["order_class"], "mleg")  # type: ignore[index]
        self.assertEqual(result.receipt.order_payload["type"], "limit")  # type: ignore[index]
        self.assertEqual(len(result.receipt.order_payload["legs"]), 2)  # type: ignore[index]
        self.assertTrue(engine.ledger.verify()[0])

    def test_bear_put_debit_spread_is_supported_and_bounded(self) -> None:
        source = build_options_chain()
        puts = tuple(
            replace(
                contract,
                symbol=f"SPY260918P{int(strike * 1000):08d}",
                option_type="put",
                strike_price=strike,
                delta=-abs(contract.delta or 0.4),
            )
            for contract, strike in zip(source.contracts, (600.0, 599.0, 598.0))
        )
        chain = OptionChainSnapshot(
            underlying_symbol="SPY",
            underlying_price=600.0,
            observed_at=source.observed_at,
            contracts=puts,
            source_refs=source.source_refs,
        )
        engine = GovernedOptionsEngine(
            proposer=DefinedRiskOptionsProposer(direction="bearish")
        )
        result = engine.run_cycle(chain, build_options_account())
        self.assertTrue(result.risk.approved)
        self.assertEqual(result.thesis.strategy, "bear_put_debit_spread")
        self.assertLess(result.thesis.breakeven_price, 600.0)
        self.assertEqual(result.receipt.order_payload["order_class"], "mleg")  # type: ignore[index]

    def test_competition_sizing_never_exceeds_contract_or_loss_budget(self) -> None:
        proposer = DefinedRiskOptionsProposer(
            direction="bullish",
            max_contracts=5,
            max_loss_budget=500.0,
        )
        thesis = proposer.propose(build_options_chain())
        self.assertEqual(thesis.quantity, 5)
        self.assertLessEqual(thesis.max_loss_dollars, 500.0)
        policy = OptionsRiskPolicy(
            max_contracts=5,
            max_loss_dollars=500.0,
            max_net_debit_per_share=5.0,
        )
        result = GovernedOptionsEngine(proposer=proposer).run_cycle(
            build_options_chain(),
            replace(build_options_account(), equity=100000, cash=100000, buying_power=200000),
            policy,
        )
        self.assertTrue(result.risk.approved)

    def test_close_payload_reverses_both_legs(self) -> None:
        thesis = GovernedOptionsEngine().proposer.propose(build_options_chain())
        payload = build_alpaca_mleg_close_payload(thesis, limit_credit_per_share=0.30)
        self.assertEqual(
            {leg["position_intent"] for leg in payload["legs"]},
            {"buy_to_close", "sell_to_close"},
        )

    def test_stale_option_evidence_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Stale option evidence"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertTrue(any("stale" in reason for reason in result.risk.reasons))
        self.assertIsNone(result.receipt.order_payload)

    def test_stale_underlying_evidence_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Stale underlying snapshot"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Underlying evidence is stale.", result.risk.reasons)
        self.assertIsNone(result.receipt.order_payload)

    def test_unknown_feed_provenance_forces_abstention(self) -> None:
        chain = replace(build_options_chain(), underlying_feed="unknown", options_feed="unknown")
        result = GovernedOptionsEngine().run_cycle(chain, build_options_account())
        self.assertFalse(result.risk.approved)
        self.assertIn("Underlying feed is outside the frozen allowlist.", result.risk.reasons)
        self.assertIn("Options feed is outside the frozen allowlist.", result.risk.reasons)

    def test_missing_greeks_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Missing Greeks"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertTrue(any("Greeks" in reason for reason in result.risk.reasons))

    def test_wide_market_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Wide bid-ask market"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertTrue(any("too wide" in reason for reason in result.risk.reasons))

    def test_maximum_loss_budget_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Maximum loss above budget"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Maximum loss exceeds the options risk budget.", result.risk.reasons)

    def test_low_open_interest_forces_abstention(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("Low open interest"), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertTrue(any("open interest" in reason for reason in result.risk.reasons))

    def test_no_vertical_preserves_abstention_baseline(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain("No valid vertical"), build_options_account()
        )
        self.assertEqual(result.thesis.strategy, "abstain")
        self.assertFalse(result.risk.approved)
        self.assertEqual(result.receipt.status, "abstained")

    def test_live_broker_mode_fails_closed(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain(), build_options_account(broker_mode="live")
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Broker mode is neither simulation nor paper.", result.risk.reasons)

    def test_open_order_reconciliation_blocks_options_plan(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain(), build_options_account(open_orders=1)
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Unreconciled open orders block a new options plan.", result.risk.reasons)

    def test_advisory_can_veto_but_cannot_authorize(self) -> None:
        chain = build_options_chain("Maximum loss above budget")
        thesis = GovernedOptionsEngine().proposer.propose(chain)
        account = build_options_account()
        optimistic = AdvisoryMemo(
            summary="approve",
            falsifier="none",
            concerns=("none",),
            abstain_recommended=False,
            source="test",
        )
        risk = DeterministicOptionsRiskGate().evaluate(
            thesis, chain, account, OptionsRiskPolicy(), optimistic
        )
        self.assertFalse(risk.approved)
        self.assertIn("Maximum loss exceeds the options risk budget.", risk.reasons)

    def test_gate_recomputes_economics_and_rejects_tampered_claims(self) -> None:
        engine = GovernedOptionsEngine()
        chain = build_options_chain()
        thesis = engine.proposer.propose(chain)
        tampered = replace(
            thesis,
            net_debit_per_share=0.01,
            max_loss_dollars=1.0,
            max_profit_dollars=99.0,
            breakeven_price=600.01,
        )
        risk = DeterministicOptionsRiskGate().evaluate(
            tampered,
            chain,
            build_options_account(),
            OptionsRiskPolicy(),
            TemplateOptionsAdvisory().analyze(tampered),
        )

        self.assertFalse(risk.approved)
        self.assertEqual(risk.projected_max_loss, 20.0)
        self.assertEqual(risk.projected_max_profit, 80.0)
        self.assertTrue(any("quote-derived economics" in reason for reason in risk.reasons))

    def test_recomputed_maximum_loss_must_fit_available_buying_power(self) -> None:
        chain = build_options_chain()
        account = replace(build_options_account(), cash=10.0, buying_power=10.0)
        result = GovernedOptionsEngine().run_cycle(chain, account)

        self.assertFalse(result.risk.approved)
        self.assertIn(
            "Available cash or buying power cannot cover the recomputed maximum loss.",
            result.risk.reasons,
        )

    def test_unavailable_model_fails_closed(self) -> None:
        result = GovernedOptionsEngine(advisory=UnavailableOptionsAdvisory()).run_cycle(
            build_options_chain(), build_options_account()
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Advisory critic recommended abstention.", result.risk.reasons)

    def test_mleg_payload_rejects_unapproved_shape(self) -> None:
        abstention = GovernedOptionsEngine().proposer.propose(build_options_chain("No valid vertical"))
        with self.assertRaises(ValueError):
            build_alpaca_mleg_payload(abstention)

    def test_template_advisory_is_deterministic(self) -> None:
        thesis = GovernedOptionsEngine().proposer.propose(build_options_chain())
        first = TemplateOptionsAdvisory().analyze(thesis).to_dict()
        second = TemplateOptionsAdvisory().analyze(thesis).to_dict()
        self.assertEqual(first, second)

    def test_openai_advisory_requires_key_and_explicit_model(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                OpenAIOptionsAdvisory()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            with self.assertRaises(RuntimeError):
                OpenAIOptionsAdvisory()

    def test_paper_policy_cannot_be_disabled(self) -> None:
        result = GovernedOptionsEngine().run_cycle(
            build_options_chain(),
            build_options_account(),
            OptionsRiskPolicy(paper_only=False),
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Policy is not locked to paper-only mode.", result.risk.reasons)


if __name__ == "__main__":
    unittest.main()
