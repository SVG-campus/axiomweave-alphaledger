from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from alphaledger.alpaca_readonly import AlpacaCredentials, AlpacaReadOnlyObserver


CONTRACTS = "https://paper-api.alpaca.markets/v2/options/contracts"
SNAPSHOTS = "https://data.alpaca.markets/v1beta1/options/snapshots/SPY"
STOCK = "https://data.alpaca.markets/v2/stocks/SPY/snapshot"
DATES = {"expiration_date_gte": "2026-09-07", "expiration_date_lte": "2026-09-18"}


class PageTransport:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get_json(self, url, *, headers, params, timeout_seconds):
        self.calls.append({"url": url, "params": dict(params)})
        result = self.pages[(url, params.get("page_token"))]
        if isinstance(result, Exception):
            raise result
        return result, {}


def contracts(symbol, token=None):
    return {"option_contracts": [{"symbol": symbol}], "next_page_token": token}


def observer(pages):
    transport = PageTransport(pages)
    return AlpacaReadOnlyObserver(AlpacaCredentials("test-key", "test-secret"), transport=transport), transport


class OptionsPaginationTests(unittest.TestCase):
    def test_complete_contracts_merge_and_hash_all_pages_without_tokens(self):
        first, second = contracts("A", "opaque-token"), contracts("B")
        reader, transport = observer({(CONTRACTS, None): first, (CONTRACTS, "opaque-token"): second})
        result = reader.read_option_contracts("SPY", option_type="put", **DATES)
        self.assertEqual(result.record_count, 2)
        self.assertEqual([r["symbol"] for r in result.payload["option_contracts"]], ["A", "B"])
        self.assertIsNone(result.payload["next_page_token"])
        self.assertEqual(result.payload["_pagination"]["page_count"], 2)
        self.assertTrue(result.payload["_pagination"]["complete"])
        canonical = json.dumps(result.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(result.payload_sha256, hashlib.sha256(canonical.encode()).hexdigest())
        self.assertNotIn("opaque-token", json.dumps(result.payload))
        for page, original in zip(result.payload["_pagination"]["pages"], (first, second)):
            expected = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(page["payload_sha256"], expected)
        self.assertEqual(transport.calls[1]["params"], {**transport.calls[0]["params"], "page_token": "opaque-token"})
        self.assertEqual(transport.calls[1]["params"]["type"], "put")
        self.assertEqual(transport.calls[0]["url"], transport.calls[1]["url"])

    def test_single_complete_page_is_unchanged(self):
        payload = contracts("A")
        reader, transport = observer({(CONTRACTS, None): payload})
        result = reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(result.payload, payload)
        self.assertEqual(len(transport.calls), 1)

    def test_snapshots_merge_without_changing_feed_or_strike_filters(self):
        reader, transport = observer({
            (SNAPSHOTS, None): {"snapshots": {"A": {"price": 1}}, "next_page_token": "next"},
            (SNAPSHOTS, "next"): {"snapshots": {"B": {"price": 2}}, "next_page_token": None},
        })
        result = reader.read_option_chain("SPY", strike_price_gte=700, strike_price_lte=800, feed="indicative", **DATES)
        self.assertEqual(result.payload["snapshots"], {"A": {"price": 1}, "B": {"price": 2}})
        self.assertEqual(result.record_count, 2)
        self.assertEqual(transport.calls[1]["params"], {**transport.calls[0]["params"], "page_token": "next"})

    def test_repeated_token_fails_without_third_request(self):
        reader, transport = observer({(CONTRACTS, None): contracts("A", "next"), (CONTRACTS, "next"): contracts("B", "next")})
        with self.assertRaisesRegex(RuntimeError, "token repeated"):
            reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 2)

    def test_token_cycle_fails_without_fourth_request(self):
        reader, transport = observer({(CONTRACTS, None): contracts("A", "one"), (CONTRACTS, "one"): contracts("B", "two"), (CONTRACTS, "two"): contracts("C", "one")})
        with self.assertRaisesRegex(RuntimeError, "token repeated"):
            reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 3)

    def test_duplicate_contract_fails_closed(self):
        reader, _ = observer({(CONTRACTS, None): contracts("A", "next"), (CONTRACTS, "next"): contracts("A")})
        with self.assertRaisesRegex(RuntimeError, "duplicate symbol"):
            reader.read_option_contracts("SPY", **DATES)

    def test_duplicate_snapshot_fails_closed(self):
        reader, _ = observer({(SNAPSHOTS, None): {"snapshots": {"A": {}}, "next_page_token": "next"}, (SNAPSHOTS, "next"): {"snapshots": {"A": {"changed": True}}}})
        with self.assertRaisesRegex(RuntimeError, "duplicate symbol"):
            reader.read_option_chain("SPY", strike_price_gte=700, strike_price_lte=800, **DATES)

    def test_empty_intermediate_page_fails_closed(self):
        reader, transport = observer({(CONTRACTS, None): {"option_contracts": [], "next_page_token": "next"}})
        with self.assertRaisesRegex(RuntimeError, "empty intermediate"):
            reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 1)

    def test_malformed_tokens_fail_without_exposing_value(self):
        for token in (123, True, {}, [], " ", "x" * 8193):
            with self.subTest(token_type=type(token).__name__):
                reader, transport = observer({(CONTRACTS, None): contracts("A", token)})
                with self.assertRaisesRegex(RuntimeError, "token is malformed"):
                    reader.read_option_contracts("SPY", **DATES)
                self.assertEqual(len(transport.calls), 1)

    def test_malformed_pages_fail_closed(self):
        for payload in ([], {}, {"option_contracts": {}}, {"option_contracts": [None]}, {"option_contracts": [{"symbol": ""}]}):
            with self.subTest(payload=payload):
                reader, _ = observer({(CONTRACTS, None): payload})
                with self.assertRaises(RuntimeError):
                    reader.read_option_contracts("SPY", **DATES)

    def test_page_budget_never_returns_partial_result(self):
        reader, transport = observer({(CONTRACTS, None): contracts("A", "one"), (CONTRACTS, "one"): contracts("B", "two")})
        with patch.object(reader, "_MAX_OPTION_PAGES", 2):
            with self.assertRaisesRegex(RuntimeError, "page budget"):
                reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 2)

    def test_record_budget_never_returns_partial_result(self):
        reader, _ = observer({(CONTRACTS, None): contracts("A", "next"), (CONTRACTS, "next"): contracts("B")})
        with patch.object(reader, "_MAX_OPTION_RECORDS", 1):
            with self.assertRaisesRegex(RuntimeError, "record budget"):
                reader.read_option_contracts("SPY", **DATES)

    def test_elapsed_budget_rejects_late_response(self):
        reader, transport = observer({(CONTRACTS, None): contracts("A")})
        with patch("alphaledger.alpaca_readonly.time.monotonic", side_effect=[0, 0, 21]):
            with self.assertRaisesRegex(RuntimeError, "elapsed-time budget"):
                reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 1)

    def test_second_page_transport_failure_is_not_swallowed(self):
        reader, transport = observer({(CONTRACTS, None): contracts("A", "next"), (CONTRACTS, "next"): TimeoutError("fixture timeout")})
        with self.assertRaises(TimeoutError):
            reader.read_option_contracts("SPY", **DATES)
        self.assertEqual(len(transport.calls), 2)

    def test_ambiguous_page_metadata_is_not_stripped(self):
        reader, _ = observer({(CONTRACTS, None): {**contracts("A"), "page_token": "unexpected"}})
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            reader.read_option_contracts("SPY", **DATES)

    def test_pagination_cannot_expand_endpoint_allowlist_or_start_midway(self):
        reader, transport = observer({})
        with self.assertRaisesRegex(RuntimeError, "allowlist"):
            reader._get_option_pages("https://api.alpaca.markets", "/v2/options/contracts", {}, collection="option_contracts")
        with self.assertRaisesRegex(RuntimeError, "first page"):
            reader._get_option_pages(reader.PAPER_BASE, "/v2/options/contracts", {"page_token": "skip"}, collection="option_contracts")
        self.assertEqual(transport.calls, [])

    def test_both_paginated_datasets_normalize_to_same_complete_fixture(self):
        fixtures = Path(__file__).parent / "fixtures"
        stock = json.loads((fixtures / "alpaca_stock_snapshot.json").read_text())
        rows = json.loads((fixtures / "alpaca_option_contracts.json").read_text())["option_contracts"]
        snapshots = json.loads((fixtures / "alpaca_option_chain.json").read_text())["snapshots"]
        symbols = list(snapshots)
        reader, transport = observer({
            (STOCK, None): stock,
            (CONTRACTS, None): {"option_contracts": rows[:1], "next_page_token": "contracts-2"},
            (CONTRACTS, "contracts-2"): {"option_contracts": rows[1:], "next_page_token": None},
            (SNAPSHOTS, None): {"snapshots": {s: snapshots[s] for s in symbols[:1]}, "next_page_token": "snapshots-2"},
            (SNAPSHOTS, "snapshots-2"): {"snapshots": {s: snapshots[s] for s in symbols[1:]}, "next_page_token": None},
        })
        normalized = reader.observe_option_chain("SPY", strike_price_gte=550, strike_price_lte=650, as_of=datetime(2026, 8, 24, 12, tzinfo=timezone.utc), **DATES)
        self.assertEqual(len(normalized.chain.contracts), 3)
        self.assertEqual(len(normalized.source_refs), 3)
        self.assertEqual(len(transport.calls), 5)


if __name__ == "__main__":
    unittest.main()
