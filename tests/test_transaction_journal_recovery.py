import json
from pathlib import Path
import tempfile
import unittest

from syncapp.journal_integrity import JournalIntegrityError
from syncapp.transaction import ApplyPlan, FileTransaction


class TransactionJournalRecoveryTests(unittest.TestCase):
    def test_corrupted_existed_set_preserves_live_state_and_recovery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            transaction_root = root / "transaction"
            live.mkdir()
            staging.mkdir()

            live_file = live / "configuration.yaml"
            live_file.write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")

            transaction = FileTransaction.prepare(
                transaction_root,
                live,
                staging,
                ApplyPlan("a" * 40, ("configuration.yaml",), ()),
            )
            transaction.record_supervisor_backup("backup-123")
            transaction.apply()
            self.assertEqual(live_file.read_text(encoding="utf-8"), "new: true\n")

            journal_path = transaction_root / FileTransaction.JOURNAL
            payload = json.loads(journal_path.read_text(encoding="utf-8"))
            payload["version"] = 1
            payload.pop("integrity_sha256", None)
            payload.pop("snapshot_sha256", None)
            payload["existed"] = []
            journal_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(JournalIntegrityError, "snapshot does not match"):
                FileTransaction.load_active(transaction_root, live, staging)

            self.assertEqual(live_file.read_text(encoding="utf-8"), "new: true\n")
            self.assertTrue(journal_path.exists())
            self.assertTrue((transaction_root / FileTransaction.SNAPSHOT / "configuration.yaml").exists())

    def test_v2_digest_tamper_is_rejected_before_state_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            transaction_root = root / "transaction"
            live.mkdir()
            staging.mkdir()

            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")
            transaction = FileTransaction.prepare(
                transaction_root,
                live,
                staging,
                ApplyPlan("b" * 40, ("configuration.yaml",), ()),
            )
            transaction.record_supervisor_backup("backup-123")

            journal_path = transaction_root / FileTransaction.JOURNAL
            payload = json.loads(journal_path.read_text(encoding="utf-8"))
            payload["state"] = "verified"
            journal_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(JournalIntegrityError, "digest does not match"):
                FileTransaction.load_active(transaction_root, live, staging)

            self.assertEqual(
                (live / "configuration.yaml").read_text(encoding="utf-8"),
                "old: true\n",
            )
            self.assertTrue(transaction_root.exists())

    def test_corrupted_snapshot_bytes_block_recovery_without_touching_live_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            transaction_root = root / "transaction"
            live.mkdir()
            staging.mkdir()

            live_file = live / "configuration.yaml"
            live_file.write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")
            transaction = FileTransaction.prepare(
                transaction_root,
                live,
                staging,
                ApplyPlan("c" * 40, ("configuration.yaml",), ()),
            )
            transaction.record_supervisor_backup("backup-123")
            transaction.apply()
            self.assertEqual(live_file.read_text(encoding="utf-8"), "new: true\n")

            snapshot = transaction_root / FileTransaction.SNAPSHOT / "configuration.yaml"
            snapshot.write_text("corrupted rollback bytes\n", encoding="utf-8")

            with self.assertRaisesRegex(JournalIntegrityError, "content digest does not match"):
                FileTransaction.load_active(transaction_root, live, staging)

            self.assertEqual(live_file.read_text(encoding="utf-8"), "new: true\n")
            self.assertTrue(transaction_root.exists())
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "corrupted rollback bytes\n")


if __name__ == "__main__":
    unittest.main()
