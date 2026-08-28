from __future__ import annotations

import copy
import unittest

from alphaledger.ledger import EvidenceLedger, verify_entries


class EvidenceLedgerTests(unittest.TestCase):
    def test_valid_chain_verifies(self) -> None:
        ledger = EvidenceLedger()
        ledger.append("one", {"value": 1})
        ledger.append("two", {"value": 2})

        ok, failures = ledger.verify()
        self.assertTrue(ok)
        self.assertEqual(failures, ())

    def test_payload_tampering_is_detected(self) -> None:
        ledger = EvidenceLedger()
        ledger.append("one", {"decision": "abstain"})
        tampered = copy.deepcopy(list(ledger.entries))
        tampered[0]["payload"]["decision"] = "buy"

        ok, failures = verify_entries(tampered)
        self.assertFalse(ok)
        self.assertTrue(any("payload hash mismatch" in failure for failure in failures))

    def test_reordering_is_detected(self) -> None:
        ledger = EvidenceLedger()
        ledger.append("one", {"value": 1})
        ledger.append("two", {"value": 2})
        reversed_entries = list(reversed(ledger.entries))

        ok, failures = verify_entries(reversed_entries)
        self.assertFalse(ok)
        self.assertTrue(any("sequence" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
