from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from alphaledger.alpaca_readonly import AlpacaCredentials, AlpacaReadOnlyObserver
from alphaledger.options import GovernedOptionsEngine


def _credentials() -> AlpacaCredentials:
    try:
        return AlpacaCredentials.from_environment()
    except RuntimeError:
        if not sys.stdin.isatty():
            raise RuntimeError("Paper credentials are unavailable in a non-interactive session")
        key_id = input("Dedicated PAPER API key ID: ").strip()
        secret = getpass.getpass("Dedicated PAPER API secret (hidden): ").strip()
        if not key_id or not secret:
            raise RuntimeError("Both paper credential fields are required")
        return AlpacaCredentials(key_id, secret)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the paper account, observe an options chain with GET only, and run deterministic policy without sending an order."
    )
    parser.add_argument("--ack-six-get-readonly", action="store_true")
    parser.add_argument("--underlying", default="SPY")
    parser.add_argument("--expiration-gte", required=True)
    parser.add_argument("--expiration-lte", required=True)
    parser.add_argument("--strike-gte", required=True, type=float)
    parser.add_argument("--strike-lte", required=True, type=float)
    parser.add_argument("--stock-feed", choices=("iex", "sip", "delayed_sip"), default="iex")
    parser.add_argument("--options-feed", choices=("indicative", "opra"), default="indicative")
    args = parser.parse_args()
    if not args.ack_six_get_readonly:
        parser.error(
            "No request was made. Re-run with --ack-six-get-readonly after reviewing docs/paper-readiness.md"
        )

    try:
        observer = AlpacaReadOnlyObserver(_credentials())
        readiness = observer.reconcile()
        if not readiness.ready_for_defined_risk_observation:
            print(json.dumps({"readiness": readiness.to_dict()}, indent=2))
            return 2

        normalized = observer.observe_option_chain(
            args.underlying,
            expiration_date_gte=args.expiration_gte,
            expiration_date_lte=args.expiration_lte,
            strike_price_gte=args.strike_gte,
            strike_price_lte=args.strike_lte,
            stock_feed=args.stock_feed,
            options_feed=args.options_feed,
        )
        result = GovernedOptionsEngine().run_cycle(
            normalized.chain,
            readiness.to_account_state(),
        )
        print(
            json.dumps(
                {
                    "claim_ceiling": "C1 read-only mechanics; not official evaluation or profit evidence",
                    "readiness": readiness.to_dict(),
                    "normalization": normalized.to_receipt_dict(),
                    "governed_decision": {
                        "strategy": result.thesis.strategy,
                        "risk": result.risk.to_dict(),
                        "receipt": result.receipt.to_dict(),
                        "ledger_hash": result.ledger_hash,
                    },
                },
                indent=2,
            )
        )
        return 0 if result.risk.approved else 3
    finally:
        os.environ.pop("APCA_API_KEY_ID", None)
        os.environ.pop("APCA_API_SECRET_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
