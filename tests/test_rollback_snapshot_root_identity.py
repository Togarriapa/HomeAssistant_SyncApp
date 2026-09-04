from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from syncapp.live_fs import LiveFilesystem
from syncapp.recovery_loader import load_active_transaction
from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class RollbackSnapshotRootIdentityTests(unittest.TestCase):
    def _prepared_applied_transaction(self, root: Path) -> FileTransaction:
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
            ApplyPlan("a" * 40, ("configuration.yaml",), ()),
        )
        transaction.record_supervisor_backup("backup-123")
        transaction.apply()
        self.assertEqual((live / "configuration.yaml").read_text(), "new: true\n")
        return transaction

    @staticmethod
    def _replace_snapshot_root_byte_identically(transaction: FileTransaction) -> Path:
        original = transaction.root / "snapshot.original"
        transaction.snapshot_dir.rename(original)
        transaction.snapshot_dir.mkdir()
        for source in original.rglob("*"):
            relative = source.relative_to(original)
            destination = transaction.snapshot_dir / relative
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        return original

    def test_in_process_rollback_rejects_root_swap_after_hash_precheck(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepared_applied_transaction(root)
            original_replace = LiveFilesystem.replace_from
            swapped = False

            def swap_then_replace(
                filesystem: LiveFilesystem,
                relative: str,
                source: Path,
                expected_sha256: str,
                *,
                expected_source_root_identity: tuple[int, int] | None = None,
            ) -> None:
                nonlocal swapped
                if not swapped and source.parent == transaction.snapshot_dir:
                    self._replace_snapshot_root_byte_identically(transaction)
                    swapped = True
                original_replace(
                    filesystem,
                    relative,
                    transaction.snapshot_dir / relative,
                    expected_sha256,
                    expected_source_root_identity=expected_source_root_identity,
                )

            with patch(
                "syncapp.transaction.LiveFilesystem.replace_from",
                new=swap_then_replace,
            ):
                with self.assertRaisesRegex(
                    TransactionError,
                    "no longer identifies validated evidence",
                ):
                    transaction.rollback()

            self.assertTrue(swapped)
            self.assertEqual(
                (transaction.source_dir / "configuration.yaml").read_text(),
                "new: true\n",
            )
            self.assertTrue(transaction.root.exists())
            self.assertEqual(transaction.state, "rollback_failed")

    def test_recovery_loader_carries_validated_snapshot_identity_into_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepared_applied_transaction(root)
            expected_identity = transaction.snapshot_root_identity
            self.assertIsNotNone(expected_identity)

            loaded = load_active_transaction(
                transaction.root,
                transaction.source_dir,
                transaction.staging_dir,
            )
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.snapshot_root_identity, expected_identity)

            self._replace_snapshot_root_byte_identically(loaded)
            with self.assertRaisesRegex(
                TransactionError,
                "rollback snapshot root no longer identifies validated evidence",
            ):
                loaded.rollback()

            self.assertEqual(
                (loaded.source_dir / "configuration.yaml").read_text(),
                "new: true\n",
            )
            self.assertTrue(loaded.root.exists())


if __name__ == "__main__":
    unittest.main()
