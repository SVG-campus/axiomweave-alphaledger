from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.pathsep.join([source_path, existing_pythonpath])
        if existing_pythonpath
        else source_path
    )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    combined_output = f"{completed.stdout}\n{completed.stderr}"
    tests_match = re.search(r"Ran (\d+) tests?", combined_output)
    benchmark_paths = (
        ROOT / "evidence" / "signal-benchmark-receipt.json",
        ROOT / "evidence" / "hourly-regime-benchmark-receipt.json",
    )
    benchmark_receipts = []
    for path in benchmark_paths:
        if path.exists():
            raw = path.read_bytes()
            payload = json.loads(raw)
            benchmark_receipts.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "final_decision": payload.get("final_decision"),
                }
            )
    receipt = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_route": "single-writer paper-only SPY call/put debit spreads; one C0 exploratory entry after 10:20 ET, $250 maximum plan loss, 45-minute maximum hold, deterministic account/clock/risk ownership, official Alpaca CLI submission, and default Thursday 15:45 ET force-flat",
        "claim_ceiling": "C1 deterministic mechanics and falsified benchmark routes; C2 organizer window observations; C0 profit, alpha, and winning probability",
        "command": command,
        "exit_code": completed.returncode,
        "tests_run": int(tests_match.group(1)) if tests_match else None,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "strategy_selection_receipts": benchmark_receipts,
        "negative_controls": [
            "cash/abstain",
            "stale option evidence",
            "stale underlying evidence",
            "unknown stock or options feed rejection",
            "missing Greeks",
            "wide bid-ask market",
            "low open interest",
            "maximum-loss overage",
            "tampered claimed economics",
            "model-unavailable fail-closed advisory",
            "live-host and redirect rejection",
            "missing-credentials rejection",
            "blocked or under-permissioned paper-account reconciliation",
            "nonready receipt-to-account-state rejection",
            "Alpaca pagination rejection",
            "Alpaca stock-symbol mismatch rejection",
            "future-dated stock evidence rejection",
            "malformed Alpaca contract named-skip retention",
            "frozen-manifest tamper rejection",
            "requested put normalization without call admission",
            "exact pinned-account identity mismatch",
            "second-writer OS lock",
            "controller-owned position leg and quantity reconciliation",
            "stale pending-order exact-ID cancellation",
            "pre-window and Thursday force-flat clock",
            "observe-only force-flat rehearsal",
            "unguarded options proposer replay",
            "fixed-seed shuffled-settlement replay",
            "buy-and-hold equity baseline",
            "shuffled-return replay",
        ],
        "not_proven": [
            "options alpha",
            "profitability",
            "future returns",
            "broker connectivity",
            "production or live safety",
            "regulatory compliance",
            "official evaluation eligibility",
            "Friday pre-open option marking",
            "Thursday-expiry settlement timing",
            "user benefit",
        ],
    }
    receipt_path = ROOT / "evidence" / "verification-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
