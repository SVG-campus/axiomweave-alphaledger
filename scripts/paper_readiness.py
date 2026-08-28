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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run three GET-only checks against the dedicated Alpaca paper account."
    )
    parser.add_argument(
        "--ack-readonly",
        action="store_true",
        help="Acknowledge GET /v2/account, /v2/positions, and /v2/orders?status=open.",
    )
    args = parser.parse_args()
    if not args.ack_readonly:
        parser.error("No request was made. Re-run with --ack-readonly after reviewing docs/paper-readiness.md")

    try:
        credentials = AlpacaCredentials.from_environment()
    except RuntimeError:
        if not sys.stdin.isatty():
            raise RuntimeError("Paper credentials are unavailable in a non-interactive session")
        key_id = input("Dedicated PAPER API key ID: ").strip()
        secret = getpass.getpass("Dedicated PAPER API secret (hidden): ").strip()
        if not key_id or not secret:
            raise RuntimeError("Both paper credential fields are required")
        credentials = AlpacaCredentials(key_id, secret)

    observer = AlpacaReadOnlyObserver(credentials)
    receipt = observer.reconcile()
    print(json.dumps(receipt.to_dict(), indent=2))
    os.environ.pop("APCA_API_KEY_ID", None)
    os.environ.pop("APCA_API_SECRET_KEY", None)
    return 0 if receipt.ready_for_defined_risk_observation else 2


if __name__ == "__main__":
    raise SystemExit(main())
