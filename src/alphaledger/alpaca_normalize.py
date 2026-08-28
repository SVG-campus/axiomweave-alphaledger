from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from .alpaca_readonly import ReadOnlyResponse
from .options import OptionChainSnapshot, OptionQuote


@dataclass(frozen=True)
class NormalizedOptionChain:
    """Redacted receipt around typed market evidence; raw payloads are never retained here."""

    chain: OptionChainSnapshot
    observed_at: str
    stock_feed: str
    options_feed: str
    payload_hashes: tuple[str, ...]
    skipped_contracts: tuple[str, ...]
    source_refs: tuple[str, ...]

    def to_receipt_dict(self) -> dict[str, Any]:
        stable_chain = json.dumps(
            self.chain.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return {
            "underlying_symbol": self.chain.underlying_symbol,
            "underlying_price": self.chain.underlying_price,
            "underlying_data_age_seconds": self.chain.underlying_data_age_seconds,
            "contracts_count": len(self.chain.contracts),
            "observed_at": self.observed_at,
            "stock_feed": self.stock_feed,
            "options_feed": self.options_feed,
            "payload_hashes": list(self.payload_hashes),
            "skipped_contracts": list(self.skipped_contracts),
            "source_refs": list(self.source_refs),
            "normalized_chain_sha256": hashlib.sha256(stable_chain.encode("utf-8")).hexdigest(),
        }


def _object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"Alpaca {field_name} must be a JSON object")
    return value


def _finite_float(value: Any, field_name: str, *, positive: bool = False) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"Alpaca {field_name} is not numeric") from error
    if not math.isfinite(parsed) or (positive and parsed <= 0):
        raise RuntimeError(f"Alpaca {field_name} is invalid")
    return parsed


def _optional_finite_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _finite_float(value, field_name)


def _nonnegative_int(value: Any, field_name: str) -> int:
    parsed = _finite_float(value, field_name)
    if parsed < 0 or not parsed.is_integer():
        raise RuntimeError(f"Alpaca {field_name} must be a nonnegative integer")
    return int(parsed)


def _timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Alpaca {field_name} timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"Alpaca {field_name} timestamp is malformed") from error
    if parsed.tzinfo is None:
        raise RuntimeError(f"Alpaca {field_name} timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _age_seconds(as_of: datetime, observed: datetime, field_name: str) -> int:
    delta = (as_of - observed).total_seconds()
    if delta < -5:
        raise RuntimeError(f"Alpaca {field_name} is future-dated")
    return max(0, math.ceil(delta))


def _reject_pagination(payload: dict[str, Any], field_name: str) -> None:
    for key in ("next_page_token", "page_token"):
        value = payload.get(key)
        if value not in (None, ""):
            raise RuntimeError(f"Alpaca {field_name} is paginated; the normalized set is incomplete")


def _source_ref(response: ReadOnlyResponse) -> str:
    return f"{response.endpoint}#sha256={response.payload_sha256}"


def normalize_option_chain(
    underlying_symbol: str,
    stock_response: ReadOnlyResponse,
    contracts_response: ReadOnlyResponse,
    chain_response: ReadOnlyResponse,
    *,
    as_of: datetime,
    stock_feed: str,
    options_feed: str,
    option_type: str = "call",
) -> NormalizedOptionChain:
    """Convert three exact Alpaca GET responses into typed, policy-ready evidence."""

    symbol = underlying_symbol.upper()
    if not symbol or symbol != underlying_symbol.upper().strip():
        raise ValueError("Underlying symbol is malformed")
    if as_of.tzinfo is None:
        raise ValueError("Normalization time must include a timezone")
    as_of_utc = as_of.astimezone(timezone.utc)
    if stock_feed not in {"iex", "sip", "delayed_sip"}:
        raise ValueError("Stock feed is outside the frozen normalization allowlist")
    if options_feed not in {"indicative", "opra"}:
        raise ValueError("Options feed is outside the frozen normalization allowlist")
    if option_type not in {"call", "put"}:
        raise ValueError("Option type must be call or put")

    stock = _object(stock_response.payload, "stock snapshot response")
    contracts_payload = _object(contracts_response.payload, "option contracts response")
    chain_payload = _object(chain_response.payload, "option chain response")
    _reject_pagination(contracts_payload, "option contracts response")
    _reject_pagination(chain_payload, "option chain response")

    observed_symbol = str(stock.get("symbol", "")).upper()
    if observed_symbol != symbol:
        raise RuntimeError("Alpaca stock snapshot symbol does not match the requested underlying")
    latest_trade = _object(stock.get("latestTrade"), "stock latestTrade")
    underlying_price = _finite_float(latest_trade.get("p"), "stock latestTrade price", positive=True)
    underlying_time = _timestamp(latest_trade.get("t"), "stock latestTrade")
    underlying_age = _age_seconds(as_of_utc, underlying_time, "stock latestTrade")

    contract_rows = contracts_payload.get("option_contracts")
    snapshots = chain_payload.get("snapshots")
    if not isinstance(contract_rows, list):
        raise RuntimeError("Alpaca option_contracts must be a JSON array")
    if not isinstance(snapshots, dict):
        raise RuntimeError("Alpaca snapshots must be a JSON object")

    contract_ref = _source_ref(contracts_response)
    chain_ref = _source_ref(chain_response)
    source_refs = (
        _source_ref(stock_response),
        contract_ref,
        chain_ref,
    )
    normalized: list[OptionQuote] = []
    skipped: list[str] = []

    for index, raw_contract in enumerate(contract_rows):
        label = f"contract[{index}]"
        if isinstance(raw_contract, dict) and raw_contract.get("symbol"):
            label = str(raw_contract["symbol"])
        try:
            metadata = _object(raw_contract, label)
            contract_symbol = str(metadata.get("symbol", "")).strip().upper()
            if not contract_symbol:
                raise RuntimeError("contract symbol is missing")
            if str(metadata.get("underlying_symbol", "")).upper() != symbol:
                raise RuntimeError("underlying symbol does not match")
            if str(metadata.get("type", "")).lower() != option_type:
                raise RuntimeError(f"contract is not a {option_type}")
            if str(metadata.get("status", "")).lower() != "active":
                raise RuntimeError("contract is not active")
            if metadata.get("tradable") is not True:
                raise RuntimeError("contract is not tradable")

            expiration_text = str(metadata.get("expiration_date", ""))
            try:
                date.fromisoformat(expiration_text)
            except ValueError as error:
                raise RuntimeError("expiration date is malformed") from error
            strike = _finite_float(metadata.get("strike_price"), "strike price", positive=True)
            open_interest = _nonnegative_int(metadata.get("open_interest"), "open interest")

            snapshot = _object(snapshots.get(contract_symbol), f"snapshot for {contract_symbol}")
            latest_quote = _object(snapshot.get("latestQuote"), f"latestQuote for {contract_symbol}")
            bid = _finite_float(latest_quote.get("bp"), f"bid for {contract_symbol}", positive=True)
            ask = _finite_float(latest_quote.get("ap"), f"ask for {contract_symbol}", positive=True)
            if bid > ask:
                raise RuntimeError("bid exceeds ask")
            quote_time = _timestamp(latest_quote.get("t"), f"latestQuote for {contract_symbol}")
            quote_age = _age_seconds(as_of_utc, quote_time, f"latestQuote for {contract_symbol}")

            greeks_value = snapshot.get("greeks")
            greeks = {} if greeks_value is None else _object(greeks_value, f"greeks for {contract_symbol}")
            delta = _optional_finite_float(greeks.get("delta"), f"delta for {contract_symbol}")
            iv_value = snapshot.get("impliedVolatility", snapshot.get("implied_volatility"))
            implied_volatility = _optional_finite_float(iv_value, f"implied volatility for {contract_symbol}")

            normalized.append(
                OptionQuote(
                    symbol=contract_symbol,
                    underlying_symbol=symbol,
                    expiration_date=expiration_text,
                    option_type=option_type,
                    strike_price=strike,
                    bid_price=bid,
                    ask_price=ask,
                    delta=delta,
                    implied_volatility=implied_volatility,
                    open_interest=open_interest,
                    data_age_seconds=quote_age,
                    source_refs=(contract_ref, chain_ref),
                )
            )
        except RuntimeError as error:
            skipped.append(f"{label}: {error}")

    if not normalized:
        details = "; ".join(skipped) if skipped else "no contract rows were returned"
        raise RuntimeError(f"No option contracts survived strict normalization: {details}")

    normalized.sort(key=lambda contract: (contract.expiration_date, contract.strike_price, contract.symbol))
    observed_at = as_of_utc.isoformat()
    typed_chain = OptionChainSnapshot(
        underlying_symbol=symbol,
        underlying_price=underlying_price,
        observed_at=observed_at,
        contracts=tuple(normalized),
        source_refs=source_refs,
        underlying_data_age_seconds=underlying_age,
        underlying_feed=stock_feed,
        options_feed=options_feed,
    )
    return NormalizedOptionChain(
        chain=typed_chain,
        observed_at=observed_at,
        stock_feed=stock_feed,
        options_feed=options_feed,
        payload_hashes=(
            stock_response.payload_sha256,
            contracts_response.payload_sha256,
            chain_response.payload_sha256,
        ),
        skipped_contracts=tuple(skipped),
        source_refs=source_refs,
    )
