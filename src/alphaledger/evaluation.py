from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .ledger import digest
from .models import AccountState
from .options import DefinedRiskOptionsProposer, GovernedOptionsEngine, OptionChainSnapshot, OptionsThesis


ReplaySourceKind = Literal["synthetic", "alpaca_historical_indicative", "alpaca_historical_opra"]


@dataclass(frozen=True)
class OptionsReplayEpisode:
    episode_id: str
    chain: OptionChainSnapshot
    account: AccountState
    settlement_underlying_price: float
    source_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "chain": self.chain.to_dict(),
            "account": self.account.to_dict(),
            "settlement_underlying_price": self.settlement_underlying_price,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class FrozenOptionsReplayManifest:
    manifest_id: str
    source_kind: ReplaySourceKind
    window_start: str
    window_end: str
    underlyings: tuple[str, ...]
    initial_cash: float
    commission_per_contract: float
    slippage_per_leg_per_share: float
    seed: int
    episodes_sha256: str
    claim_ceiling: str
    source_refs: tuple[str, ...]

    @classmethod
    def freeze(
        cls,
        episodes: tuple[OptionsReplayEpisode, ...],
        *,
        source_kind: ReplaySourceKind,
        window_start: str,
        window_end: str,
        initial_cash: float = 1000.0,
        commission_per_contract: float = 0.0,
        slippage_per_leg_per_share: float = 0.0,
        seed: int = 20260824,
        source_refs: tuple[str, ...] = (),
    ) -> "FrozenOptionsReplayManifest":
        if len(episodes) < 3:
            raise ValueError("Options replay requires at least three frozen episodes")
        if initial_cash <= 0 or not math.isfinite(initial_cash):
            raise ValueError("Replay initial cash must be finite and positive")
        if commission_per_contract < 0 or not math.isfinite(commission_per_contract):
            raise ValueError("Commission must be finite and non-negative")
        if slippage_per_leg_per_share < 0 or not math.isfinite(slippage_per_leg_per_share):
            raise ValueError("Slippage must be finite and non-negative")
        episodes_sha256 = digest([episode.to_dict() for episode in episodes])
        stable = {
            "source_kind": source_kind,
            "window_start": window_start,
            "window_end": window_end,
            "underlyings": sorted({episode.chain.underlying_symbol for episode in episodes}),
            "initial_cash": initial_cash,
            "commission_per_contract": commission_per_contract,
            "slippage_per_leg_per_share": slippage_per_leg_per_share,
            "seed": seed,
            "episodes_sha256": episodes_sha256,
            "source_refs": source_refs,
        }
        return cls(
            manifest_id="options-replay-" + digest(stable)[:12],
            source_kind=source_kind,
            window_start=window_start,
            window_end=window_end,
            underlyings=tuple(stable["underlyings"]),
            initial_cash=initial_cash,
            commission_per_contract=commission_per_contract,
            slippage_per_leg_per_share=slippage_per_leg_per_share,
            seed=seed,
            episodes_sha256=episodes_sha256,
            claim_ceiling="C1" if source_kind == "synthetic" else "C2_MAX_PENDING_INDEPENDENCE",
            source_refs=source_refs,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionsReplayMetric:
    route: str
    episodes: int
    plans: int
    abstentions: int
    synthetic_realized_pnl: float
    maximum_drawdown: float
    worst_episode_pnl: float
    total_modeled_maximum_loss: float
    decision_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionsReplayReceipt:
    manifest: FrozenOptionsReplayManifest
    metrics: tuple[OptionsReplayMetric, ...]
    replay_fingerprint: str
    claim_ceiling: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "replay_fingerprint": self.replay_fingerprint,
            "claim_ceiling": self.claim_ceiling,
            "warnings": list(self.warnings),
        }


def _spread_pnl(
    thesis: OptionsThesis,
    settlement_underlying_price: float,
    *,
    commission_per_contract: float,
    slippage_per_leg_per_share: float,
) -> float:
    if thesis.strategy != "bull_call_debit_spread" or len(thesis.legs) != 2:
        return 0.0
    long_leg, short_leg = thesis.legs
    long_intrinsic = max(0.0, settlement_underlying_price - long_leg.contract.strike_price)
    short_intrinsic = max(0.0, settlement_underlying_price - short_leg.contract.strike_price)
    gross_payoff = (long_intrinsic - short_intrinsic) * 100.0 * thesis.quantity
    debit = thesis.net_debit_per_share * 100.0 * thesis.quantity
    commissions = commission_per_contract * 2.0 * thesis.quantity
    slippage = slippage_per_leg_per_share * 100.0 * 2.0 * thesis.quantity
    return round(gross_payoff - debit - commissions - slippage, 2)


def _metric(
    route: str,
    *,
    outcomes: list[float],
    plan_losses: list[float],
    initial_cash: float,
) -> OptionsReplayMetric:
    equity = initial_cash
    peak = initial_cash
    maximum_drawdown = 0.0
    for outcome in outcomes:
        equity += outcome
        if equity <= 0:
            raise RuntimeError("Synthetic replay exhausted its frozen initial cash")
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, (equity / peak) - 1.0)
    plans = len(plan_losses)
    stable = {
        "route": route,
        "outcomes": outcomes,
        "plan_losses": plan_losses,
        "initial_cash": initial_cash,
    }
    return OptionsReplayMetric(
        route=route,
        episodes=len(outcomes),
        plans=plans,
        abstentions=len(outcomes) - plans,
        synthetic_realized_pnl=round(sum(outcomes), 2),
        maximum_drawdown=round(maximum_drawdown, 6),
        worst_episode_pnl=round(min(outcomes, default=0.0), 2),
        total_modeled_maximum_loss=round(sum(plan_losses), 2),
        decision_fingerprint=digest(stable),
    )


def run_options_replay(
    episodes: tuple[OptionsReplayEpisode, ...],
    manifest: FrozenOptionsReplayManifest,
) -> OptionsReplayReceipt:
    if len(episodes) < 3:
        raise ValueError("Options replay requires at least three frozen episodes")
    if digest([episode.to_dict() for episode in episodes]) != manifest.episodes_sha256:
        raise RuntimeError("Replay observations do not match the frozen manifest digest")
    if manifest.initial_cash <= 0 or not math.isfinite(manifest.initial_cash):
        raise ValueError("Replay initial cash must be finite and positive")
    if manifest.commission_per_contract < 0 or not math.isfinite(manifest.commission_per_contract):
        raise ValueError("Replay commission must be finite and non-negative")
    if manifest.slippage_per_leg_per_share < 0 or not math.isfinite(
        manifest.slippage_per_leg_per_share
    ):
        raise ValueError("Replay slippage must be finite and non-negative")
    for episode in episodes:
        if episode.settlement_underlying_price <= 0 or not math.isfinite(
            episode.settlement_underlying_price
        ):
            raise ValueError("Replay settlement prices must be finite and positive")

    governed_outcomes: list[float] = []
    governed_losses: list[float] = []
    governed_theses: list[OptionsThesis | None] = []
    engine = GovernedOptionsEngine()
    for episode in episodes:
        result = engine.run_cycle(episode.chain, episode.account)
        if result.risk.approved:
            governed_outcomes.append(
                _spread_pnl(
                    result.thesis,
                    episode.settlement_underlying_price,
                    commission_per_contract=manifest.commission_per_contract,
                    slippage_per_leg_per_share=manifest.slippage_per_leg_per_share,
                )
            )
            governed_losses.append(result.risk.projected_max_loss)
            governed_theses.append(result.thesis)
        else:
            governed_outcomes.append(0.0)
            governed_theses.append(None)

    proposer = DefinedRiskOptionsProposer()
    unguarded_outcomes: list[float] = []
    unguarded_losses: list[float] = []
    for episode in episodes:
        thesis = proposer.propose(episode.chain)
        if thesis.strategy == "bull_call_debit_spread":
            unguarded_outcomes.append(
                _spread_pnl(
                    thesis,
                    episode.settlement_underlying_price,
                    commission_per_contract=manifest.commission_per_contract,
                    slippage_per_leg_per_share=manifest.slippage_per_leg_per_share,
                )
            )
            unguarded_losses.append(thesis.max_loss_dollars)
        else:
            unguarded_outcomes.append(0.0)

    shuffled_settlements = [episode.settlement_underlying_price for episode in episodes]
    random.Random(manifest.seed).shuffle(shuffled_settlements)
    shuffled_outcomes: list[float] = []
    shuffled_losses: list[float] = []
    for thesis, settlement in zip(governed_theses, shuffled_settlements, strict=True):
        if thesis is None:
            shuffled_outcomes.append(0.0)
        else:
            shuffled_outcomes.append(
                _spread_pnl(
                    thesis,
                    settlement,
                    commission_per_contract=manifest.commission_per_contract,
                    slippage_per_leg_per_share=manifest.slippage_per_leg_per_share,
                )
            )
            shuffled_losses.append(thesis.max_loss_dollars)

    metrics = (
        _metric(
            "governed options agent",
            outcomes=governed_outcomes,
            plan_losses=governed_losses,
            initial_cash=manifest.initial_cash,
        ),
        _metric(
            "unguarded proposer control",
            outcomes=unguarded_outcomes,
            plan_losses=unguarded_losses,
            initial_cash=manifest.initial_cash,
        ),
        _metric(
            "cash/abstain control",
            outcomes=[0.0] * len(episodes),
            plan_losses=[],
            initial_cash=manifest.initial_cash,
        ),
        _metric(
            "shuffled-settlement negative control",
            outcomes=shuffled_outcomes,
            plan_losses=shuffled_losses,
            initial_cash=manifest.initial_cash,
        ),
    )
    fingerprint = digest([metric.to_dict() for metric in metrics])
    return OptionsReplayReceipt(
        manifest=manifest,
        metrics=metrics,
        replay_fingerprint=fingerprint,
        claim_ceiling=manifest.claim_ceiling,
        warnings=(
            "Synthetic payoff mechanics are not market evidence or a profitability estimate.",
            "Indicative and OPRA data must be evaluated as separate evidence layers.",
            "Historical promotion requires an organizer-approved frozen window and independent adjudication.",
        ),
    )
