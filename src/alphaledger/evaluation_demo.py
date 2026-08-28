from __future__ import annotations

from .evaluation import FrozenOptionsReplayManifest, OptionsReplayEpisode
from .options_demo import build_options_account, build_options_chain


def build_frozen_options_replay() -> tuple[
    tuple[OptionsReplayEpisode, ...], FrozenOptionsReplayManifest
]:
    scenarios = (
        ("valid-up", "Valid defined-risk spread", 600.50),
        ("valid-down", "Valid defined-risk spread", 599.50),
        ("stale", "Stale option evidence", 600.80),
        ("missing-greeks", "Missing Greeks", 599.80),
        ("loss-overage", "Maximum loss above budget", 601.30),
        ("low-interest", "Low open interest", 600.10),
        ("wide-market", "Wide bid-ask market", 599.70),
        ("no-vertical", "No valid vertical", 600.40),
    )
    episodes = tuple(
        OptionsReplayEpisode(
            episode_id=episode_id,
            chain=build_options_chain(scenario),
            account=build_options_account(),
            settlement_underlying_price=settlement,
            source_refs=(
                f"demo://options-replay/{episode_id}",
                "policy://frozen-options-replay-v1",
            ),
        )
        for episode_id, scenario, settlement in scenarios
    )
    manifest = FrozenOptionsReplayManifest.freeze(
        episodes,
        source_kind="synthetic",
        window_start="2026-08-24T12:00:00Z",
        window_end="2026-08-24T12:08:00Z",
        initial_cash=1000.0,
        commission_per_contract=0.0,
        slippage_per_leg_per_share=0.0,
        seed=20260824,
        source_refs=(
            "demo://frozen-options-replay-v1",
            "alpaca-docs://historical-options-data-contract",
        ),
    )
    return episodes, manifest
