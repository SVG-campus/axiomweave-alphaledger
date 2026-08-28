from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from .alpaca_cli_options import AlpacaCliOptionsPaperExecutor, PaperOrderReceipt
from .alpaca_readonly import AlpacaReadOnlyObserver, PaperReadinessReceipt, ReadOnlyResponse
from .competition import (
    CompetitionPhase,
    CompetitionRiskPolicy,
    CompetitionWindow,
    compute_momentum_signal,
    evaluate_clean_competition_account,
    evaluate_entry_gate,
    evaluate_exit,
    natural_close_credit,
    normalize_stock_bars,
)
from .models import AccountState
from .options import (
    DefinedRiskOptionsProposer,
    DeterministicOptionsRiskGate,
    OptionLeg,
    OptionQuote,
    OptionsRiskPolicy,
    OptionsThesis,
    TemplateOptionsAdvisory,
)


class RuntimeMode(str, Enum):
    DRY_RUN = "dry-run"
    OBSERVE = "observe"
    PAPER = "paper"


class CompetitionObserver(Protocol):
    def reconcile(self) -> PaperReadinessReceipt: ...

    def read_positions(self) -> ReadOnlyResponse: ...

    def read_open_orders(self) -> ReadOnlyResponse: ...

    def read_stock_bars(
        self,
        underlying_symbol: str,
        *,
        start: str,
        end: str,
        timeframe: str = "5Min",
        feed: str = "iex",
        limit: int = 1000,
    ) -> ReadOnlyResponse: ...

    def observe_option_chain(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str,
        expiration_date_lte: str,
        strike_price_gte: float,
        strike_price_lte: float,
        option_type: str = "call",
        stock_feed: str = "iex",
        options_feed: str = "indicative",
        as_of: datetime | None = None,
    ) -> Any: ...


class PaperExecutor(Protocol):
    def submit_open(self, thesis: OptionsThesis) -> PaperOrderReceipt: ...

    def submit_close(
        self,
        thesis: OptionsThesis,
        *,
        limit_credit_per_share: float,
        attempt: int = 0,
    ) -> PaperOrderReceipt: ...

    def get_by_client_order_id(self, client_order_id: str) -> PaperOrderReceipt: ...

    def cancel_order(self, order_id: str, *, client_order_id: str) -> PaperOrderReceipt: ...


@dataclass
class ManagedPlan:
    thesis: dict[str, Any]
    status: str
    opened_at: str
    entry_debit_per_share: float
    client_order_id: str
    submitted_at: str = ""
    close_reason: str = ""
    last_status: str = ""
    close_attempt: int = 0

    def typed_thesis(self) -> OptionsThesis:
        return _thesis_from_dict(self.thesis)


@dataclass
class CompetitionState:
    schema_version: int = 1
    writer_id: str = ""
    account_gate_passed: bool = False
    account_ref_sha256: str = ""
    baseline_verified_at: str = ""
    entries_by_session: dict[str, int] = field(default_factory=dict)
    plans: list[ManagedPlan] = field(default_factory=list)
    final_equity: float | None = None
    final_snapshot_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "writer_id": self.writer_id,
            "account_gate_passed": self.account_gate_passed,
            "account_ref_sha256": self.account_ref_sha256,
            "baseline_verified_at": self.baseline_verified_at,
            "entries_by_session": dict(self.entries_by_session),
            "plans": [asdict(plan) for plan in self.plans],
            "final_equity": self.final_equity,
            "final_snapshot_at": self.final_snapshot_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CompetitionState":
        if int(payload.get("schema_version", 0)) != 1:
            raise RuntimeError("Competition state schema is unsupported")
        plans_payload = payload.get("plans", [])
        if not isinstance(plans_payload, list):
            raise RuntimeError("Competition state plans must be a list")
        plans = [ManagedPlan(**dict(item)) for item in plans_payload]
        entries = payload.get("entries_by_session", {})
        if not isinstance(entries, dict):
            raise RuntimeError("Competition state session counts must be an object")
        return cls(
            schema_version=1,
            writer_id=str(payload.get("writer_id", "")),
            account_gate_passed=bool(payload.get("account_gate_passed", False)),
            account_ref_sha256=str(payload.get("account_ref_sha256", "")),
            baseline_verified_at=str(payload.get("baseline_verified_at", "")),
            entries_by_session={str(key): int(value) for key, value in entries.items()},
            plans=plans,
            final_equity=(
                None if payload.get("final_equity") is None else float(payload["final_equity"])
            ),
            final_snapshot_at=str(payload.get("final_snapshot_at", "")),
        )


class CompetitionStateStore:
    """Atomic local state. Runtime data belongs under an ignored var directory."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> CompetitionState:
        if not self.path.exists():
            return CompetitionState()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Competition state must be a JSON object")
        return CompetitionState.from_dict(payload)

    def save(self, state: CompetitionState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


class ExclusiveProcessLock:
    """OS-released writer lock; a crash cannot leave a permanent stale lease."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: Any = None

    def __enter__(self) -> "ExclusiveProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self._handle.write(b"0")
            self._handle.flush()
        self._handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise RuntimeError("Another AlphaLedger competition writer is active") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


class ReceiptJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: Mapping[str, Any]) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        previous_hash = "GENESIS"
        if self.path.exists():
            lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
            if lines:
                last = json.loads(lines[-1])
                previous_hash = str(last["entry_hash"])
        stable = {"previous_hash": previous_hash, "event": dict(event)}
        canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        record = {**stable, "entry_hash": entry_hash}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return entry_hash


@dataclass(frozen=True)
class CompetitionTickReceipt:
    observed_at: str
    mode: str
    phase: str
    action: str
    reasons: tuple[str, ...]
    equity: float | None
    open_plans: int
    entries_this_session: int
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompetitionAgent:
    """One deterministic controller. AI may veto elsewhere; it cannot call this executor."""

    TERMINAL_ORDER_STATUSES = {"canceled", "expired", "rejected", "replaced", "stopped"}

    def __init__(
        self,
        *,
        mode: RuntimeMode,
        state_store: CompetitionStateStore,
        journal: ReceiptJournal,
        lock_path: Path,
        writer_id: str,
        observer: CompetitionObserver | None = None,
        executor: PaperExecutor | None = None,
        expected_account_ref_sha256: str = "",
        window: CompetitionWindow | None = None,
        risk_policy: CompetitionRiskPolicy | None = None,
    ) -> None:
        if not writer_id or len(writer_id) > 80:
            raise ValueError("A bounded exclusive writer ID is required")
        if mode is RuntimeMode.DRY_RUN and (observer is not None or executor is not None):
            raise ValueError("Dry-run mode must not receive broker adapters")
        if mode in {RuntimeMode.OBSERVE, RuntimeMode.PAPER} and observer is None:
            raise ValueError("Observe and paper modes require a read-only observer")
        if mode is RuntimeMode.PAPER and executor is None:
            raise ValueError("Paper mode requires the locked official-CLI executor")
        if mode is not RuntimeMode.PAPER and executor is not None:
            raise ValueError("A mutating executor is permitted only in paper mode")
        if expected_account_ref_sha256 and not _is_sha256(expected_account_ref_sha256):
            raise ValueError("Expected account reference must be a SHA-256 digest")
        if mode is RuntimeMode.PAPER and not expected_account_ref_sha256:
            raise ValueError("Paper mode requires a pinned account reference")
        self.mode = mode
        self.state_store = state_store
        self.journal = journal
        self.lock_path = lock_path
        self.writer_id = writer_id
        self.observer = observer
        self.executor = executor
        self.expected_account_ref_sha256 = expected_account_ref_sha256
        self.window = window or CompetitionWindow()
        self.risk_policy = risk_policy or CompetitionRiskPolicy()

    def run_once(self, instant: datetime | None = None) -> CompetitionTickReceipt:
        now = _aware_utc(instant or datetime.now(timezone.utc))
        with ExclusiveProcessLock(self.lock_path):
            state = self.state_store.load()
            if state.writer_id and state.writer_id != self.writer_id:
                return self._finish(
                    state,
                    now,
                    "halted",
                    ("Persisted state belongs to a different exclusive writer.",),
                    None,
                )
            state.writer_id = self.writer_id
            phase = self.window.phase_at(now)
            if self.mode is RuntimeMode.DRY_RUN:
                return self._finish(
                    state,
                    now,
                    "clock_only",
                    ("Dry-run mode has no broker adapter and cannot submit orders.",),
                    None,
                )

            assert self.observer is not None
            try:
                readiness = self.observer.reconcile()
            except Exception as exc:  # fail-closed boundary; journal only exception type
                return self._finish(
                    state,
                    now,
                    "halted",
                    (f"Read-only reconciliation failed: {type(exc).__name__}.",),
                    None,
                )

            if self.expected_account_ref_sha256 and (
                readiness.account_ref_sha256 != self.expected_account_ref_sha256
            ):
                return self._finish(
                    state,
                    now,
                    "halted",
                    ("Observed paper account does not match the pinned competition account.",),
                    readiness.equity,
                )
            if state.account_ref_sha256 and state.account_ref_sha256 != readiness.account_ref_sha256:
                return self._finish(
                    state,
                    now,
                    "halted",
                    ("Paper account identity changed after baseline verification.",),
                    readiness.equity,
                )
            if not state.account_gate_passed:
                account_gate = evaluate_clean_competition_account(readiness, self.risk_policy)
                if not account_gate.approved:
                    return self._finish(
                        state,
                        now,
                        "halted",
                        account_gate.reasons,
                        readiness.equity,
                    )
                state.account_gate_passed = True
                state.account_ref_sha256 = readiness.account_ref_sha256
                state.baseline_verified_at = now.isoformat()

            health_reasons = _account_health_reasons(readiness)
            if health_reasons:
                return self._finish(state, now, "halted", health_reasons, readiness.equity)

            pending_errors = self._reconcile_pending(state, now)
            if pending_errors:
                return self._finish(state, now, "halted", pending_errors, readiness.equity)

            try:
                positions = self.observer.read_positions()
                ownership = validate_managed_positions(positions, state)
            except Exception as exc:
                return self._finish(
                    state,
                    now,
                    "halted",
                    (f"Managed-position reconciliation failed: {type(exc).__name__}.",),
                    readiness.equity,
                )
            if ownership:
                return self._finish(state, now, "halted", ownership, readiness.equity)

            if phase is CompetitionPhase.COMPLETE:
                state.final_equity = readiness.equity
                state.final_snapshot_at = now.isoformat()
                return self._finish(
                    state,
                    now,
                    "complete",
                    (
                        "Window-end observation recorded; organizer scoring basis is portfolio "
                        "total equity as of EOD Thursday.",
                    ),
                    readiness.equity,
                )

            exit_action = self._manage_exits(state, now)
            if exit_action is not None:
                action, reasons = exit_action
                return self._finish(state, now, action, reasons, readiness.equity)

            if phase is not CompetitionPhase.ENTRY_ALLOWED:
                reasons = [f"Competition clock is {phase.value}; no new entry is permitted."]
                if phase is CompetitionPhase.FORCE_FLAT and state.plans:
                    reasons.append("Residual managed exposure remains after the tradable force-flat window.")
                return self._finish(state, now, "observe", tuple(reasons), readiness.equity)

            if readiness.positions_count or readiness.open_orders_count:
                return self._finish(
                    state,
                    now,
                    "observe",
                    ("Reconciled exposure or orders block a new entry.",),
                    readiness.equity,
                )

            return self._evaluate_entry(state, readiness, now)

    def _reconcile_pending(
        self,
        state: CompetitionState,
        now: datetime,
    ) -> tuple[str, ...]:
        if self.mode is not RuntimeMode.PAPER:
            return ()
        assert self.executor is not None
        retained: list[ManagedPlan] = []
        for plan in state.plans:
            if plan.status not in {"pending_open", "pending_close"}:
                retained.append(plan)
                continue
            try:
                receipt = self.executor.get_by_client_order_id(plan.client_order_id)
            except Exception as exc:
                return (f"Pending order reconciliation failed: {type(exc).__name__}.",)
            status = receipt.status.lower()
            plan.last_status = status
            if status == "filled":
                if plan.status == "pending_open":
                    plan.status = "open"
                    retained.append(plan)
                continue
            if status in self.TERMINAL_ORDER_STATUSES:
                if plan.status == "pending_close":
                    plan.status = "open"
                    plan.client_order_id = ""
                    plan.close_attempt += 1
                    retained.append(plan)
                continue
            submitted = datetime.fromisoformat(plan.submitted_at or plan.opened_at)
            if submitted.tzinfo is None:
                return ("Persisted pending-order timestamp has no timezone.",)
            if now - submitted.astimezone(timezone.utc) >= timedelta(minutes=3):
                try:
                    assert self.observer is not None
                    open_orders = self.observer.read_open_orders()
                    order_id = _find_owned_open_order_id(open_orders, plan.client_order_id)
                    cancel_receipt = self.executor.cancel_order(
                        order_id,
                        client_order_id=plan.client_order_id,
                    )
                    plan.last_status = cancel_receipt.status
                except Exception as exc:
                    return (f"Stale pending-order cancellation failed: {type(exc).__name__}.",)
            retained.append(plan)
        state.plans = retained
        return ()

    def _manage_exits(
        self,
        state: CompetitionState,
        now: datetime,
    ) -> tuple[str, tuple[str, ...]] | None:
        tradable = _market_is_open(now, self.window)
        for plan in state.plans:
            if plan.status != "open":
                continue
            thesis = plan.typed_thesis()
            try:
                long_contract, short_contract = thesis.legs
                expiration = long_contract.contract.expiration_date
                option_type = long_contract.contract.option_type
                strikes = [leg.contract.strike_price for leg in thesis.legs]
                assert self.observer is not None
                normalized = self.observer.observe_option_chain(
                    thesis.underlying_symbol,
                    expiration_date_gte=expiration,
                    expiration_date_lte=expiration,
                    strike_price_gte=min(strikes) - 0.01,
                    strike_price_lte=max(strikes) + 0.01,
                    option_type=option_type,
                    stock_feed="iex",
                    options_feed="indicative",
                    as_of=now,
                )
                quotes = {
                    quote.symbol: {
                        "bid_price": quote.bid_price,
                        "ask_price": quote.ask_price,
                    }
                    for quote in normalized.chain.contracts
                }
                close_credit = natural_close_credit(
                    quotes,
                    long_contract.contract.symbol,
                    short_contract.contract.symbol,
                )
                exit_decision = evaluate_exit(
                    entry_debit_per_share=plan.entry_debit_per_share,
                    current_close_credit_per_share=close_credit,
                    opened_at=datetime.fromisoformat(plan.opened_at),
                    instant=now,
                    window=self.window,
                    policy=self.risk_policy,
                )
            except Exception as exc:
                return "observe", (f"Exit evidence failed closed: {type(exc).__name__}.",)
            if not exit_decision.should_close:
                continue
            if not tradable:
                return "observe", (
                    f"Exit reason {exit_decision.reason} is active, but the options market is closed.",
                )
            if self.mode is RuntimeMode.OBSERVE:
                return "would_close", (
                    f"Observe-only exit: {exit_decision.reason}; no order was submitted.",
                )
            assert self.executor is not None
            aggressive_credit = max(0.01, close_credit)
            try:
                receipt = self.executor.submit_close(
                    thesis,
                    limit_credit_per_share=aggressive_credit,
                    attempt=plan.close_attempt,
                )
            except Exception as exc:
                return "halted", (f"Paper close submission failed: {type(exc).__name__}.",)
            plan.close_reason = exit_decision.reason
            plan.client_order_id = receipt.client_order_id
            plan.submitted_at = now.isoformat()
            plan.last_status = receipt.status
            if receipt.status.lower() == "filled":
                state.plans.remove(plan)
            else:
                plan.status = "pending_close"
            return "paper_close_submitted", (f"Exit reason: {exit_decision.reason}.",)
        return None

    def _evaluate_entry(
        self,
        state: CompetitionState,
        readiness: PaperReadinessReceipt,
        now: datetime,
    ) -> CompetitionTickReceipt:
        assert self.observer is not None
        start = (now - timedelta(days=4)).isoformat().replace("+00:00", "Z")
        end = now.isoformat().replace("+00:00", "Z")
        try:
            response = self.observer.read_stock_bars(
                "SPY",
                start=start,
                end=end,
                timeframe="5Min",
                feed="iex",
                limit=1000,
            )
            bars = normalize_stock_bars(response, "SPY")
            signal = compute_momentum_signal(
                bars,
                as_of=now,
                policy=self.risk_policy,
                source_refs=(f"{response.endpoint}#sha256={response.payload_sha256}",),
            )
        except Exception as exc:
            return self._finish(
                state,
                now,
                "abstain",
                (f"Momentum evidence failed closed: {type(exc).__name__}.",),
                readiness.equity,
            )

        # The event dates are in EDT (UTC-4); the window performs the authoritative session check.
        session_key = now.astimezone(timezone(timedelta(hours=-4))).date().isoformat()
        entry_gate = evaluate_entry_gate(
            instant=now,
            window=self.window,
            policy=self.risk_policy,
            signal=signal,
            current_equity=readiness.equity,
            daily_pnl=readiness.daily_pnl,
            open_plans=len(state.plans),
            aggregate_open_max_loss=sum(
                float(plan.thesis.get("max_loss_dollars", 0.0)) for plan in state.plans
            ),
            entries_this_session=state.entries_by_session.get(session_key, 0),
        )
        if not entry_gate.approved:
            return self._finish(
                state,
                now,
                "abstain",
                entry_gate.reasons,
                readiness.equity,
            )

        option_type = "call" if signal.direction == "bullish" else "put"
        first_expiry = (now.date() + timedelta(days=7)).isoformat()
        last_expiry = (now.date() + timedelta(days=18)).isoformat()
        underlying = bars[-1].close
        try:
            normalized = self.observer.observe_option_chain(
                "SPY",
                expiration_date_gte=first_expiry,
                expiration_date_lte=last_expiry,
                strike_price_gte=round(underlying * 0.96, 2),
                strike_price_lte=round(underlying * 1.04, 2),
                option_type=option_type,
                stock_feed="iex",
                options_feed="indicative",
                as_of=now,
            )
            proposer = DefinedRiskOptionsProposer(
                direction=signal.direction,
                max_contracts=self.risk_policy.max_contracts_per_plan,
                max_loss_budget=self.risk_policy.max_loss_per_plan_usd,
            )
            thesis = proposer.propose(normalized.chain)
            advisory = TemplateOptionsAdvisory().analyze(thesis)
            options_policy = OptionsRiskPolicy(
                max_contracts=self.risk_policy.max_contracts_per_plan,
                max_loss_dollars=self.risk_policy.max_loss_per_plan_usd,
                max_net_debit_per_share=self.risk_policy.max_loss_per_plan_usd / 100.0,
                min_days_to_expiration=7,
                max_days_to_expiration=18,
                max_data_age_seconds=180,
                max_underlying_data_age_seconds=180,
                max_open_orders=0,
            )
            account = AccountState(
                equity=readiness.equity,
                cash=readiness.cash,
                buying_power=readiness.buying_power,
                daily_pnl=readiness.daily_pnl,
                positions={},
                open_orders=readiness.open_orders_count,
                broker_mode="paper",
            )
            risk = DeterministicOptionsRiskGate().evaluate(
                thesis,
                normalized.chain,
                account,
                options_policy,
                advisory,
            )
        except Exception as exc:
            return self._finish(
                state,
                now,
                "abstain",
                (f"Options evidence failed closed: {type(exc).__name__}.",),
                readiness.equity,
            )
        if not risk.approved:
            return self._finish(state, now, "abstain", risk.reasons, readiness.equity)

        if self.mode is RuntimeMode.OBSERVE:
            return self._finish(
                state,
                now,
                "would_open",
                (
                    f"Observe-only {thesis.strategy} passed every gate; no order was submitted.",
                ),
                readiness.equity,
            )

        assert self.executor is not None
        try:
            receipt = self.executor.submit_open(thesis)
        except Exception as exc:
            return self._finish(
                state,
                now,
                "halted",
                (f"Paper open submission failed: {type(exc).__name__}.",),
                readiness.equity,
            )
        state.entries_by_session[session_key] = state.entries_by_session.get(session_key, 0) + 1
        state.plans.append(
            ManagedPlan(
                thesis=thesis.to_dict(),
                status="open" if receipt.status.lower() == "filled" else "pending_open",
                opened_at=now.isoformat(),
                entry_debit_per_share=thesis.net_debit_per_share,
                client_order_id=receipt.client_order_id,
                submitted_at=now.isoformat(),
                last_status=receipt.status,
            )
        )
        return self._finish(
            state,
            now,
            "paper_open_submitted",
            (f"A bounded {thesis.strategy} was submitted through the official Alpaca CLI.",),
            readiness.equity,
        )

    def _finish(
        self,
        state: CompetitionState,
        now: datetime,
        action: str,
        reasons: tuple[str, ...],
        equity: float | None,
    ) -> CompetitionTickReceipt:
        self.state_store.save(state)
        session_key = now.astimezone(timezone(timedelta(hours=-4))).date().isoformat()
        bare = CompetitionTickReceipt(
            observed_at=now.isoformat(),
            mode=self.mode.value,
            phase=self.window.phase_at(now).value,
            action=action,
            reasons=reasons,
            equity=equity,
            open_plans=len(state.plans),
            entries_this_session=state.entries_by_session.get(session_key, 0),
        )
        evidence_hash = self.journal.append(bare.to_dict())
        return CompetitionTickReceipt(**{**bare.to_dict(), "evidence_hash": evidence_hash})


def validate_managed_positions(
    response: ReadOnlyResponse,
    state: CompetitionState,
) -> tuple[str, ...]:
    if not isinstance(response.payload, list):
        return ("Alpaca positions response is not a JSON array.",)
    expected: dict[str, float] = {}
    for plan in state.plans:
        if plan.status not in {"open", "pending_close"}:
            continue
        thesis = plan.typed_thesis()
        for leg in thesis.legs:
            sign = 1.0 if leg.side == "buy" else -1.0
            expected[leg.contract.symbol] = expected.get(leg.contract.symbol, 0.0) + (
                sign * thesis.quantity * leg.ratio_qty
            )
    actual: dict[str, float] = {}
    for item in response.payload:
        if not isinstance(item, dict):
            return ("An Alpaca position row is malformed.",)
        symbol = str(item.get("symbol", ""))
        try:
            quantity = float(item.get("qty"))
        except (TypeError, ValueError):
            return ("An Alpaca position quantity is malformed.",)
        if not symbol or not math.isfinite(quantity):
            return ("An Alpaca position row is incomplete.",)
        actual[symbol] = actual.get(symbol, 0.0) + quantity
    if actual != expected:
        return ("Observed positions do not exactly match the controller-owned option legs.",)
    return ()


def _find_owned_open_order_id(response: ReadOnlyResponse, client_order_id: str) -> str:
    if not isinstance(response.payload, list):
        raise RuntimeError("Alpaca open-orders response is not a JSON array")
    matches = [
        item
        for item in response.payload
        if isinstance(item, dict) and str(item.get("client_order_id", "")) == client_order_id
    ]
    if len(matches) != 1:
        raise RuntimeError("Pending order does not map to exactly one controller-owned open order")
    order_id = str(matches[0].get("id", ""))
    if not order_id:
        raise RuntimeError("Controller-owned open order has no broker identifier")
    return order_id


def pinned_account_hash(account_id: str) -> str:
    value = account_id.strip()
    if not value:
        raise ValueError("Paper account ID is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _account_health_reasons(receipt: PaperReadinessReceipt) -> tuple[str, ...]:
    reasons: list[str] = []
    if receipt.account_status != "ACTIVE":
        reasons.append("Paper account is not ACTIVE.")
    if receipt.trading_blocked:
        reasons.append("Paper account has an active trading restriction.")
    if receipt.options_approved_level < 3 or receipt.options_trading_level < 3:
        reasons.append("Paper account no longer has options level 3.")
    if not all(math.isfinite(value) for value in (receipt.equity, receipt.cash, receipt.buying_power)):
        reasons.append("Paper account capital is non-finite.")
    return tuple(reasons)


def _market_is_open(now: datetime, window: CompetitionWindow) -> bool:
    local = _aware_utc(now).astimezone(timezone(timedelta(hours=-4)))
    return (
        local.date() in window.eligible_sessions
        and window.market_open <= local.time() < window.market_close
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _thesis_from_dict(payload: Mapping[str, Any]) -> OptionsThesis:
    legs: list[OptionLeg] = []
    for raw_leg in payload.get("legs", []):
        if not isinstance(raw_leg, dict) or not isinstance(raw_leg.get("contract"), dict):
            raise RuntimeError("Persisted options leg is malformed")
        contract_payload = dict(raw_leg["contract"])
        contract_payload["source_refs"] = tuple(contract_payload.get("source_refs", ()))
        contract = OptionQuote(**contract_payload)
        legs.append(
            OptionLeg(
                contract=contract,
                side=str(raw_leg["side"]),  # type: ignore[arg-type]
                position_intent=str(raw_leg["position_intent"]),  # type: ignore[arg-type]
                ratio_qty=int(raw_leg.get("ratio_qty", 1)),
            )
        )
    return OptionsThesis(
        thesis_id=str(payload["thesis_id"]),
        created_at=str(payload["created_at"]),
        strategy=str(payload["strategy"]),  # type: ignore[arg-type]
        underlying_symbol=str(payload["underlying_symbol"]),
        quantity=int(payload["quantity"]),
        legs=tuple(legs),
        net_debit_per_share=float(payload["net_debit_per_share"]),
        spread_width=float(payload["spread_width"]),
        max_loss_dollars=float(payload["max_loss_dollars"]),
        max_profit_dollars=float(payload["max_profit_dollars"]),
        breakeven_price=(
            None if payload.get("breakeven_price") is None else float(payload["breakeven_price"])
        ),
        rationale=str(payload["rationale"]),
        evidence_refs=tuple(str(value) for value in payload.get("evidence_refs", ())),
        invalidation_condition=str(payload["invalidation_condition"]),
    )


def build_agent_from_environment(
    *,
    mode: RuntimeMode,
    root: Path,
    writer_id: str,
) -> CompetitionAgent:
    if mode is RuntimeMode.DRY_RUN:
        return CompetitionAgent(
            mode=mode,
            state_store=CompetitionStateStore(root / "var" / "competition-state.json"),
            journal=ReceiptJournal(root / "var" / "competition-receipts.jsonl"),
            lock_path=root / "var" / "competition-writer.lock",
            writer_id=writer_id,
        )
    from .alpaca_readonly import AlpacaCredentials

    credentials = AlpacaCredentials.from_environment()
    observer = AlpacaReadOnlyObserver(credentials)
    expected_id = os.environ.get("ALPHALEDGER_EXPECTED_ACCOUNT_ID", "")
    expected_hash = pinned_account_hash(expected_id) if expected_id else ""
    executor: AlpacaCliOptionsPaperExecutor | None = None
    if mode is RuntimeMode.PAPER:
        executor = AlpacaCliOptionsPaperExecutor(allow_submission=True)
    return CompetitionAgent(
        mode=mode,
        state_store=CompetitionStateStore(root / "var" / "competition-state.json"),
        journal=ReceiptJournal(root / "var" / "competition-receipts.jsonl"),
        lock_path=root / "var" / "competition-writer.lock",
        writer_id=writer_id,
        observer=observer,
        executor=executor,
        expected_account_ref_sha256=expected_hash,
    )
