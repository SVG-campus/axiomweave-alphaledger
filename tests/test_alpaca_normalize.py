from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alphaledger.alpaca_normalize import normalize_option_chain
from alphaledger.alpaca_readonly import ReadOnlyResponse
from alphaledger.models import AccountState
from alphaledger.options import GovernedOptionsEngine


FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def _response(endpoint: str, payload: dict[str, Any]) -> ReadOnlyResponse:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return ReadOnlyResponse(
        endpoint=endpoint,
        observed_at=AS_OF.isoformat(),
        request_id="fixture-request",
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        record_count=1,
        payload=payload,
    )


def _normalize(
    *,
    stock: dict[str, Any] | None = None,
    contracts: dict[str, Any] | None = None,
    chain: dict[str, Any] | None = None,
    as_of: datetime = AS_OF,
    option_type: str = "call",
):
    return normalize_option_chain(
        "SPY",
        _response(
            "https://data.alpaca.markets/v2/stocks/SPY/snapshot",
            stock or _fixture("alpaca_stock_snapshot.json"),
        ),
        _response(
            "https://paper-api.alpaca.markets/v2/options/contracts",
            contracts or _fixture("alpaca_option_contracts.json"),
        ),
        _response(
            "https://data.alpaca.markets/v1beta1/options/snapshots/SPY",
            chain or _fixture("alpaca_option_chain.json"),
        ),
        as_of=as_of,
        stock_feed="iex",
        options_feed="indicative",
        option_type=option_type,
    )


class AlpacaNormalizationTests(unittest.TestCase):
    def test_requested_puts_normalize_without_admitting_calls(self) -> None:
        contracts = _fixture("alpaca_option_contracts.json")
        chain = _fixture("alpaca_option_chain.json")
        put_rows = []
        put_snapshots = {}
        for row in contracts["option_contracts"]:
            converted = copy.deepcopy(row)
            old_symbol = converted["symbol"]
            new_symbol = old_symbol.replace("C", "P", 1)
            converted["symbol"] = new_symbol
            converted["type"] = "put"
            put_rows.append(converted)
            put_snapshots[new_symbol] = chain["snapshots"][old_symbol]
        normalized = _normalize(
            contracts={"option_contracts": put_rows, "next_page_token": None},
            chain={"snapshots": put_snapshots, "next_page_token": None},
            option_type="put",
        )
        self.assertTrue(normalized.chain.contracts)
        self.assertTrue(all(contract.option_type == "put" for contract in normalized.chain.contracts))

    def test_frozen_alpaca_shapes_reproduce_governed_twenty_dollar_plan(self) -> None:
        normalized = _normalize()
        account = AccountState(
            equity=100000.0,
            cash=100000.0,
            buying_power=200000.0,
            daily_pnl=5.0,
            broker_mode="paper",
        )
        result = GovernedOptionsEngine().run_cycle(normalized.chain, account)

        self.assertEqual(len(normalized.chain.contracts), 3)
        self.assertEqual(normalized.chain.underlying_data_age_seconds, 12)
        self.assertEqual(normalized.chain.underlying_feed, "iex")
        self.assertEqual(normalized.chain.options_feed, "indicative")
        self.assertTrue(result.risk.approved)
        self.assertEqual(result.risk.projected_max_loss, 20.0)
        self.assertEqual(result.receipt.status, "simulated_plan")

    def test_stale_underlying_fixture_is_rejected_by_policy(self) -> None:
        normalized = _normalize(as_of=datetime(2026, 8, 24, 12, 20, tzinfo=timezone.utc))
        result = GovernedOptionsEngine().run_cycle(
            normalized.chain,
            AccountState(100000.0, 100000.0, 200000.0, 0.0, broker_mode="paper"),
        )
        self.assertFalse(result.risk.approved)
        self.assertIn("Underlying evidence is stale.", result.risk.reasons)

    def test_pagination_token_fails_closed(self) -> None:
        contracts = _fixture("alpaca_option_contracts.json")
        contracts["next_page_token"] = "more-results"
        with self.assertRaisesRegex(RuntimeError, "paginated"):
            _normalize(contracts=contracts)

    def test_stock_symbol_mismatch_fails_closed(self) -> None:
        stock = _fixture("alpaca_stock_snapshot.json")
        stock["symbol"] = "QQQ"
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            _normalize(stock=stock)

    def test_future_dated_stock_trade_fails_closed(self) -> None:
        stock = _fixture("alpaca_stock_snapshot.json")
        stock["latestTrade"]["t"] = "2026-08-24T12:00:30Z"
        with self.assertRaisesRegex(RuntimeError, "future-dated"):
            _normalize(stock=stock)

    def test_malformed_contract_is_named_and_skipped(self) -> None:
        chain = _fixture("alpaca_option_chain.json")
        chain["snapshots"]["SPY260918C00602000"]["latestQuote"]["bp"] = "bad"
        normalized = _normalize(chain=chain)
        result = GovernedOptionsEngine().run_cycle(
            normalized.chain,
            AccountState(100000.0, 100000.0, 200000.0, 0.0, broker_mode="paper"),
        )

        self.assertEqual(len(normalized.chain.contracts), 2)
        self.assertEqual(len(normalized.skipped_contracts), 1)
        self.assertIn("SPY260918C00602000", normalized.skipped_contracts[0])
        self.assertTrue(result.risk.approved)

    def test_redacted_receipt_contains_hashes_not_raw_payload(self) -> None:
        stock = copy.deepcopy(_fixture("alpaca_stock_snapshot.json"))
        stock["dailyBar"]["raw_only_sentinel"] = "must-not-enter-receipt"
        normalized = _normalize(stock=stock)
        serialized = json.dumps(normalized.to_receipt_dict(), sort_keys=True)

        self.assertNotIn("must-not-enter-receipt", serialized)
        self.assertNotIn("latestTrade", serialized)
        self.assertEqual(len(normalized.payload_hashes), 3)
        self.assertEqual(len(normalized.source_refs), 3)


if __name__ == "__main__":
    unittest.main()
