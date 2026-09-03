from pathlib import Path
import os
import tempfile
import unittest

from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class TransactionRevalidationConfinementTests(unittest.TestCase):
    def _prepare_nested(self, root: Path) -> tuple[FileTransaction, Path, Path, Path]:
        live = root / "live"
        staging = root / "staging"
        tx_root = root / "transaction"
        (live / "packages").mkdir(parents=True)
        (staging / "packages").mkdir(parents=True)
        (live / "packages" / "config.yaml").write_text("old: true\n", encoding="utf-8")
        (staging / "packages" / "config.yaml").write_text("new: true\n", encoding="utf-8")
        staging_info = os.stat(staging, follow_symlinks=False)
        tx = FileTransaction.prepare(
            tx_root,
            live,
            staging,
            ApplyPlan("a" * 40, ("packages/config.yaml",), ()),
            staging_root_identity=(staging_info.st_dev, staging_info.st_ino),
        )
        return tx, live, staging, tx_root

    def test_staging_root_byte_identical_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx, _, staging, _ = self._prepare_nested(root)
            detached = root / "staging.detached"
            staging.rename(detached)
            (staging / "packages").mkdir(parents=True)
            (staging / "packages" / "config.yaml").write_text("new: true\n", encoding="utf-8")

            with self.assertRaisesRegex(TransactionError, "staging root no longer identifies"):
                tx.assert_staging_unchanged()

    def test_staging_parent_symlink_is_rejected_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx, _, staging, _ = self._prepare_nested(root)
            outside = root / "outside"
            outside.mkdir()
            (outside / "config.yaml").write_text("new: true\n", encoding="utf-8")
            (staging / "packages").rename(staging / "packages.detached")
            (staging / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(TransactionError, "integrity check failed safely"):
                tx.assert_staging_unchanged()

            self.assertEqual((outside / "config.yaml").read_text(), "new: true\n")

    def test_snapshot_root_byte_identical_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx, _, _, tx_root = self._prepare_nested(root)
            snapshot = tx_root / "snapshot"
            detached = tx_root / "snapshot.detached"
            snapshot.rename(detached)
            (snapshot / "packages").mkdir(parents=True)
            (snapshot / "packages" / "config.yaml").write_text("old: true\n", encoding="utf-8")

            with self.assertRaisesRegex(TransactionError, "rollback snapshot root no longer identifies"):
                tx.assert_snapshot_unchanged()

    def test_snapshot_parent_symlink_is_rejected_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx, _, _, tx_root = self._prepare_nested(root)
            snapshot = tx_root / "snapshot"
            outside = root / "outside"
            outside.mkdir()
            (outside / "config.yaml").write_text("old: true\n", encoding="utf-8")
            (snapshot / "packages").rename(snapshot / "packages.detached")
            (snapshot / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(TransactionError, "integrity check failed safely"):
                tx.assert_snapshot_unchanged()

            self.assertEqual((outside / "config.yaml").read_text(), "old: true\n")


if __name__ == "__main__":
    unittest.main()
