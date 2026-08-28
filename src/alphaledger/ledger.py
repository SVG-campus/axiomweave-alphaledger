from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


GENESIS_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class EvidenceLedger:
    """Small hash-chained ledger; Git history supplies durable append-only review."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._entries: list[dict[str, Any]] = []
        if path and path.exists():
            self._entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._entries)

    @property
    def head_hash(self) -> str:
        return self._entries[-1]["entry_hash"] if self._entries else GENESIS_HASH

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        unsigned = {
            "sequence": len(self._entries) + 1,
            "event_type": event_type,
            "previous_hash": self.head_hash,
            "payload_hash": digest(payload),
            "payload": payload,
        }
        entry = {**unsigned, "entry_hash": digest(unsigned)}
        self._entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json(entry) + "\n")
        return entry

    def verify(self) -> tuple[bool, tuple[str, ...]]:
        return verify_entries(self._entries)


def verify_entries(entries: Iterable[dict[str, Any]]) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    previous = GENESIS_HASH
    for expected_sequence, entry in enumerate(entries, start=1):
        if entry.get("sequence") != expected_sequence:
            failures.append(f"sequence {expected_sequence}: unexpected sequence number")
        if entry.get("previous_hash") != previous:
            failures.append(f"sequence {expected_sequence}: previous hash mismatch")
        if entry.get("payload_hash") != digest(entry.get("payload")):
            failures.append(f"sequence {expected_sequence}: payload hash mismatch")
        unsigned = {key: value for key, value in entry.items() if key != "entry_hash"}
        if entry.get("entry_hash") != digest(unsigned):
            failures.append(f"sequence {expected_sequence}: entry hash mismatch")
        previous = str(entry.get("entry_hash", ""))
    return len(failures) == 0, tuple(failures)
