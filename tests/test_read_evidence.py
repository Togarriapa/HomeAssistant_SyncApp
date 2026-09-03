from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from syncapp.read_evidence import PinnedReadRoot, ReadEvidenceError


class PinnedReadRootTests(unittest.TestCase):
    def test_hashes_nested_regular_file_and_checks_expected_root_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            nested = root / "packages"
            nested.mkdir(parents=True)
            payload = b"hello: world\n"
            (nested / "config.yaml").write_bytes(payload)
            info = os.stat(root, follow_symlinks=False)

            with PinnedReadRoot(
                root,
                expected_identity=(info.st_dev, info.st_ino),
                label="staging",
            ) as evidence:
                self.assertEqual(
                    evidence.sha256("packages/config.yaml"),
                    hashlib.sha256(payload).hexdigest(),
                )

    def test_refuses_symlinked_parent_without_reading_outside_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "config.yaml").write_text("secret: outside\n", encoding="utf-8")
            (root / "packages").symlink_to(outside, target_is_directory=True)

            with PinnedReadRoot(root, label="staging") as evidence:
                with self.assertRaises(ReadEvidenceError):
                    evidence.sha256("packages/config.yaml")

            self.assertEqual(
                (outside / "config.yaml").read_text(encoding="utf-8"),
                "secret: outside\n",
            )

    def test_refuses_byte_identical_root_replacement_during_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            root.mkdir()
            (root / "config.yaml").write_text("same: true\n", encoding="utf-8")
            replacement = base / "replacement"
            replacement.mkdir()
            (replacement / "config.yaml").write_text("same: true\n", encoding="utf-8")
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

            with PinnedReadRoot(root, label="staging") as evidence:
                with mock.patch("syncapp.read_evidence.os.read", side_effect=swapping_read):
                    with self.assertRaisesRegex(ReadEvidenceError, "root pathname was replaced"):
                        evidence.sha256("config.yaml")

            self.assertEqual((root / "config.yaml").read_text(), "same: true\n")
            self.assertEqual((base / "detached" / "config.yaml").read_text(), "same: true\n")

    def test_refuses_byte_identical_leaf_replacement_during_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            leaf = root / "config.yaml"
            leaf.write_text("same: true\n", encoding="utf-8")
            original_read = os.read
            swapped = False

            def swapping_read(fd: int, size: int) -> bytes:
                nonlocal swapped
                data = original_read(fd, size)
                if data and not swapped:
                    swapped = True
                    leaf.rename(root / "detached.yaml")
                    leaf.write_text("same: true\n", encoding="utf-8")
                return data

            with PinnedReadRoot(root, label="rollback snapshot") as evidence:
                with mock.patch("syncapp.read_evidence.os.read", side_effect=swapping_read):
                    with self.assertRaisesRegex(ReadEvidenceError, "file config.yaml was replaced"):
                        evidence.sha256("config.yaml")

    def test_refuses_unsafe_relative_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            with PinnedReadRoot(root) as evidence:
                for relative in ("../outside", "/absolute", "."):
                    with self.subTest(relative=relative):
                        with self.assertRaises(ReadEvidenceError):
                            evidence.sha256(relative)


if __name__ == "__main__":
    unittest.main()
