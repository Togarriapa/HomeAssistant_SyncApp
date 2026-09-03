from pathlib import Path
import hashlib
import os
import tempfile
import unittest

from syncapp.staging import StagingResult, StagingValidationError, assert_staging_integrity


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
