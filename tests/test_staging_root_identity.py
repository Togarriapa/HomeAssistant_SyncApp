from pathlib import Path
import hashlib
import os
import tempfile
import unittest

from syncapp.staging import StagingResult, StagingValidationError, assert_staging_integrity
from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class StagingRootIdentityTests(unittest.TestCase):
    def test_byte_identical_replacement_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            staging.mkdir()
            content = b"safe: true\n"
            (staging / "configuration.yaml").write_bytes(content)
            info = os.stat(staging, follow_symlinks=False)
            staged = StagingResult(
                commit="a" * 40,
                file_count=1,
                total_bytes=len(content),
                file_sha256=(("configuration.yaml", hashlib.sha256(content).hexdigest()),),
                integrity_bound=True,
                root_identity=(info.st_dev, info.st_ino),
            )

            original = root / "staging.original"
            staging.rename(original)
            staging.mkdir()
            (staging / "configuration.yaml").write_bytes(content)

            with self.assertRaisesRegex(StagingValidationError, "root pathname was replaced"):
                assert_staging_integrity(staging, staged)

            self.assertEqual((original / "configuration.yaml").read_bytes(), content)
            self.assertEqual((staging / "configuration.yaml").read_bytes(), content)

    def test_apply_rejects_byte_identical_root_swap_after_transaction_prepare(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            transaction_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            content = b"safe: true\n"
            (staging / "configuration.yaml").write_bytes(content)
            info = os.stat(staging, follow_symlinks=False)

            transaction = FileTransaction.prepare(
                transaction_root,
                live,
                staging,
                ApplyPlan("c" * 40, ("configuration.yaml",), ()),
                staging_root_identity=(info.st_dev, info.st_ino),
            )
            transaction.record_supervisor_backup("backup-123")

            original = root / "staging.original"
            staging.rename(original)
            staging.mkdir()
            (staging / "configuration.yaml").write_bytes(content)

            with self.assertRaisesRegex(TransactionError, "no longer identifies validated evidence"):
                transaction.apply()

            self.assertFalse((live / "configuration.yaml").exists())
            self.assertTrue(transaction_root.exists())

    def test_legacy_unbound_fixture_still_uses_hash_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            content = b"safe: true\n"
            (staging / "configuration.yaml").write_bytes(content)
            staged = StagingResult(
                commit="b" * 40,
                file_count=1,
                total_bytes=len(content),
                file_sha256=(("configuration.yaml", hashlib.sha256(content).hexdigest()),),
                integrity_bound=True,
            )

            assert_staging_integrity(staging, staged)


if __name__ == "__main__":
    unittest.main()
