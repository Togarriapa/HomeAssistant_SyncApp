from pathlib import Path
import json
import tempfile
import unittest

from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class TransactionJournalWriteConfinementTests(unittest.TestCase):
    @staticmethod
    def _prepare(root: Path) -> FileTransaction:
        live = root / "live"
        staging = root / "staging"
        transaction_root = root / "transaction"
        live.mkdir()
        staging.mkdir()
        (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
        (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")
        return FileTransaction.prepare(
            transaction_root,
            live,
            staging,
            ApplyPlan("a" * 40, ("configuration.yaml",), ()),
        )

    def test_replaced_transaction_root_cannot_receive_later_journal_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root)
            original = root / "transaction.original"
            transaction.root.rename(original)
            transaction.root.mkdir()
            sentinel = transaction.root / "sentinel"
            sentinel.write_text("outside transaction evidence\n", encoding="utf-8")

            with self.assertRaisesRegex(
                TransactionError,
                "no longer identifies the validated transaction evidence",
            ):
                transaction.mark("backed_up")

            self.assertTrue(sentinel.exists())
            self.assertFalse((transaction.root / FileTransaction.JOURNAL).exists())
            original_journal = json.loads(
                (original / FileTransaction.JOURNAL).read_text(encoding="utf-8")
            )
            self.assertEqual(original_journal["state"], "prepared")
            self.assertEqual(transaction.state, "prepared")

    def test_preexisting_journal_temp_symlink_is_refused_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root)
            outside = root / "outside.txt"
            outside.write_text("do not touch\n", encoding="utf-8")
            temporary_leaf = transaction.root / "journal.json.tmp"
            temporary_leaf.symlink_to(outside)

            with self.assertRaisesRegex(
                TransactionError,
                "pre-existing transaction journal temporary file",
            ):
                transaction.record_supervisor_backup("backup-123")

            self.assertTrue(temporary_leaf.is_symlink())
            self.assertEqual(outside.read_text(encoding="utf-8"), "do not touch\n")
            journal = json.loads(transaction.journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["state"], "prepared")
            self.assertEqual(transaction.state, "prepared")
            self.assertIsNone(transaction.supervisor_backup)


if __name__ == "__main__":
    unittest.main()
