import tempfile
import unittest
import uuid
from pathlib import Path

import app.core

from app.task.MaaFW.tools.notify.ledger import (
    MaaFWNotificationClaim,
    MaaFWNotificationLedger,
)


class MaafwNotificationLedgerIdempotencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.ledger_path = Path(self._temp.name) / "sub" / "ledger.sqlite3"

    def test_claim_is_idempotent_until_explicit_failure(self) -> None:
        ledger = MaaFWNotificationLedger(self.ledger_path)
        key = uuid.uuid4().hex

        first = ledger.claim(key)
        self.assertIsInstance(first, MaaFWNotificationClaim)
        self.assertEqual(ledger.status(key), "claimed")
        self.assertIsNone(ledger.claim(key))

        self.assertTrue(ledger.failed(first, "network_error"))
        self.assertEqual(ledger.status(key), "failed")

        retry = ledger.claim(key)
        self.assertIsInstance(retry, MaaFWNotificationClaim)
        self.assertNotEqual(retry.owner, first.owner)

    def test_delivered_claim_is_final(self) -> None:
        ledger = MaaFWNotificationLedger(self.ledger_path)
        key = uuid.uuid4().hex

        claim = ledger.claim(key)
        self.assertTrue(ledger.delivered(claim))
        self.assertEqual(ledger.status(key), "delivered")
        self.assertIsNone(ledger.claim(key))

    def test_state_persists_across_ledger_instances(self) -> None:
        ledger = MaaFWNotificationLedger(self.ledger_path)
        key = uuid.uuid4().hex
        claim = ledger.claim(key)
        ledger.delivered(claim)

        fresh = MaaFWNotificationLedger(self.ledger_path)
        self.assertEqual(fresh.status(key), "delivered")
        self.assertIsNone(fresh.claim(key))

    def test_finishing_with_forged_owner_is_rejected(self) -> None:
        ledger = MaaFWNotificationLedger(self.ledger_path)
        key = uuid.uuid4().hex
        claim = ledger.claim(key)

        forged = MaaFWNotificationClaim(key=key, owner="not-the-owner")
        self.assertFalse(ledger.delivered(forged))
        self.assertFalse(ledger.failed(forged, "boom"))
        self.assertEqual(ledger.status(key), "claimed")

        self.assertTrue(ledger.delivered(claim))


if __name__ == "__main__":
    unittest.main()
