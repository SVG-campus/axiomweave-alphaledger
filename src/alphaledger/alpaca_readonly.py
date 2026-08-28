from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import AccountState


JsonPayload = dict[str, Any] | list[Any]


class JsonGetTransport(Protocol):
    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str | int | float | bool],
        timeout_seconds: float,
    ) -> tuple[JsonPayload, Mapping[str, str]]: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class UrllibJsonGetTransport:
    """Minimal HTTPS JSON transport that exposes GET and no mutation method."""

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str | int | float | bool],
        timeout_seconds: float,
    ) -> tuple[JsonPayload, Mapping[str, str]]:
        encoded = urlencode(sorted((key, str(value).lower() if isinstance(value, bool) else value) for key, value in params.items()))
        target = f"{url}?{encoded}" if encoded else url
        request = Request(target, headers=dict(headers), method="GET")
        opener = build_opener(_RejectRedirects())
        with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310 - exact hosts are frozen by the observer
            raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, (dict, list)):
                raise RuntimeError("Alpaca returned a non-object JSON payload")
            return payload, dict(response.headers.items())


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key_id: str = field(repr=False)
    api_secret_key: str = field(repr=False)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "AlpacaCredentials":
        source = environment if environment is not None else os.environ
        key_id = source.get("APCA_API_KEY_ID", "").strip()
        secret = source.get("APCA_API_SECRET_KEY", "").strip()
        if not key_id or not secret:
            raise RuntimeError("Dedicated Alpaca paper credentials are not configured")
        return cls(api_key_id=key_id, api_secret_key=secret)


@dataclass(frozen=True)
class ReadOnlyResponse:
    endpoint: str
    observed_at: str
    request_id: str | None
    payload_sha256: str
    record_count: int
    payload: JsonPayload = field(repr=False)

    def to_receipt_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "observed_at": self.observed_at,
            "request_id": self.request_id,
            "payload_sha256": self.payload_sha256,
            "record_count": self.record_count,
        }


@dataclass(frozen=True)
class PaperReadinessReceipt:
    observed_at: str
    ready_for_defined_risk_observation: bool
    reasons: tuple[str, ...]
    account_status: str
    equity: float
    cash: float
    buying_power: float
    daily_pnl: float
    options_approved_level: int
    options_trading_level: int
    positions_count: int
    open_orders_count: int
    trading_blocked: bool
    request_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    account_ref_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_account_state(self) -> AccountState:
        if not self.ready_for_defined_risk_observation:
            raise RuntimeError("A nonready paper receipt cannot become governed account state")
        if self.positions_count != 0 or self.open_orders_count != 0 or self.trading_blocked:
            raise RuntimeError("Paper receipt contains unreconciled account state")
        return AccountState(
            equity=self.equity,
            cash=self.cash,
            buying_power=self.buying_power,
            daily_pnl=self.daily_pnl,
            positions={},
            open_orders=0,
            broker_mode="paper",
        )


def _payload_hash(payload: JsonPayload) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_count(payload: JsonPayload) -> int:
    if isinstance(payload, list):
        return len(payload)
    for key in ("option_contracts", "snapshots", "orders", "positions"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            return len(value)
    return 1


def _finite_float(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"Alpaca account field {field_name} is not numeric") from error
    if not math.isfinite(parsed):
        raise RuntimeError(f"Alpaca account field {field_name} is not finite")
    return parsed


def _level(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class AlpacaReadOnlyObserver:
    """Named GET-only paper observer. It has no generic request or order-submission API."""

    PAPER_BASE = "https://paper-api.alpaca.markets"
    DATA_BASE = "https://data.alpaca.markets"
    _PAPER_PATHS = frozenset(
        {
            "/v2/account",
            "/v2/positions",
            "/v2/orders",
            "/v2/options/contracts",
        }
    )
    _UNDERLYING = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")

    def __init__(
        self,
        credentials: AlpacaCredentials,
        *,
        transport: JsonGetTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Read-only timeout must be in (0, 30] seconds")
        self._credentials = credentials
        self._transport = transport or UrllibJsonGetTransport()
        self._timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "APCA-API-KEY-ID": self._credentials.api_key_id,
            "APCA-API-SECRET-KEY": self._credentials.api_secret_key,
            "User-Agent": "AxiomWeave-AlphaLedger/0.3-readonly",
        }

    def _get(
        self,
        base: str,
        path: str,
        params: Mapping[str, str | int | float | bool] | None = None,
    ) -> ReadOnlyResponse:
        if base == self.PAPER_BASE:
            allowed = path in self._PAPER_PATHS
        elif base == self.DATA_BASE:
            allowed = bool(
                re.fullmatch(r"/v1beta1/options/snapshots/[A-Z][A-Z0-9.]{0,9}", path)
                or re.fullmatch(r"/v2/stocks/[A-Z][A-Z0-9.]{0,9}/snapshot", path)
                or path == "/v2/stocks/bars"
            )
        else:
            allowed = False
        if not allowed:
            raise RuntimeError("Endpoint is outside the frozen Alpaca read-only allowlist")

        endpoint = f"{base}{path}"
        payload, response_headers = self._transport.get_json(
            endpoint,
            headers=self._headers(),
            params=params or {},
            timeout_seconds=self._timeout_seconds,
        )
        request_id = response_headers.get("X-Request-ID") or response_headers.get("x-request-id")
        return ReadOnlyResponse(
            endpoint=endpoint,
            observed_at=datetime.now(timezone.utc).isoformat(),
            request_id=request_id,
            payload_sha256=_payload_hash(payload),
            record_count=_record_count(payload),
            payload=payload,
        )

    def read_account(self) -> ReadOnlyResponse:
        return self._get(self.PAPER_BASE, "/v2/account")

    def read_positions(self) -> ReadOnlyResponse:
        return self._get(self.PAPER_BASE, "/v2/positions")

    def read_open_orders(self) -> ReadOnlyResponse:
        return self._get(
            self.PAPER_BASE,
            "/v2/orders",
            {"status": "open", "nested": True, "direction": "asc", "limit": 500},
        )

    def read_option_contracts(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str,
        expiration_date_lte: str,
        option_type: str = "call",
        limit: int = 1000,
    ) -> ReadOnlyResponse:
        symbol = underlying_symbol.upper()
        if not self._UNDERLYING.fullmatch(symbol):
            raise ValueError("Underlying symbol is malformed")
        if not 1 <= limit <= 10000:
            raise ValueError("Contract limit is outside Alpaca's documented range")
        if option_type not in {"call", "put"}:
            raise ValueError("Option type must be call or put")
        return self._get(
            self.PAPER_BASE,
            "/v2/options/contracts",
            {
                "underlying_symbols": symbol,
                "status": "active",
                "type": option_type,
                "expiration_date_gte": expiration_date_gte,
                "expiration_date_lte": expiration_date_lte,
                "limit": limit,
            },
        )

    def read_stock_snapshot(self, underlying_symbol: str, *, feed: str = "iex") -> ReadOnlyResponse:
        symbol = underlying_symbol.upper()
        if not self._UNDERLYING.fullmatch(symbol):
            raise ValueError("Underlying symbol is malformed")
        if feed not in {"iex", "sip", "delayed_sip"}:
            raise ValueError("Stock feed is outside the frozen read-only allowlist")
        return self._get(
            self.DATA_BASE,
            f"/v2/stocks/{symbol}/snapshot",
            {"feed": feed},
        )

    def read_stock_bars(
        self,
        underlying_symbol: str,
        *,
        start: str,
        end: str,
        timeframe: str = "5Min",
        feed: str = "iex",
        limit: int = 1000,
    ) -> ReadOnlyResponse:
        """Read one bounded, ascending stock-bar page from Alpaca's documented endpoint."""

        symbol = underlying_symbol.upper()
        if not self._UNDERLYING.fullmatch(symbol):
            raise ValueError("Underlying symbol is malformed")
        if timeframe not in {"1Min", "5Min", "15Min", "1Hour", "1Day"}:
            raise ValueError("Bar timeframe is outside the frozen read-only allowlist")
        if feed not in {"iex", "sip", "delayed_sip"}:
            raise ValueError("Stock feed is outside the frozen read-only allowlist")
        if not start or not end or start >= end:
            raise ValueError("Stock-bar time window is invalid")
        if not 1 <= limit <= 10000:
            raise ValueError("Stock-bar limit is outside Alpaca's documented range")
        return self._get(
            self.DATA_BASE,
            "/v2/stocks/bars",
            {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
                "adjustment": "raw",
                "feed": feed,
                "sort": "asc",
            },
        )

    def read_option_chain(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str,
        expiration_date_lte: str,
        strike_price_gte: float,
        strike_price_lte: float,
        option_type: str = "call",
        feed: str = "indicative",
        limit: int = 1000,
    ) -> ReadOnlyResponse:
        symbol = underlying_symbol.upper()
        if not self._UNDERLYING.fullmatch(symbol):
            raise ValueError("Underlying symbol is malformed")
        if feed not in {"indicative", "opra"}:
            raise ValueError("Option feed must be explicitly indicative or OPRA")
        if option_type not in {"call", "put"}:
            raise ValueError("Option type must be call or put")
        if strike_price_gte <= 0 or strike_price_lte < strike_price_gte:
            raise ValueError("Option strike window is invalid")
        if not 1 <= limit <= 1000:
            raise ValueError("Snapshot limit is outside Alpaca's documented range")
        return self._get(
            self.DATA_BASE,
            f"/v1beta1/options/snapshots/{symbol}",
            {
                "feed": feed,
                "type": option_type,
                "expiration_date_gte": expiration_date_gte,
                "expiration_date_lte": expiration_date_lte,
                "strike_price_gte": strike_price_gte,
                "strike_price_lte": strike_price_lte,
                "limit": limit,
            },
        )

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
    ) -> Any:
        """Run the three named GETs and return a redacted, typed normalization receipt."""

        from .alpaca_normalize import normalize_option_chain

        stock = self.read_stock_snapshot(underlying_symbol, feed=stock_feed)
        contracts = self.read_option_contracts(
            underlying_symbol,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            option_type=option_type,
        )
        chain = self.read_option_chain(
            underlying_symbol,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            option_type=option_type,
            feed=options_feed,
        )
        return normalize_option_chain(
            underlying_symbol,
            stock,
            contracts,
            chain,
            as_of=as_of or datetime.now(timezone.utc),
            stock_feed=stock_feed,
            options_feed=options_feed,
            option_type=option_type,
        )

    def reconcile(self) -> PaperReadinessReceipt:
        account_response = self.read_account()
        positions_response = self.read_positions()
        orders_response = self.read_open_orders()
        if not isinstance(account_response.payload, dict):
            raise RuntimeError("Alpaca account response must be a JSON object")
        if not isinstance(positions_response.payload, list):
            raise RuntimeError("Alpaca positions response must be a JSON array")
        if not isinstance(orders_response.payload, list):
            raise RuntimeError("Alpaca open-orders response must be a JSON array")

        account = account_response.payload
        account_id = str(account.get("id", "")).strip()
        equity = _finite_float(account.get("equity"), "equity")
        last_equity = _finite_float(account.get("last_equity"), "last_equity")
        cash = _finite_float(account.get("cash"), "cash")
        buying_power = _finite_float(account.get("buying_power"), "buying_power")
        approved_level = _level(account.get("options_approved_level"))
        trading_level = _level(account.get("options_trading_level"))
        account_status = str(account.get("status", "UNKNOWN")).upper()
        trading_blocked = any(
            bool(account.get(field_name, False))
            for field_name in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
        )

        reasons: list[str] = []
        if account_status != "ACTIVE":
            reasons.append("Paper account status is not ACTIVE.")
        if not account_id:
            reasons.append("Paper account identifier is missing.")
        if trading_blocked:
            reasons.append("Paper account has an active trading restriction.")
        if approved_level < 3 or trading_level < 3:
            reasons.append("Paper account is not reconciled at options level 3 for multi-leg spreads.")
        if equity <= 0 or cash < 0 or buying_power <= 0:
            reasons.append("Paper account capital fields are not usable.")
        if positions_response.payload:
            reasons.append("Existing positions require ownership and exposure reconciliation.")
        if orders_response.payload:
            reasons.append("Open orders must be reconciled before a new options plan.")

        request_ids = tuple(
            request_id
            for request_id in (
                account_response.request_id,
                positions_response.request_id,
                orders_response.request_id,
            )
            if request_id
        )
        return PaperReadinessReceipt(
            observed_at=datetime.now(timezone.utc).isoformat(),
            ready_for_defined_risk_observation=len(reasons) == 0,
            reasons=tuple(reasons) if reasons else ("Read-only paper reconciliation passed.",),
            account_status=account_status,
            equity=round(equity, 2),
            cash=round(cash, 2),
            buying_power=round(buying_power, 2),
            daily_pnl=round(equity - last_equity, 2),
            options_approved_level=approved_level,
            options_trading_level=trading_level,
            positions_count=len(positions_response.payload),
            open_orders_count=len(orders_response.payload),
            trading_blocked=trading_blocked,
            request_ids=request_ids,
            source_refs=(
                account_response.endpoint,
                positions_response.endpoint,
                orders_response.endpoint,
            ),
            account_ref_sha256=hashlib.sha256(account_id.encode("utf-8")).hexdigest()
            if account_id
            else "",
        )
