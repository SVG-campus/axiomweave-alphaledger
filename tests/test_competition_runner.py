from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from alphaledger.alpaca_readonly import PaperReadinessReceipt, ReadOnlyResponse
from alphaledger.competition_runner import (
    CompetitionAgent,
    CompetitionState,
    CompetitionStateStore,
    ExclusiveProcessLock,
    ManagedPlan,
    ReceiptJournal,
    RuntimeMode,
    pinned_account_hash,
    validate_managed_positions,
)
from alphaledger.options import DefinedRiskOptionsProposer
from alphaledger.options_demo import build_options_chain


ACCOUNT_HASH = pinned_account_hash("private-paper-account")


def _readiness(*, positions: int = 0, orders: int = 0) -> PaperReadinessReceipt:
    return PaperReadinessReceipt(
        observed_at="2026-08-31T13:25:00+00:00",
        ready_for_defined_risk_observation=positions == 0 and orders == 0,
        reasons=("passed",) if positions == 0 and orders == 0 else ("managed exposure",),
        account_status="ACTIVE",
        equity=100000.0,
        cash=100000.0,
        buying_power=200000.0,
        daily_pnl=0.0,
        options_approved_level=3,
        options_trading_level=3,
        positions_count=positions,
        open_orders_count=orders,
        trading_blocked=False,
        request_ids=("redacted",),
        source_refs=("account", "positions", "orders"),
        account_ref_sha256=ACCOUNT_HASH,
    )


def _response(payload):
    return ReadOnlyResponse(
        endpoint="https://paper-api.alpaca.markets/v2/positions",
        observed_at="2026-09-03T19:45:00+00:00",
        request_id="redacted",
        payload_sha256="a" * 64,
        record_count=len(payload),
        payload=payload,
    )


class FakeObserver:
    def __init__(
        self,
        readiness: PaperReadinessReceipt,
        positions,
        chain=None,
        open_orders=None,
        bars_response=None,
    ) -> None:
        self.readiness = readiness
        self.positions = positions
        self.chain = chain or build_options_chain()
        self.open_orders = open_orders or []
        self.bars_response = bars_response

    def reconcile(self):
        return self.readiness

    def read_positions(self):
        return _response(self.positions)

    def read_open_orders(self):
        response = _response(self.open_orders)
        return ReadOnlyResponse(
            endpoint="https://paper-api.alpaca.markets/v2/orders",
            observed_at=response.observed_at,
            request_id=response.request_id,
            payload_sha256=response.payload_sha256,
            record_count=response.record_count,
            payload=response.payload,
        )

    def observe_option_chain(self, *args, **kwargs):
        return SimpleNamespace(chain=self.chain)

    def read_stock_bars(self, *args, **kwargs):
        if self.bars_response is None:
            raise AssertionError("Stock bars are not needed in this test")
        return self.bars_response


def _bull_bars_response() -> ReadOnlyResponse:
    start = datetime(2026, 8, 31, 13, 30, tzinfo=timezone.utc)
    rows = []
    for index in range(30):
        close = 600.0 + 0.35 * index
        opened = close - 0.12
        rows.append(
            {
                "t": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
                "o": opened,
                "h": close + 0.10,
                "l": opened - 0.10,
                "c": close,
                "v": 1000 + index,
                "vw": (opened + close) / 2,
            }
        )
    return ReadOnlyResponse(
        endpoint="https://data.alpaca.markets/v2/stocks/bars",
        observed_at="2026-08-31T15:56:00+00:00",
        request_id="redacted-bars",
        payload_sha256="b" * 64,
        record_count=len(rows),
        payload={"bars": {"SPY": rows}, "next_page_token": None},
    )


class CompetitionRunnerTests(unittest.TestCase):
    def _paths(self, root: Path):
        return (
            CompetitionStateStore(root / "state.json"),
            ReceiptJournal(root / "receipts.jsonl"),
            root / "writer.lock",
        )

    def test_dry_run_has_no_broker_adapter_and_only_reports_clock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            agent = CompetitionAgent(
                mode=RuntimeMode.DRY_RUN,
                state_store=store,
                journal=journal,
                lock_path=lock,
                writer_id="test-writer",
            )
            receipt = agent.run_once(datetime(2026, 8, 31, 13, 29, tzinfo=timezone.utc))
            self.assertEqual(receipt.action, "clock_only")
            self.assertEqual(receipt.phase, "pre_window")
            self.assertEqual(len(receipt.evidence_hash), 64)

    def test_paper_mode_requires_executor_and_pinned_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            with self.assertRaisesRegex(ValueError, "executor"):
                CompetitionAgent(
                    mode=RuntimeMode.PAPER,
                    state_store=store,
                    journal=journal,
                    lock_path=lock,
                    writer_id="test-writer",
                    observer=FakeObserver(_readiness(), []),
                )

    def test_os_lock_refuses_a_second_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "writer.lock"
            with ExclusiveProcessLock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "Another"):
                    with ExclusiveProcessLock(lock_path):
                        pass

    def test_state_round_trip_and_writer_identity_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CompetitionStateStore(Path(directory) / "state.json")
            state = CompetitionState(
                writer_id="primary",
                account_gate_passed=True,
                account_ref_sha256=ACCOUNT_HASH,
                entries_by_session={"2026-08-31": 1},
            )
            store.save(state)
            loaded = store.load()
            self.assertEqual(loaded.writer_id, "primary")
            self.assertEqual(loaded.entries_by_session["2026-08-31"], 1)

    def test_account_identity_mismatch_halts_before_market_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            agent = CompetitionAgent(
                mode=RuntimeMode.OBSERVE,
                state_store=store,
                journal=journal,
                lock_path=lock,
                writer_id="test-writer",
                observer=FakeObserver(_readiness(), []),
                expected_account_ref_sha256="b" * 64,
            )
            receipt = agent.run_once(datetime(2026, 8, 31, 13, 25, tzinfo=timezone.utc))
            self.assertEqual(receipt.action, "halted")
            self.assertIn("pinned", receipt.reasons[0])

    def test_managed_position_manifest_requires_exact_legs_and_quantities(self) -> None:
        thesis = DefinedRiskOptionsProposer().propose(build_options_chain())
        plan = ManagedPlan(
            thesis=thesis.to_dict(),
            status="open",
            opened_at="2026-08-31T15:00:00+00:00",
            entry_debit_per_share=thesis.net_debit_per_share,
            client_order_id="aw-open-example123",
        )
        state = CompetitionState(plans=[plan])
        positions = [
            {"symbol": thesis.legs[0].contract.symbol, "qty": "1"},
            {"symbol": thesis.legs[1].contract.symbol, "qty": "-1"},
        ]
        self.assertEqual(validate_managed_positions(_response(positions), state), ())
        positions[1]["qty"] = "-2"
        self.assertTrue(validate_managed_positions(_response(positions), state))

    def test_force_flat_in_observe_mode_never_submits_an_order(self) -> None:
        thesis = DefinedRiskOptionsProposer().propose(build_options_chain())
        plan = ManagedPlan(
            thesis=thesis.to_dict(),
            status="open",
            opened_at="2026-08-31T15:00:00+00:00",
            entry_debit_per_share=thesis.net_debit_per_share,
            client_order_id="aw-open-example123",
        )
        positions = [
            {"symbol": thesis.legs[0].contract.symbol, "qty": "1"},
            {"symbol": thesis.legs[1].contract.symbol, "qty": "-1"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            store.save(
                CompetitionState(
                    writer_id="test-writer",
                    account_gate_passed=True,
                    account_ref_sha256=ACCOUNT_HASH,
                    plans=[plan],
                )
            )
            agent = CompetitionAgent(
                mode=RuntimeMode.OBSERVE,
                state_store=store,
                journal=journal,
                lock_path=lock,
                writer_id="test-writer",
                observer=FakeObserver(_readiness(positions=2), positions),
                expected_account_ref_sha256=ACCOUNT_HASH,
            )
            receipt = agent.run_once(datetime(2026, 9, 3, 19, 45, tzinfo=timezone.utc))
            self.assertEqual(receipt.action, "would_close")
            self.assertIn("competition_force_flat", receipt.reasons[0])

    def test_stale_pending_order_is_canceled_by_exact_owned_id(self) -> None:
        class FakeExecutor:
            def __init__(self) -> None:
                self.canceled = []

            def get_by_client_order_id(self, client_order_id):
                return SimpleNamespace(status="accepted")

            def cancel_order(self, order_id, *, client_order_id):
                self.canceled.append((order_id, client_order_id))
                return SimpleNamespace(status="accepted")

        thesis = DefinedRiskOptionsProposer().propose(build_options_chain())
        now = datetime(2026, 8, 31, 13, 25, tzinfo=timezone.utc)
        client_id = "aw-open-0-example123"
        plan = ManagedPlan(
            thesis=thesis.to_dict(),
            status="pending_open",
            opened_at=(now - timedelta(minutes=4)).isoformat(),
            submitted_at=(now - timedelta(minutes=4)).isoformat(),
            entry_debit_per_share=thesis.net_debit_per_share,
            client_order_id=client_id,
        )
        executor = FakeExecutor()
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            store.save(
                CompetitionState(
                    writer_id="test-writer",
                    account_gate_passed=True,
                    account_ref_sha256=ACCOUNT_HASH,
                    plans=[plan],
                )
            )
            observer = FakeObserver(
                _readiness(orders=1),
                [],
                open_orders=[{"id": "private-order-id", "client_order_id": client_id}],
            )
            agent = CompetitionAgent(
                mode=RuntimeMode.PAPER,
                state_store=store,
                journal=journal,
                lock_path=lock,
                writer_id="test-writer",
                observer=observer,
                executor=executor,
                expected_account_ref_sha256=ACCOUNT_HASH,
            )
            agent.run_once(now)
            self.assertEqual(executor.canceled, [("private-order-id", client_id)])

    def test_observe_mode_runs_full_bullish_entry_path_without_submission(self) -> None:
        now = datetime(2026, 8, 31, 15, 56, tzinfo=timezone.utc)
        base_chain = build_options_chain()
        chain = replace(
            base_chain,
            underlying_price=600.0,
            observed_at=now.isoformat(),
            source_refs=("stock-hash", "contracts-hash", "chain-hash"),
            underlying_data_age_seconds=5,
            underlying_feed="iex",
            options_feed="indicative",
        )
        with tempfile.TemporaryDirectory() as directory:
            store, journal, lock = self._paths(Path(directory))
            agent = CompetitionAgent(
                mode=RuntimeMode.OBSERVE,
                state_store=store,
                journal=journal,
                lock_path=lock,
                writer_id="test-writer",
                observer=FakeObserver(
                    _readiness(),
                    [],
                    chain=chain,
                    bars_response=_bull_bars_response(),
                ),
                expected_account_ref_sha256=ACCOUNT_HASH,
            )
            receipt = agent.run_once(now)
            self.assertEqual(receipt.action, "would_open")
            self.assertEqual(receipt.open_plans, 0)
            self.assertEqual(store.load().entries_by_session, {})


if __name__ == "__main__":
    unittest.main()
