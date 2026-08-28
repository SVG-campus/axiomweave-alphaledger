from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .models import ExecutionReceipt, MarketSnapshot, TradeThesis, utc_now_iso


class Broker(Protocol):
    mode: str

    def execute(self, thesis: TradeThesis, snapshot: MarketSnapshot) -> ExecutionReceipt: ...


@dataclass
class SimulationBroker:
    mode: str = "simulation"

    def execute(self, thesis: TradeThesis, snapshot: MarketSnapshot) -> ExecutionReceipt:
        return ExecutionReceipt(
            receipt_id=f"sim-{thesis.thesis_id}",
            created_at=utc_now_iso(),
            status="simulated",
            thesis_id=thesis.thesis_id,
            symbol=thesis.symbol,
            side=thesis.side,
            quantity=thesis.quantity,
            fill_price=snapshot.last_price,
            broker_mode=self.mode,
            message="Deterministic simulation only; no broker request was made.",
        )


class AlpacaCliPaperBroker:
    """Optional paper-only CLI adapter with a deliberate two-key execution lock."""

    mode = "paper"
    REQUIRED_ACK = "I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER"

    def __init__(self, *, allow_submission: bool = False) -> None:
        self.allow_submission = allow_submission
        if shutil.which("alpaca") is None:
            raise RuntimeError("Alpaca CLI is not installed or not on PATH.")
        if os.getenv("ALPACA_LIVE_TRADE", "").lower() in {"1", "true", "yes"}:
            raise RuntimeError("ALPACA_LIVE_TRADE is set; AlphaLedger fails closed.")

    def execute(self, thesis: TradeThesis, snapshot: MarketSnapshot) -> ExecutionReceipt:
        if not self.allow_submission or os.getenv("ALPHALEDGER_PAPER_ORDER_ACK") != self.REQUIRED_ACK:
            raise RuntimeError("Paper submission is locked; use simulation for the public demo.")
        if thesis.side not in {"buy", "sell"}:
            raise RuntimeError("Only buy or sell candidates can reach the CLI adapter.")

        command = [
            "alpaca",
            "order",
            "submit",
            "--symbol",
            thesis.symbol,
            "--side",
            thesis.side,
            "--qty",
            str(thesis.quantity),
            "--type",
            "market",
            "--time-in-force",
            "day",
        ]
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        payload = json.loads(completed.stdout)
        order_id = payload.get("id", "unknown")
        return ExecutionReceipt(
            receipt_id=str(order_id),
            created_at=utc_now_iso(),
            status="paper_submitted",
            thesis_id=thesis.thesis_id,
            symbol=thesis.symbol,
            side=thesis.side,
            quantity=thesis.quantity,
            fill_price=None,
            broker_mode=self.mode,
            message="Submitted through the official Alpaca CLI in its paper-default configuration.",
        )


def abstention_receipt(thesis: TradeThesis, reasons: tuple[str, ...]) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id=f"abstain-{thesis.thesis_id}",
        created_at=utc_now_iso(),
        status="abstained",
        thesis_id=thesis.thesis_id,
        symbol=thesis.symbol,
        side=thesis.side,
        quantity=0.0,
        fill_price=None,
        broker_mode="none",
        message=" | ".join(reasons),
    )
