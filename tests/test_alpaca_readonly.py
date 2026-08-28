from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from alphaledger.alpaca_readonly import AlpacaCredentials, AlpacaReadOnlyObserver, JsonPayload


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


class FakeGetTransport:
    def __init__(
        self,
        *,
        account: dict[str, Any] | None = None,
        positions: list[Any] | None = None,
        orders: list[Any] | None = None,
        stock: dict[str, Any] | None = None,
        contracts: dict[str, Any] | None = None,
        chain: dict[str, Any] | None = None,
        bars: dict[str, Any] | None = None,
    ) -> None:
        self.account = account or {
            "status": "ACTIVE",
            "equity": "100000.00",
            "last_equity": "99995.00",
            "cash": "100000.00",
            "buying_power": "200000.00",
            "options_approved_level": 3,
            "options_trading_level": 3,
            "trading_blocked": False,
            "account_blocked": False,
            "trade_suspended_by_user": False,
            "id": "must-not-enter-receipt",
        }
        self.positions = positions if positions is not None else []
        self.orders = orders if orders is not None else []
        self.stock = stock or {"symbol": "SPY", "latestTrade": {"t": "2026-08-24T11:59:48Z", "p": 600.0}}
        self.contracts = contracts or {"option_contracts": [{"symbol": "SPY260918C00600000"}]}
        self.chain = chain or {"snapshots": {"SPY260918C00600000": {"greeks": {"delta": 0.5}}}}
        self.bars = bars or {
            "bars": {
                "SPY": [
                    {"t": "2026-08-28T15:00:00Z", "o": 600, "h": 601, "l": 599, "c": 600.5, "v": 1000, "vw": 600.2}
                ]
            },
            "next_page_token": None,
        }
        self.calls: list[dict[str, Any]] = []

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str | int | float | bool],
        timeout_seconds: float,
    ) -> tuple[JsonPayload, Mapping[str, str]]:
        self.calls.append(
            {
                "url": url,
                "header_names": tuple(sorted(headers)),
                "params": dict(params),
                "timeout_seconds": timeout_seconds,
            }
        )
        if url.endswith("/v2/account"):
            return self.account, {"X-Request-ID": "request-account"}
        if url.endswith("/v2/positions"):
            return self.positions, {"X-Request-ID": "request-positions"}
        if url.endswith("/v2/orders"):
            return self.orders, {"X-Request-ID": "request-orders"}
        if url.endswith("/v2/options/contracts"):
            return self.contracts, {
                "X-Request-ID": "request-contracts"
            }
        if url.endswith("/v2/stocks/SPY/snapshot"):
            return self.stock, {"X-Request-ID": "request-stock"}
        if "/v1beta1/options/snapshots/SPY" in url:
            return self.chain, {
                "X-Request-ID": "request-chain"
            }
        if url.endswith("/v2/stocks/bars"):
            return self.bars, {"X-Request-ID": "request-bars"}
        raise AssertionError(f"Unexpected read-only URL {url}")


class AlpacaReadOnlyObserverTests(unittest.TestCase):
    def _observer(self, transport: FakeGetTransport) -> AlpacaReadOnlyObserver:
        return AlpacaReadOnlyObserver(
            AlpacaCredentials("paper-test-id", "paper-test-secret"),
            transport=transport,
        )

    def test_missing_credentials_fail_before_any_request(self) -> None:
        with self.assertRaises(RuntimeError):
            AlpacaCredentials.from_environment({})

    def test_reconciliation_is_get_only_ready_and_redacted(self) -> None:
        transport = FakeGetTransport()
        credentials = AlpacaCredentials("paper-test-id", "paper-test-secret")
        receipt = AlpacaReadOnlyObserver(credentials, transport=transport).reconcile()

        self.assertTrue(receipt.ready_for_defined_risk_observation)
        self.assertEqual(receipt.open_orders_count, 0)
        self.assertEqual(receipt.positions_count, 0)
        self.assertEqual(len(transport.calls), 3)
        self.assertTrue(all(call["url"].startswith("https://paper-api.alpaca.markets/") for call in transport.calls))
        serialized = json.dumps(receipt.to_dict())
        self.assertNotIn("paper-test-id", serialized)
        self.assertNotIn("paper-test-secret", serialized)
        self.assertNotIn("must-not-enter-receipt", serialized)
        self.assertEqual(len(receipt.account_ref_sha256), 64)
        self.assertNotIn("paper-test-id", repr(credentials))
        self.assertNotIn("paper-test-secret", repr(credentials))
        account_state = receipt.to_account_state()
        self.assertEqual(account_state.broker_mode, "paper")
        self.assertEqual(account_state.open_orders, 0)

    def test_positions_open_orders_or_low_options_level_fail_readiness(self) -> None:
        account = FakeGetTransport().account.copy()
        account["options_trading_level"] = 2
        transport = FakeGetTransport(
            account=account,
            positions=[{"symbol": "SPY"}],
            orders=[{"id": "paper-order"}],
        )
        receipt = self._observer(transport).reconcile()

        self.assertFalse(receipt.ready_for_defined_risk_observation)
        self.assertTrue(any("options level 3" in reason for reason in receipt.reasons))
        self.assertTrue(any("Existing positions" in reason for reason in receipt.reasons))
        self.assertTrue(any("Open orders" in reason for reason in receipt.reasons))
        with self.assertRaisesRegex(RuntimeError, "nonready"):
            receipt.to_account_state()

    def test_live_trading_host_is_rejected_even_inside_private_dispatch(self) -> None:
        observer = self._observer(FakeGetTransport())
        with self.assertRaises(RuntimeError):
            observer._get("https://api.alpaca.markets", "/v2/account")  # noqa: SLF001
        with self.assertRaises(RuntimeError):
            observer._get(  # noqa: SLF001
                "https://data.alpaca.markets",
                "/v1beta1/options/snapshots/extra/SPY",
            )

    def test_options_reads_use_documented_hosts_and_explicit_feed(self) -> None:
        transport = FakeGetTransport()
        observer = self._observer(transport)
        contracts = observer.read_option_contracts(
            "SPY",
            expiration_date_gte="2026-09-04",
            expiration_date_lte="2026-10-09",
        )
        chain = observer.read_option_chain(
            "SPY",
            expiration_date_gte="2026-09-04",
            expiration_date_lte="2026-10-09",
            strike_price_gte=550.0,
            strike_price_lte=650.0,
            feed="indicative",
        )

        self.assertEqual(contracts.record_count, 1)
        self.assertEqual(chain.record_count, 1)
        self.assertEqual(
            transport.calls[-2]["url"],
            "https://paper-api.alpaca.markets/v2/options/contracts",
        )
        self.assertEqual(
            transport.calls[-1]["url"],
            "https://data.alpaca.markets/v1beta1/options/snapshots/SPY",
        )
        self.assertEqual(transport.calls[-1]["params"]["feed"], "indicative")

    def test_stock_snapshot_uses_exact_data_host_and_explicit_feed(self) -> None:
        transport = FakeGetTransport()
        snapshot = self._observer(transport).read_stock_snapshot("SPY", feed="iex")

        self.assertEqual(snapshot.record_count, 1)
        self.assertEqual(
            transport.calls[-1]["url"],
            "https://data.alpaca.markets/v2/stocks/SPY/snapshot",
        )
        self.assertEqual(transport.calls[-1]["params"]["feed"], "iex")

    def test_stock_bars_use_bounded_documented_data_endpoint(self) -> None:
        transport = FakeGetTransport()
        response = self._observer(transport).read_stock_bars(
            "SPY",
            start="2026-08-28T13:30:00Z",
            end="2026-08-28T15:00:00Z",
            timeframe="5Min",
            feed="iex",
        )
        self.assertEqual(response.record_count, 1)
        self.assertEqual(
            transport.calls[-1]["url"],
            "https://data.alpaca.markets/v2/stocks/bars",
        )
        self.assertEqual(transport.calls[-1]["params"]["symbols"], "SPY")
        self.assertEqual(transport.calls[-1]["params"]["sort"], "asc")

    def test_put_chain_is_explicitly_selected(self) -> None:
        transport = FakeGetTransport()
        self._observer(transport).read_option_chain(
            "SPY",
            expiration_date_gte="2026-09-11",
            expiration_date_lte="2026-09-18",
            strike_price_gte=550.0,
            strike_price_lte=650.0,
            option_type="put",
            feed="indicative",
        )
        self.assertEqual(transport.calls[-1]["params"]["type"], "put")

    def test_three_get_observation_normalizes_into_governed_shape(self) -> None:
        transport = FakeGetTransport(
            stock=_fixture("alpaca_stock_snapshot.json"),
            contracts=_fixture("alpaca_option_contracts.json"),
            chain=_fixture("alpaca_option_chain.json"),
        )
        normalized = self._observer(transport).observe_option_chain(
            "SPY",
            expiration_date_gte="2026-09-04",
            expiration_date_lte="2026-10-09",
            strike_price_gte=550.0,
            strike_price_lte=650.0,
            stock_feed="iex",
            options_feed="indicative",
            as_of=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(len(normalized.chain.contracts), 3)
        self.assertEqual(normalized.chain.underlying_price, 600.0)
        self.assertEqual(normalized.chain.underlying_feed, "iex")
        self.assertEqual(normalized.chain.options_feed, "indicative")

    def test_malformed_symbol_or_implicit_feed_is_rejected(self) -> None:
        observer = self._observer(FakeGetTransport())
        with self.assertRaises(ValueError):
            observer.read_option_chain(
                "SPY/../orders",
                expiration_date_gte="2026-09-04",
                expiration_date_lte="2026-10-09",
                strike_price_gte=550.0,
                strike_price_lte=650.0,
            )
        with self.assertRaises(ValueError):
            observer.read_option_chain(
                "SPY",
                expiration_date_gte="2026-09-04",
                expiration_date_lte="2026-10-09",
                strike_price_gte=550.0,
                strike_price_lte=650.0,
                feed="sip",
            )
        with self.assertRaises(ValueError):
            observer.read_stock_snapshot("SPY", feed="indicative")


if __name__ == "__main__":
    unittest.main()
