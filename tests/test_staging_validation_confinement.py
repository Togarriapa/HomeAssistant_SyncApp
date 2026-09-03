from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest import mock

import syncapp.staging as staging_module
from syncapp.staging import (
    StagingResult,
    StagingValidationError,
    assert_staging_integrity,
    validate_configuration_directory,
)


class StagingValidationConfinementTests(unittest.TestCase):
    def test_validates_nested_allowed_bytes_and_ignores_blocked_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "staging"
            nested = root / "packages"
            nested.mkdir(parents=True)
            payload = b"hello: world\n"
            (nested / "config.yaml").write_bytes(payload)
            (root / "secrets.yaml").write_text("password: hidden\n", encoding="utf-8")
            storage = root / ".storage"
            storage.mkdir()
            (storage / "core.config_entries").write_text("runtime", encoding="utf-8")

            result = validate_configuration_directory(root)

            self.assertEqual(result.file_count, 1)
            self.assertEqual(result.total_bytes, len(payload))
            self.assertEqual(
                result.file_sha256,
                (("packages/config.yaml", hashlib.sha256(payload).hexdigest()),),
            )

    def test_refuses_symlinked_allowed_parent_without_reading_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "configuration.yaml").write_text("outside: true\n", encoding="utf-8")
            (root / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(StagingValidationError, "not a regular file"):
                validate_configuration_directory(root)

            self.assertEqual(
                (outside / "configuration.yaml").read_text(encoding="utf-8"),
                "outside: true\n",
            )

    def test_refuses_byte_identical_root_replacement_during_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging"
            replacement = base / "replacement"
            root.mkdir()
            replacement.mkdir()
            (root / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            (replacement / "configuration.yaml").write_text("same: true\n", encoding="utf-8")
            original_read = os.read
            swapped = False

            def swapping_read(fd: int, size: int) -> bytes:
                nonlocal swapped
                data = original_read(fd, size)
                if data and not swapped:
                    swapped = True
                    root.rename(base / "detached")
                    replacement.rename(root)
                return data

            with mock.patch("syncapp.read_evidence.os.read", side_effect=swapping_read):
                with self.assertRaisesRegex(StagingValidationError, "root pathname was replaced"):
                    validate_configuration_directory(root)

    def test_refuses_path_set_change_during_syntax_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "staging"
            root.mkdir()
            (root / "configuration.yaml").write_text("safe: true\n", encoding="utf-8")
            original_validate = staging_module._validate_file_bytes
            injected = False

            def mutating_validate(relative: str, raw: bytes) -> None:
                nonlocal injected
                original_validate(relative, raw)
                if not injected:
                    injected = True
                    (root / "added.yaml").write_text("added: true\n", encoding="utf-8")

            with mock.patch.object(
                staging_module,
                "_validate_file_bytes",
                side_effect=mutating_validate,
            ):
                with self.assertRaisesRegex(StagingValidationError, "path set changed"):
                    validate_configuration_directory(root)

    def test_integrity_revalidation_binds_expected_root_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging"
            root.mkdir()
            payload = b"safe: true\n"
            (root / "configuration.yaml").write_bytes(payload)
            info = os.stat(root, follow_symlinks=False)
            staged = StagingResult(
                commit="a" * 40,
                file_count=1,
                total_bytes=len(payload),
                file_sha256=(("configuration.yaml", hashlib.sha256(payload).hexdigest()),),
                integrity_bound=True,
                root_identity=(info.st_dev, info.st_ino),
            )
            root.rename(base / "detached")
            root.mkdir()
            (root / "configuration.yaml").write_bytes(payload)

            with self.assertRaisesRegex(
                StagingValidationError,
                "root no longer identifies validated evidence",
            ):
                assert_staging_integrity(root, staged)


if __name__ == "__main__":
    unittest.main()
