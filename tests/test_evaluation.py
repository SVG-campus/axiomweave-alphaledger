from __future__ import annotations

import unittest
from dataclasses import replace

from alphaledger.evaluation import run_options_replay
from alphaledger.evaluation_demo import build_frozen_options_replay


class OptionsEvaluationTests(unittest.TestCase):
    def test_frozen_synthetic_replay_is_deterministic(self) -> None:
        episodes, manifest = build_frozen_options_replay()
        first = run_options_replay(episodes, manifest)
        second = run_options_replay(episodes, manifest)

        self.assertEqual(first.replay_fingerprint, second.replay_fingerprint)
        self.assertEqual(
            [metric.to_dict() for metric in first.metrics],
            [metric.to_dict() for metric in second.metrics],
        )
        self.assertEqual(first.claim_ceiling, "C1")

    def test_governed_route_abstains_on_six_of_eight_falsifiers(self) -> None:
        episodes, manifest = build_frozen_options_replay()
        receipt = run_options_replay(episodes, manifest)
        governed = receipt.metrics[0]

        self.assertEqual(governed.route, "governed options agent")
        self.assertEqual(governed.episodes, 8)
        self.assertEqual(governed.plans, 2)
        self.assertEqual(governed.abstentions, 6)
        self.assertEqual(governed.synthetic_realized_pnl, 10.0)
        self.assertEqual(governed.worst_episode_pnl, -20.0)
        self.assertEqual(governed.total_modeled_maximum_loss, 40.0)

    def test_controls_are_retained_and_cash_is_zero(self) -> None:
        episodes, manifest = build_frozen_options_replay()
        receipt = run_options_replay(episodes, manifest)
        by_route = {metric.route: metric for metric in receipt.metrics}

        self.assertEqual(by_route["cash/abstain control"].synthetic_realized_pnl, 0.0)
        self.assertEqual(by_route["cash/abstain control"].plans, 0)
        self.assertGreater(by_route["unguarded proposer control"].plans, 2)
        self.assertIn("shuffled-settlement negative control", by_route)

    def test_manifest_tampering_fails_closed(self) -> None:
        episodes, manifest = build_frozen_options_replay()
        tampered = (replace(episodes[0], settlement_underlying_price=650.0), *episodes[1:])

        with self.assertRaises(RuntimeError):
            run_options_replay(tampered, manifest)

    def test_invalid_settlement_fails_even_under_a_new_manifest(self) -> None:
        episodes, manifest = build_frozen_options_replay()
        invalid = (replace(episodes[0], settlement_underlying_price=float("nan")), *episodes[1:])
        invalid_manifest = replace(
            manifest,
            episodes_sha256=manifest.freeze(
                invalid,
                source_kind="synthetic",
                window_start=manifest.window_start,
                window_end=manifest.window_end,
            ).episodes_sha256,
        )

        with self.assertRaises(ValueError):
            run_options_replay(invalid, invalid_manifest)
        with self.assertRaises(ValueError):
            manifest.freeze(
                episodes,
                source_kind="synthetic",
                window_start=manifest.window_start,
                window_end=manifest.window_end,
                commission_per_contract=-0.01,
            )


if __name__ == "__main__":
    unittest.main()
