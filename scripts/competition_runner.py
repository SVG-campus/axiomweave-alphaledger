from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from alphaledger.competition_runner import RuntimeMode, build_agent_from_environment


def main() -> int:
    parser = argparse.ArgumentParser(description="AxiomWeave AlphaLedger competition controller")
    parser.add_argument("--mode", choices=[mode.value for mode in RuntimeMode], default="dry-run")
    parser.add_argument("--writer-id", default="alphaledger-primary")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()
    if not 30 <= args.interval_seconds <= 300:
        parser.error("--interval-seconds must be between 30 and 300")
    agent = build_agent_from_environment(
        mode=RuntimeMode(args.mode),
        root=ROOT,
        writer_id=args.writer_id,
    )
    while True:
        receipt = agent.run_once()
        print(json.dumps(receipt.to_dict(), sort_keys=True), flush=True)
        if args.once or receipt.phase == "complete":
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
