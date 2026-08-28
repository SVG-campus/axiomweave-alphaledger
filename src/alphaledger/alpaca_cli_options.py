from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence

from .options import OptionsThesis, build_alpaca_mleg_close_payload, build_alpaca_mleg_payload


class CliRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        input_text: str | None,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, str, str]: ...


class SubprocessCliRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        input_text: str | None,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, str, str]:
        completed = subprocess.run(
            list(command),
            input=input_text,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr


@dataclass(frozen=True)
class PaperOrderReceipt:
    action: str
    status: str
    client_order_id: str
    order_ref_sha256: str
    response_sha256: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AlpacaCliOptionsPaperExecutor:
    """Official-CLI options executor with paper-only host semantics and two explicit locks."""

    REQUIRED_ACK = "I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER"
    _OPTION_SYMBOL = re.compile(r"^SPY\d{6}[CP]\d{8}$")

    def __init__(
        self,
        *,
        allow_submission: bool = False,
        runner: CliRunner | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("CLI timeout must be in (0, 60] seconds")
        self._runner = runner or SubprocessCliRunner()
        self._source_environment = dict(environment or os.environ)
        self._allow_submission = allow_submission
        self._timeout_seconds = timeout_seconds
        if runner is None and shutil.which("alpaca") is None:
            raise RuntimeError("Official Alpaca CLI is not installed or not on PATH")
        if self._source_environment.get("ALPACA_LIVE_TRADE", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            raise RuntimeError("ALPACA_LIVE_TRADE is set; AlphaLedger fails closed")

    def submit_open(self, thesis: OptionsThesis) -> PaperOrderReceipt:
        payload = build_alpaca_mleg_payload(thesis)
        client_order_id = _client_order_id(thesis, "open")
        payload["client_order_id"] = client_order_id
        return self._submit(payload, client_order_id, "open")

    def submit_close(
        self,
        thesis: OptionsThesis,
        *,
        limit_credit_per_share: float,
        attempt: int = 0,
    ) -> PaperOrderReceipt:
        payload = build_alpaca_mleg_close_payload(
            thesis,
            limit_credit_per_share=limit_credit_per_share,
        )
        client_order_id = _client_order_id(thesis, "close", attempt=attempt)
        payload["client_order_id"] = client_order_id
        return self._submit(payload, client_order_id, "close")

    def get_by_client_order_id(self, client_order_id: str) -> PaperOrderReceipt:
        if not re.fullmatch(r"aw-[a-z0-9-]{8,96}", client_order_id):
            raise ValueError("Client order ID is outside the AlphaLedger namespace")
        code, stdout, stderr = self._invoke(
            [
                "alpaca",
                "order",
                "get-by-client-id",
                "--client-order-id",
                client_order_id,
            ],
            input_text=None,
            mutation=False,
        )
        payload = _parse_cli_json(code, stdout, stderr)
        return _receipt_from_payload("observe", client_order_id, payload)

    def cancel_order(self, order_id: str, *, client_order_id: str) -> PaperOrderReceipt:
        if not order_id or len(order_id) > 128 or not re.fullmatch(r"[A-Za-z0-9-]+", order_id):
            raise ValueError("Order ID is malformed")
        code, stdout, stderr = self._invoke(
            ["alpaca", "order", "cancel", "--order-id", order_id],
            input_text=None,
            mutation=True,
        )
        payload = _parse_cli_json(code, stdout, stderr, allow_empty=True)
        return _receipt_from_payload("cancel", client_order_id, payload, fallback_order_id=order_id)

    def _submit(
        self,
        payload: dict[str, Any],
        client_order_id: str,
        action: str,
    ) -> PaperOrderReceipt:
        _validate_mleg_payload(payload)
        code, stdout, stderr = self._invoke(
            ["alpaca", "api", "POST", "/v2/orders"],
            input_text=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            mutation=True,
        )
        response = _parse_cli_json(code, stdout, stderr)
        return _receipt_from_payload(action, client_order_id, response)

    def _invoke(
        self,
        command: Sequence[str],
        *,
        input_text: str | None,
        mutation: bool,
    ) -> tuple[int, str, str]:
        if mutation and (
            not self._allow_submission
            or self._source_environment.get("ALPHALEDGER_PAPER_ORDER_ACK") != self.REQUIRED_ACK
        ):
            raise RuntimeError("Paper submission is locked by the explicit acknowledgement gate")
        env = dict(self._source_environment)
        api_key = env.get("APCA_API_KEY_ID") or env.get("ALPACA_API_KEY")
        api_secret = env.get("APCA_API_SECRET_KEY") or env.get("ALPACA_SECRET_KEY")
        if not api_key or not api_secret:
            raise RuntimeError("Paper credentials are unavailable")
        env["ALPACA_API_KEY"] = api_key
        env["ALPACA_SECRET_KEY"] = api_secret
        env["ALPACA_OUTPUT"] = "json"
        env["ALPACA_QUIET"] = "true"
        env.pop("ALPACA_LIVE_TRADE", None)
        return self._runner.run(
            command,
            input_text=input_text,
            env=env,
            timeout_seconds=self._timeout_seconds,
        )


def _validate_mleg_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("order_class") != "mleg":
        raise ValueError("Order class must be mleg")
    if payload.get("type") != "limit" or payload.get("time_in_force") != "day":
        raise ValueError("Only day limit MLeg orders are permitted")
    try:
        quantity = int(str(payload["qty"]))
        limit_price = float(str(payload["limit_price"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("MLeg quantity or limit price is malformed") from exc
    if not 1 <= quantity <= 5:
        raise ValueError("MLeg quantity is outside the competition contract budget")
    if limit_price <= 0 or not math.isfinite(limit_price):
        raise ValueError("MLeg limit price must be finite and positive")
    legs = payload.get("legs")
    if not isinstance(legs, list) or len(legs) != 2:
        raise ValueError("MLeg order must have exactly two legs")
    intents: set[str] = set()
    sides: set[str] = set()
    for leg in legs:
        if not isinstance(leg, dict) or not AlpacaCliOptionsPaperExecutor._OPTION_SYMBOL.fullmatch(
            str(leg.get("symbol", ""))
        ):
            raise ValueError("MLeg option symbol is outside the SPY competition allowlist")
        if str(leg.get("ratio_qty")) != "1":
            raise ValueError("Only one-to-one vertical legs are permitted")
        intents.add(str(leg.get("position_intent")))
        sides.add(str(leg.get("side")))
    if sides != {"buy", "sell"}:
        raise ValueError("MLeg vertical must have one buy and one sell leg")
    if intents not in ({"buy_to_open", "sell_to_open"}, {"buy_to_close", "sell_to_close"}):
        raise ValueError("MLeg position intents are inconsistent")


def _client_order_id(thesis: OptionsThesis, action: str, *, attempt: int = 0) -> str:
    if action not in {"open", "close"}:
        raise ValueError("Order action is invalid")
    if not 0 <= attempt <= 9:
        raise ValueError("Order attempt is outside the bounded retry range")
    digest = hashlib.sha256(
        f"{thesis.thesis_id}:{action}:{attempt}".encode("utf-8")
    ).hexdigest()[:20]
    return f"aw-{action}-{attempt}-{digest}"


def _parse_cli_json(
    code: int,
    stdout: str,
    stderr: str,
    *,
    allow_empty: bool = False,
) -> dict[str, Any]:
    if code != 0:
        error_hash = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
        raise RuntimeError(f"Alpaca CLI failed with exit {code}; stderr_sha256={error_hash}")
    if not stdout.strip() and allow_empty:
        return {"status": "accepted"}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Alpaca CLI did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Alpaca CLI order response must be a JSON object")
    return payload


def _receipt_from_payload(
    action: str,
    client_order_id: str,
    payload: Mapping[str, Any],
    *,
    fallback_order_id: str = "",
) -> PaperOrderReceipt:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    order_id = str(payload.get("id") or fallback_order_id or "unavailable")
    status = str(payload.get("status") or "accepted")
    return PaperOrderReceipt(
        action=action,
        status=status,
        client_order_id=client_order_id,
        order_ref_sha256=hashlib.sha256(order_id.encode("utf-8")).hexdigest(),
        response_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        message="Official Alpaca CLI paper-order response was received and identifiers were redacted.",
    )
