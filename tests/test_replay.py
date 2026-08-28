from __future__ import annotations

import unittest

from alphaledger.demo import demo_prices
from alphaledger.replay import replay_controls


class ReplayTests(unittest.TestCase):
    def test_replay_is_deterministic(self) -> None:
        first = [metric.to_dict() for metric in replay_controls(demo_prices(), seed=17)]
        second = [metric.to_dict() for metric in replay_controls(demo_prices(), seed=17)]
        self.assertEqual(first, second)

    def test_required_controls_are_present(self) -> None:
        names = {metric.name for metric in replay_controls(demo_prices())}
        self.assertEqual(
            names,
            {
                "governed momentum replay",
                "buy-and-hold baseline",
                "cash/abstain control",
                "shuffled-return negative control",
            },
        )

    def test_short_replay_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            replay_controls([100.0] * 10)


if __name__ == "__main__":
    unittest.main()
