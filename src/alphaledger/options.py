from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from .ledger import EvidenceLedger
from .models import AccountState, utc_now_iso


OptionType = Literal["call", "put"]
OptionSide = Literal["buy", "sell"]
PositionIntent = Literal["buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"]
OptionsStrategy = Literal["bull_call_debit_spread", "bear_put_debit_spread", "abstain"]
TradeDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    underlying_symbol: str
    expiration_date: str
    option_type: OptionType
    strike_price: float
    bid_price: float
    ask_price: float
    delta: float | None
    implied_volatility: float | None
    open_interest: int
    data_age_seconds: int
    source_refs: tuple[str, ...]

    @property
    def midpoint(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0

    @property
    def relative_spread(self) -> float:
        midpoint = self.midpoint
        return math.inf if midpoint <= 0 else (self.ask_price - self.bid_price) / midpoint

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionChainSnapshot:
    underlying_symbol: str
    underlying_price: float
    observed_at: str
    contracts: tuple[OptionQuote, ...]
    source_refs: tuple[str, ...]
    underlying_data_age_seconds: int = 0
    underlying_feed: str = "synthetic"
    options_feed: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionLeg:
    contract: OptionQuote
    side: OptionSide
    position_intent: PositionIntent
    ratio_qty: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "side": self.side,
            "position_intent": self.position_intent,
            "ratio_qty": self.ratio_qty,
        }

    def to_alpaca_dict(self) -> dict[str, str]:
        return {
            "symbol": self.contract.symbol,
            "ratio_qty": str(self.ratio_qty),
            "side": self.side,
            "position_intent": self.position_intent,
        }


@dataclass(frozen=True)
class OptionsThesis:
    thesis_id: str
    created_at: str
    strategy: OptionsStrategy
    underlying_symbol: str
    quantity: int
    legs: tuple[OptionLeg, ...]
    net_debit_per_share: float
    spread_width: float
    max_loss_dollars: float
    max_profit_dollars: float
    breakeven_price: float | None
    rationale: str
    evidence_refs: tuple[str, ...]
    invalidation_condition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "thesis_id": self.thesis_id,
            "created_at": self.created_at,
            "strategy": self.strategy,
            "underlying_symbol": self.underlying_symbol,
            "quantity": self.quantity,
            "legs": [leg.to_dict() for leg in self.legs],
            "net_debit_per_share": self.net_debit_per_share,
            "spread_width": self.spread_width,
            "max_loss_dollars": self.max_loss_dollars,
            "max_profit_dollars": self.max_profit_dollars,
            "breakeven_price": self.breakeven_price,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "invalidation_condition": self.invalidation_condition,
        }


@dataclass(frozen=True)
class AdvisoryMemo:
    summary: str
    falsifier: str
    concerns: tuple[str, ...]
    abstain_recommended: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OptionsAdvisoryAgent(Protocol):
    def analyze(self, thesis: OptionsThesis) -> AdvisoryMemo: ...


@dataclass(frozen=True)
class OptionsRiskPolicy:
    paper_only: bool = True
    allowed_underlyings: tuple[str, ...] = ("SPY",)
    max_contracts: int = 1
    max_loss_dollars: float = 25.0
    max_net_debit_per_share: float = 0.25
    min_days_to_expiration: int = 7
    max_days_to_expiration: int = 45
    max_data_age_seconds: int = 180
    max_underlying_data_age_seconds: int = 180
    allowed_underlying_feeds: tuple[str, ...] = ("synthetic", "iex", "sip", "delayed_sip")
    allowed_options_feeds: tuple[str, ...] = ("synthetic", "indicative", "opra")
    min_open_interest: int = 100
    max_relative_spread: float = 0.35
    min_evidence_refs: int = 3
    max_open_orders: int = 0
    require_greeks: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionsRiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    projected_max_loss: float
    projected_max_profit: float
    worst_relative_spread: float
    days_to_expiration: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionsExecutionReceipt:
    receipt_id: str
    created_at: str
    status: Literal["simulated_plan", "abstained"]
    thesis_id: str
    broker_mode: str
    order_payload: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernedOptionsResult:
    chain: OptionChainSnapshot
    thesis: OptionsThesis
    advisory: AdvisoryMemo
    risk: OptionsRiskDecision
    receipt: OptionsExecutionReceipt
    ledger_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.to_dict(),
            "thesis": self.thesis.to_dict(),
            "advisory": self.advisory.to_dict(),
            "risk": self.risk.to_dict(),
            "receipt": self.receipt.to_dict(),
            "ledger_hash": self.ledger_hash,
        }


class DefinedRiskOptionsProposer:
    """Builds a transparent directional debit spread; it never authorizes it."""

    def __init__(
        self,
        *,
        direction: TradeDirection = "bullish",
        max_contracts: int = 1,
        max_loss_budget: float = 25.0,
    ) -> None:
        if direction not in {"bullish", "bearish"}:
            raise ValueError("Direction must be bullish or bearish")
        if max_contracts < 1:
            raise ValueError("Maximum contracts must be positive")
        if max_loss_budget <= 0 or not math.isfinite(max_loss_budget):
            raise ValueError("Maximum loss budget must be finite and positive")
        self.direction = direction
        self.max_contracts = max_contracts
        self.max_loss_budget = max_loss_budget

    def propose(self, chain: OptionChainSnapshot) -> OptionsThesis:
        option_type: OptionType = "call" if self.direction == "bullish" else "put"
        eligible = [
            contract
            for contract in chain.contracts
            if contract.underlying_symbol == chain.underlying_symbol
            and contract.option_type == option_type
            and (
                contract.strike_price >= chain.underlying_price
                if self.direction == "bullish"
                else contract.strike_price <= chain.underlying_price
            )
        ]
        eligible.sort(
            key=lambda contract: (
                contract.expiration_date,
                contract.strike_price if self.direction == "bullish" else -contract.strike_price,
            )
        )

        selected: tuple[OptionQuote, OptionQuote] | None = None
        for long_contract in eligible:
            shorts = [
                contract
                for contract in eligible
                if contract.expiration_date == long_contract.expiration_date
                and (
                    contract.strike_price > long_contract.strike_price
                    if self.direction == "bullish"
                    else contract.strike_price < long_contract.strike_price
                )
            ]
            if shorts:
                selected = (long_contract, shorts[0])
                break

        if selected is None:
            return self._abstention(
                chain,
                f"No same-expiration defined-risk {option_type} spread could be formed.",
            )

        long_contract, short_contract = selected
        net_debit = round(long_contract.ask_price - short_contract.bid_price, 4)
        width = round(abs(short_contract.strike_price - long_contract.strike_price), 4)
        loss_per_contract = max(0.0, net_debit) * 100.0
        quantity = (
            max(1, min(self.max_contracts, int(self.max_loss_budget // loss_per_contract)))
            if loss_per_contract > 0
            else 1
        )
        max_loss = round(loss_per_contract * quantity, 2)
        max_profit = round(max(0.0, width - net_debit) * 100.0 * quantity, 2)
        breakeven = (
            round(
                long_contract.strike_price + net_debit
                if self.direction == "bullish"
                else long_contract.strike_price - net_debit,
                4,
            )
            if net_debit > 0
            else None
        )
        legs = (
            OptionLeg(long_contract, "buy", "buy_to_open"),
            OptionLeg(short_contract, "sell", "sell_to_open"),
        )
        evidence_refs = tuple(
            dict.fromkeys(
                [
                    *chain.source_refs,
                    *long_contract.source_refs,
                    *short_contract.source_refs,
                ]
            )
        )
        stable = {
            "chain": chain.to_dict(),
            "strategy": (
                "bull_call_debit_spread"
                if self.direction == "bullish"
                else "bear_put_debit_spread"
            ),
            "legs": [leg.to_alpaca_dict() for leg in legs],
            "quantity": quantity,
        }
        thesis_id = "options-" + hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]
        return OptionsThesis(
            thesis_id=thesis_id,
            created_at=utc_now_iso(),
            strategy=(
                "bull_call_debit_spread"
                if self.direction == "bullish"
                else "bear_put_debit_spread"
            ),
            underlying_symbol=chain.underlying_symbol,
            quantity=quantity,
            legs=legs,
            net_debit_per_share=net_debit,
            spread_width=width,
            max_loss_dollars=max_loss,
            max_profit_dollars=max_profit,
            breakeven_price=breakeven,
            rationale=(
                f"Construct the nearest same-expiration {option_type} debit spread around the underlying. "
                "The maximum loss is the debit paid and is known before any order plan exists."
            ),
            evidence_refs=evidence_refs,
            invalidation_condition=(
                "Abstain if quotes or Greeks are missing or stale, liquidity widens, expiration or leg "
                "structure diverges, maximum loss exceeds policy, or the advisory critic recommends abstention."
            ),
        )

    def _abstention(self, chain: OptionChainSnapshot, reason: str) -> OptionsThesis:
        stable = json.dumps(chain.to_dict(), sort_keys=True, separators=(",", ":"))
        return OptionsThesis(
            thesis_id="options-abstain-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:12],
            created_at=utc_now_iso(),
            strategy="abstain",
            underlying_symbol=chain.underlying_symbol,
            quantity=0,
            legs=(),
            net_debit_per_share=0.0,
            spread_width=0.0,
            max_loss_dollars=0.0,
            max_profit_dollars=0.0,
            breakeven_price=None,
            rationale=reason,
            evidence_refs=chain.source_refs,
            invalidation_condition="Remain in cash until a complete defined-risk structure is available.",
        )


class TemplateOptionsAdvisory:
    """Deterministic zero-cost baseline for the optional structured model lane."""

    def analyze(self, thesis: OptionsThesis) -> AdvisoryMemo:
        abstain = thesis.strategy == "abstain"
        return AdvisoryMemo(
            summary=(
                "The candidate is a capped-loss vertical spread; policy must still verify quotes, "
                "liquidity, expiration, evidence, and account state."
                if not abstain
                else "No complete defined-risk candidate was available."
            ),
            falsifier=thesis.invalidation_condition,
            concerns=(
                "Paper fills can differ from displayed option quotes.",
                "Greeks and implied volatility may be absent for some contracts.",
            ),
            abstain_recommended=abstain,
            source="deterministic_template",
        )


class UnavailableOptionsAdvisory:
    """Fail-closed adapter used when an optional model lane cannot run."""

    def analyze(self, thesis: OptionsThesis) -> AdvisoryMemo:
        return AdvisoryMemo(
            summary="The optional AI advisory lane was unavailable; policy fails closed.",
            falsifier=thesis.invalidation_condition,
            concerns=("No structured advisory receipt was produced.",),
            abstain_recommended=True,
            source="model_unavailable",
        )


class DeterministicOptionsRiskGate:
    """Fail-closed options policy; a model may veto but can never authorize."""

    def evaluate(
        self,
        thesis: OptionsThesis,
        chain: OptionChainSnapshot,
        account: AccountState,
        policy: OptionsRiskPolicy,
        advisory: AdvisoryMemo,
    ) -> OptionsRiskDecision:
        reasons: list[str] = []
        worst_relative_spread = 0.0
        days_to_expiration: int | None = None
        projected_net_debit = thesis.net_debit_per_share
        projected_spread_width = thesis.spread_width
        projected_max_loss = thesis.max_loss_dollars
        projected_max_profit = thesis.max_profit_dollars

        if not policy.paper_only:
            reasons.append("Policy is not locked to paper-only mode.")
        if account.broker_mode not in {"simulation", "paper"}:
            reasons.append("Broker mode is neither simulation nor paper.")
        if chain.underlying_symbol not in policy.allowed_underlyings:
            reasons.append("Underlying is outside the frozen allowlist.")
        if chain.underlying_price <= 0 or not math.isfinite(chain.underlying_price):
            reasons.append("Underlying price is invalid.")
        if chain.underlying_data_age_seconds < 0:
            reasons.append("Underlying evidence age is invalid.")
        elif chain.underlying_data_age_seconds > policy.max_underlying_data_age_seconds:
            reasons.append("Underlying evidence is stale.")
        if chain.underlying_feed not in policy.allowed_underlying_feeds:
            reasons.append("Underlying feed is outside the frozen allowlist.")
        if chain.options_feed not in policy.allowed_options_feeds:
            reasons.append("Options feed is outside the frozen allowlist.")
        if thesis.strategy == "abstain":
            reasons.append("Proposer selected the abstention baseline.")
        if thesis.strategy not in {
            "bull_call_debit_spread",
            "bear_put_debit_spread",
            "abstain",
        }:
            reasons.append("Unsupported options strategy.")
        if thesis.quantity < 1 or thesis.quantity > policy.max_contracts:
            reasons.append("Contract quantity violates the frozen contract budget.")
        if len(thesis.legs) != 2:
            reasons.append("Defined-risk vertical requires exactly two legs.")
        if len(thesis.evidence_refs) < policy.min_evidence_refs:
            reasons.append("Evidence manifest is incomplete.")
        if len(set(thesis.evidence_refs)) != len(thesis.evidence_refs):
            reasons.append("Evidence manifest contains duplicate references.")
        if account.open_orders > policy.max_open_orders:
            reasons.append("Unreconciled open orders block a new options plan.")
        if account.equity <= 0:
            reasons.append("Account equity is invalid.")
        elif max(0.0, -account.daily_pnl / account.equity) >= 0.015:
            reasons.append("Daily-loss stop is active.")
        if advisory.abstain_recommended:
            reasons.append("Advisory critic recommended abstention.")

        if len(thesis.legs) == 2:
            long_leg, short_leg = thesis.legs
            contracts = (long_leg.contract, short_leg.contract)
            if long_leg.side != "buy" or long_leg.position_intent != "buy_to_open":
                reasons.append("Long leg is not buy-to-open.")
            if short_leg.side != "sell" or short_leg.position_intent != "sell_to_open":
                reasons.append("Short leg is not sell-to-open.")
            if long_leg.ratio_qty != 1 or short_leg.ratio_qty != 1:
                reasons.append("Only one-to-one vertical spreads are allowed.")
            if any(contract.underlying_symbol != thesis.underlying_symbol for contract in contracts):
                reasons.append("Option legs do not match the thesis underlying.")
            expected_type = "call" if thesis.strategy == "bull_call_debit_spread" else "put"
            if any(contract.option_type != expected_type for contract in contracts):
                reasons.append(f"{thesis.strategy} requires {expected_type} contracts only.")
            if long_leg.contract.expiration_date != short_leg.contract.expiration_date:
                reasons.append("Option legs must share one expiration date.")
            if (
                thesis.strategy == "bull_call_debit_spread"
                and long_leg.contract.strike_price >= short_leg.contract.strike_price
            ):
                reasons.append("Long call strike must be below the short call strike.")
            if (
                thesis.strategy == "bear_put_debit_spread"
                and long_leg.contract.strike_price <= short_leg.contract.strike_price
            ):
                reasons.append("Long put strike must be above the short put strike.")

            economics_inputs = (
                long_leg.contract.ask_price,
                short_leg.contract.bid_price,
                long_leg.contract.strike_price,
                short_leg.contract.strike_price,
            )
            if thesis.quantity > 0 and all(math.isfinite(value) for value in economics_inputs):
                projected_net_debit = round(
                    long_leg.contract.ask_price - short_leg.contract.bid_price, 4
                )
                projected_spread_width = round(
                    abs(short_leg.contract.strike_price - long_leg.contract.strike_price), 4
                )
                projected_max_loss = round(
                    max(0.0, projected_net_debit) * 100.0 * thesis.quantity, 2
                )
                projected_max_profit = round(
                    max(0.0, projected_spread_width - projected_net_debit)
                    * 100.0
                    * thesis.quantity,
                    2,
                )
                expected_breakeven = None
                if projected_net_debit > 0:
                    expected_breakeven = round(
                        long_leg.contract.strike_price + projected_net_debit
                        if thesis.strategy == "bull_call_debit_spread"
                        else long_leg.contract.strike_price - projected_net_debit,
                        4,
                    )
                claimed_economics = (
                    ("net debit", thesis.net_debit_per_share, projected_net_debit),
                    ("spread width", thesis.spread_width, projected_spread_width),
                    ("maximum loss", thesis.max_loss_dollars, projected_max_loss),
                    ("maximum profit", thesis.max_profit_dollars, projected_max_profit),
                )
                for label, claimed, recomputed in claimed_economics:
                    if not math.isfinite(claimed) or abs(claimed - recomputed) > 1e-6:
                        reasons.append(f"Claimed {label} does not match quote-derived economics.")
                if expected_breakeven is None:
                    if thesis.breakeven_price is not None:
                        reasons.append("Claimed breakeven does not match quote-derived economics.")
                elif (
                    thesis.breakeven_price is None
                    or not math.isfinite(thesis.breakeven_price)
                    or abs(thesis.breakeven_price - expected_breakeven) > 1e-6
                ):
                    reasons.append("Claimed breakeven does not match quote-derived economics.")
            else:
                reasons.append("Spread economics could not be recomputed from valid finite inputs.")

            try:
                observed = datetime.fromisoformat(chain.observed_at.replace("Z", "+00:00")).date()
                expiration = datetime.fromisoformat(long_leg.contract.expiration_date).date()
                days_to_expiration = (expiration - observed).days
            except ValueError:
                reasons.append("Expiration or observation timestamp is malformed.")
            else:
                if not policy.min_days_to_expiration <= days_to_expiration <= policy.max_days_to_expiration:
                    reasons.append("Days to expiration is outside the frozen window.")

            for contract in contracts:
                if (
                    contract.bid_price <= 0
                    or contract.ask_price <= 0
                    or contract.bid_price > contract.ask_price
                    or not math.isfinite(contract.bid_price)
                    or not math.isfinite(contract.ask_price)
                ):
                    reasons.append(f"{contract.symbol}: quote is invalid.")
                worst_relative_spread = max(worst_relative_spread, contract.relative_spread)
                if contract.relative_spread > policy.max_relative_spread:
                    reasons.append(f"{contract.symbol}: bid-ask spread is too wide.")
                if contract.data_age_seconds < 0:
                    reasons.append(f"{contract.symbol}: option evidence age is invalid.")
                elif contract.data_age_seconds > policy.max_data_age_seconds:
                    reasons.append(f"{contract.symbol}: option evidence is stale.")
                if contract.open_interest < policy.min_open_interest:
                    reasons.append(f"{contract.symbol}: open interest is below the liquidity floor.")
                if policy.require_greeks and (
                    contract.delta is None or contract.implied_volatility is None
                ):
                    reasons.append(f"{contract.symbol}: required Greeks or implied volatility are missing.")
                if len(contract.source_refs) < 2:
                    reasons.append(f"{contract.symbol}: contract evidence is incomplete.")

        if projected_net_debit <= 0:
            reasons.append("Net debit must be positive.")
        if projected_net_debit > policy.max_net_debit_per_share + 1e-9:
            reasons.append("Net debit exceeds the per-share policy ceiling.")
        if projected_max_loss > policy.max_loss_dollars + 1e-9:
            reasons.append("Maximum loss exceeds the options risk budget.")
        if projected_max_profit <= 0 and thesis.strategy != "abstain":
            reasons.append("Spread has no positive capped payoff after debit.")
        if (
            not math.isfinite(account.cash)
            or not math.isfinite(account.buying_power)
            or account.cash < projected_max_loss
            or account.buying_power < projected_max_loss
        ):
            reasons.append("Available cash or buying power cannot cover the recomputed maximum loss.")

        return OptionsRiskDecision(
            approved=len(reasons) == 0,
            reasons=tuple(reasons) if reasons else ("All deterministic options gates passed.",),
            projected_max_loss=round(projected_max_loss, 2),
            projected_max_profit=round(projected_max_profit, 2),
            worst_relative_spread=round(worst_relative_spread, 6),
            days_to_expiration=days_to_expiration,
        )


def build_alpaca_mleg_payload(thesis: OptionsThesis) -> dict[str, Any]:
    """Create the documented Alpaca multi-leg paper-order shape without submitting it."""

    if (
        thesis.strategy not in {"bull_call_debit_spread", "bear_put_debit_spread"}
        or len(thesis.legs) != 2
        or thesis.quantity < 1
    ):
        raise ValueError("Only an approved directional debit spread can produce an order plan")
    return {
        "order_class": "mleg",
        "qty": str(thesis.quantity),
        "type": "limit",
        "limit_price": f"{thesis.net_debit_per_share:.2f}",
        "time_in_force": "day",
        "legs": [leg.to_alpaca_dict() for leg in thesis.legs],
    }


def build_alpaca_mleg_close_payload(
    thesis: OptionsThesis,
    *,
    limit_credit_per_share: float,
) -> dict[str, Any]:
    """Build a two-leg close order for a previously approved debit spread."""

    if (
        thesis.strategy not in {"bull_call_debit_spread", "bear_put_debit_spread"}
        or len(thesis.legs) != 2
        or thesis.quantity < 1
    ):
        raise ValueError("Only an opened directional debit spread can produce a close plan")
    if limit_credit_per_share <= 0 or not math.isfinite(limit_credit_per_share):
        raise ValueError("Close credit must be finite and positive")
    close_legs: list[dict[str, str]] = []
    for leg in thesis.legs:
        if leg.side == "buy" and leg.position_intent == "buy_to_open":
            close_legs.append(
                {
                    "symbol": leg.contract.symbol,
                    "ratio_qty": str(leg.ratio_qty),
                    "side": "sell",
                    "position_intent": "sell_to_close",
                }
            )
        elif leg.side == "sell" and leg.position_intent == "sell_to_open":
            close_legs.append(
                {
                    "symbol": leg.contract.symbol,
                    "ratio_qty": str(leg.ratio_qty),
                    "side": "buy",
                    "position_intent": "buy_to_close",
                }
            )
        else:
            raise ValueError("Thesis legs are not an opening debit-spread shape")
    return {
        "order_class": "mleg",
        "qty": str(thesis.quantity),
        "type": "limit",
        "limit_price": f"{limit_credit_per_share:.2f}",
        "time_in_force": "day",
        "legs": close_legs,
    }


class GovernedOptionsEngine:
    """Observe -> propose -> advisory critique -> deterministic gate -> plan/abstain -> ledger."""

    def __init__(
        self,
        *,
        proposer: DefinedRiskOptionsProposer | None = None,
        advisory: OptionsAdvisoryAgent | None = None,
        risk_gate: DeterministicOptionsRiskGate | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.proposer = proposer or DefinedRiskOptionsProposer()
        self.advisory = advisory or TemplateOptionsAdvisory()
        self.risk_gate = risk_gate or DeterministicOptionsRiskGate()
        self.ledger = ledger or EvidenceLedger()

    def run_cycle(
        self,
        chain: OptionChainSnapshot,
        account: AccountState,
        policy: OptionsRiskPolicy | None = None,
    ) -> GovernedOptionsResult:
        frozen_policy = policy or OptionsRiskPolicy()
        thesis = self.proposer.propose(chain)
        advisory = self.advisory.analyze(thesis)
        risk = self.risk_gate.evaluate(thesis, chain, account, frozen_policy, advisory)
        if risk.approved:
            order_payload = build_alpaca_mleg_payload(thesis)
            receipt = OptionsExecutionReceipt(
                receipt_id=f"options-plan-{thesis.thesis_id}",
                created_at=utc_now_iso(),
                status="simulated_plan",
                thesis_id=thesis.thesis_id,
                broker_mode="simulation",
                order_payload=order_payload,
                message="Validated Alpaca multi-leg paper-order plan; no broker request was made.",
            )
        else:
            receipt = OptionsExecutionReceipt(
                receipt_id=f"options-abstain-{thesis.thesis_id}",
                created_at=utc_now_iso(),
                status="abstained",
                thesis_id=thesis.thesis_id,
                broker_mode="none",
                order_payload=None,
                message=" | ".join(risk.reasons),
            )

        payload = {
            "chain": chain.to_dict(),
            "account": account.to_dict(),
            "policy": frozen_policy.to_dict(),
            "thesis": thesis.to_dict(),
            "advisory": advisory.to_dict(),
            "risk": risk.to_dict(),
            "receipt": receipt.to_dict(),
        }
        entry = self.ledger.append("governed_options_cycle", payload)
        return GovernedOptionsResult(
            chain=chain,
            thesis=thesis,
            advisory=advisory,
            risk=risk,
            receipt=receipt,
            ledger_hash=entry["entry_hash"],
        )
