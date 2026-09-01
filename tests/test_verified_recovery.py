from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from syncapp.apply import recover_interrupted_apply
from syncapp.git_repo import GitTreeEntry
from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class FakeAdoptedRepository:
    def __init__(self, commit: str, expected: bytes):
        self.commit = commit
        self.expected = expected

    def head(self) -> str:
        return self.commit

    def tree_entries(self, commit: str):
        return [GitTreeEntry("100644", "blob", "blob-1", "configuration.yaml")]

    def read_blob(self, object_id: str) -> bytes:
        return self.expected


class BrokenRepository(FakeAdoptedRepository):
    def head(self) -> str:
        raise RuntimeError("repository unavailable")


class VerifiedRecoveryTests(unittest.TestCase):
    def _verified_transaction(self, root: Path):
        live = root / "live"
        staging = root / "staging"
        tx_root = root / "transaction"
        live.mkdir()
        staging.mkdir()
        (live / "configuration.yaml").write_text("version: old\n", encoding="utf-8")
        (staging / "configuration.yaml").write_text("version: new\n", encoding="utf-8")
        commit = "a" * 40
        tx = FileTransaction.prepare(
            tx_root,
            live,
            staging,
            ApplyPlan(commit, ("configuration.yaml",), ()),
        )
        tx.record_supervisor_backup("backup-123")
        tx.apply()
        tx.mark("verified")
        settings = SimpleNamespace(
            transaction_dir=tx_root,
            source_dir=live,
            staging_dir=staging,
            manifest_path=root / "manifest.json",
            verify_timeout_seconds=30,
        )
        return settings, live, tx_root, commit

    def test_adopted_verified_transaction_with_live_drift_blocks_finalize_and_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings, live, tx_root, commit = self._verified_transaction(root)
            (live / "configuration.yaml").write_text("local: changed-after-crash\n", encoding="utf-8")
            repository = FakeAdoptedRepository(commit, b"version: new\n")

            with self.assertRaisesRegex(TransactionError, "refusing both finalize and rollback"):
                recover_interrupted_apply(settings, repository)  # type: ignore[arg-type]

            self.assertEqual(
                (live / "configuration.yaml").read_text(),
                "local: changed-after-crash\n",
            )
            active = FileTransaction.load_active(tx_root, live, settings.staging_dir)
            self.assertIsNotNone(active)
            self.assertEqual(active.state, "verified_drift")  # type: ignore[union-attr]

            with self.assertRaisesRegex(TransactionError, "automatic rollback is blocked"):
                recover_interrupted_apply(settings, repository)  # type: ignore[arg-type]
            self.assertTrue(tx_root.exists())

    def test_verified_transaction_with_unreadable_git_baseline_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings, live, tx_root, commit = self._verified_transaction(root)
            repository = BrokenRepository(commit, b"version: new\n")

            with self.assertRaisesRegex(TransactionError, "cannot prove the Git baseline"):
                recover_interrupted_apply(settings, repository)  # type: ignore[arg-type]

            self.assertEqual((live / "configuration.yaml").read_text(), "version: new\n")
            active = FileTransaction.load_active(tx_root, live, settings.staging_dir)
            self.assertIsNotNone(active)
            self.assertEqual(active.state, "verified")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
