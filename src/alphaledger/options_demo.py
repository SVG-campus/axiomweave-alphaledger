from __future__ import annotations

from dataclasses import replace

from .models import AccountState
from .options import OptionChainSnapshot, OptionQuote


def _quote(
    symbol: str,
    strike: float,
    *,
    bid: float,
    ask: float,
    delta: float | None,
    implied_volatility: float | None = 0.22,
    open_interest: int = 650,
    data_age_seconds: int = 12,
    expiration_date: str = "2026-09-18",
) -> OptionQuote:
    return OptionQuote(
        symbol=symbol,
        underlying_symbol="SPY",
        expiration_date=expiration_date,
        option_type="call",
        strike_price=strike,
        bid_price=bid,
        ask_price=ask,
        delta=delta,
        implied_volatility=implied_volatility,
        open_interest=open_interest,
        data_age_seconds=data_age_seconds,
        source_refs=(
            f"demo://option-snapshot/{symbol}",
            "alpaca-docs://options-snapshots-schema",
        ),
    )


def build_options_chain(scenario: str = "Valid defined-risk spread") -> OptionChainSnapshot:
    contracts = [
        _quote("SPY260918C00600000", 600.0, bid=0.50, ask=0.55, delta=0.51),
        _quote("SPY260918C00601000", 601.0, bid=0.35, ask=0.40, delta=0.42),
        _quote("SPY260918C00602000", 602.0, bid=0.23, ask=0.28, delta=0.34),
    ]

    if scenario == "Stale option evidence":
        contracts = [replace(contract, data_age_seconds=900) for contract in contracts]
    elif scenario == "Missing Greeks":
        contracts[0] = replace(contracts[0], delta=None, implied_volatility=None)
    elif scenario == "Wide bid-ask market":
        contracts[0] = replace(contracts[0], bid_price=0.20, ask_price=0.55)
    elif scenario == "Maximum loss above budget":
        contracts[0] = replace(contracts[0], ask_price=0.75)
    elif scenario == "Low open interest":
        contracts[1] = replace(contracts[1], open_interest=5)
    elif scenario == "No valid vertical":
        contracts = [contracts[0]]

    chain = OptionChainSnapshot(
        underlying_symbol="SPY",
        underlying_price=600.0,
        observed_at="2026-08-24T12:00:00+00:00",
        contracts=tuple(contracts),
        source_refs=(
            "demo://spy-options-chain/frozen-v1",
            "policy://defined-risk-options-v1",
        ),
    )
    if scenario == "Stale underlying snapshot":
        chain = replace(chain, underlying_data_age_seconds=900)
    return chain


def build_options_account(*, broker_mode: str = "simulation", open_orders: int = 0) -> AccountState:
    return AccountState(
        equity=500.0,
        cash=500.0,
        buying_power=500.0,
        daily_pnl=0.0,
        positions={},
        open_orders=open_orders,
        broker_mode=broker_mode,
    )
