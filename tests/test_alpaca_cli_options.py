from __future__ import annotations

import json
import unittest

from alphaledger.alpaca_cli_options import AlpacaCliOptionsPaperExecutor
from alphaledger.options_demo import build_options_chain
from alphaledger.options import GovernedOptionsEngine


class FakeCliRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, command, *, input_text, env, timeout_seconds):
        self.calls.append(
            {
                "command": list(command),
                "input_text": input_text,
                "env_keys": sorted(key for key in env if key.startswith("ALPACA")),
                "timeout_seconds": timeout_seconds,
            }
        )
        return 0, json.dumps({"id": "paper-order-secret-ref", "status": "accepted"}), ""


def _environment(*, ack: bool = True) -> dict[str, str]:
    result = {
        "APCA_API_KEY_ID": "paper-key",
        "APCA_API_SECRET_KEY": "paper-secret",
    }
    if ack:
        result["ALPHALEDGER_PAPER_ORDER_ACK"] = (
            AlpacaCliOptionsPaperExecutor.REQUIRED_ACK
        )
    return result


class AlpacaCliOptionsTests(unittest.TestCase):
    def _thesis(self):
        return GovernedOptionsEngine().proposer.propose(build_options_chain())

    def test_open_and_close_use_official_cli_raw_paper_api(self) -> None:
        runner = FakeCliRunner()
        executor = AlpacaCliOptionsPaperExecutor(
            allow_submission=True,
            runner=runner,
            environment=_environment(),
        )
        opened = executor.submit_open(self._thesis())
        closed = executor.submit_close(self._thesis(), limit_credit_per_share=0.30)
        self.assertEqual(runner.calls[0]["command"], ["alpaca", "api", "POST", "/v2/orders"])
        self.assertEqual(len(opened.order_ref_sha256), 64)
        self.assertNotIn("paper-order-secret-ref", json.dumps(opened.to_dict()))
        close_payload = json.loads(runner.calls[1]["input_text"])
        self.assertEqual(
            {leg["position_intent"] for leg in close_payload["legs"]},
            {"buy_to_close", "sell_to_close"},
        )
        self.assertEqual(closed.action, "close")

    def test_no_ack_blocks_before_any_cli_call(self) -> None:
        runner = FakeCliRunner()
        executor = AlpacaCliOptionsPaperExecutor(
            allow_submission=True,
            runner=runner,
            environment=_environment(ack=False),
        )
        with self.assertRaisesRegex(RuntimeError, "locked"):
            executor.submit_open(self._thesis())
        self.assertEqual(runner.calls, [])

    def test_live_environment_fails_closed(self) -> None:
        environment = _environment()
        environment["ALPACA_LIVE_TRADE"] = "true"
        with self.assertRaisesRegex(RuntimeError, "fails closed"):
            AlpacaCliOptionsPaperExecutor(
                allow_submission=True,
                runner=FakeCliRunner(),
                environment=environment,
            )

    def test_cli_error_is_hashed_not_exposed(self) -> None:
        class FailingRunner(FakeCliRunner):
            def run(self, command, *, input_text, env, timeout_seconds):
                return 2, "", "credential-shaped-private-error"

        executor = AlpacaCliOptionsPaperExecutor(
            allow_submission=True,
            runner=FailingRunner(),
            environment=_environment(),
        )
        with self.assertRaisesRegex(RuntimeError, "stderr_sha256") as raised:
            executor.submit_open(self._thesis())
        self.assertNotIn("credential-shaped", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
