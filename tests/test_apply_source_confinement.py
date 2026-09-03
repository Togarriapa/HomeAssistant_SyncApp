from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from syncapp.live_fs import LiveFilesystem, LiveFilesystemError


class ApplySourceConfinementTests(unittest.TestCase):
    def test_nested_source_parent_swap_fails_before_live_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            outside = root / "outside"
            live.mkdir()
            staging.mkdir()
            outside.mkdir()
            (staging / "packages").mkdir()
            source = staging / "packages" / "configuration.yaml"
            source.write_text("new: true\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            moved = staging / "packages-opened"
            real_read = os.read
            swapped = False

            def read_then_swap(fd: int, size: int) -> bytes:
                nonlocal swapped
                chunk = real_read(fd, size)
                if chunk and not swapped:
                    (staging / "packages").rename(moved)
                    (staging / "packages").symlink_to(outside, target_is_directory=True)
                    swapped = True
                return chunk

            with mock.patch("syncapp.live_fs.os.read", side_effect=read_then_swap):
                with self.assertRaisesRegex(LiveFilesystemError, "source parent changed"):
                    LiveFilesystem(live).replace_from(
                        "packages/configuration.yaml", source, digest
                    )

            self.assertFalse((live / "packages" / "configuration.yaml").exists())
            self.assertFalse((outside / "configuration.yaml").exists())
            self.assertEqual((moved / "configuration.yaml").read_text(), "new: true\n")
            self.assertFalse((live / "packages" / ".configuration.yaml.syncapp-new").exists())

    def test_source_root_swap_fails_before_live_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            moved = root / "staging-opened"
            outside = root / "outside"
            live.mkdir()
            staging.mkdir()
            outside.mkdir()
            source = staging / "configuration.yaml"
            source.write_text("new: true\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            real_read = os.read
            swapped = False

            def read_then_swap(fd: int, size: int) -> bytes:
                nonlocal swapped
                chunk = real_read(fd, size)
                if chunk and not swapped:
                    staging.rename(moved)
                    staging.symlink_to(outside, target_is_directory=True)
                    swapped = True
                return chunk

            with mock.patch("syncapp.live_fs.os.read", side_effect=read_then_swap):
                with self.assertRaisesRegex(LiveFilesystemError, "source root changed"):
                    LiveFilesystem(live).replace_from("configuration.yaml", source, digest)

            self.assertFalse((live / "configuration.yaml").exists())
            self.assertFalse((outside / "configuration.yaml").exists())
            self.assertEqual((moved / "configuration.yaml").read_text(), "new: true\n")
            self.assertFalse((live / ".configuration.yaml.syncapp-new").exists())

    def test_symlinked_source_parent_is_refused_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            outside = root / "outside"
            live.mkdir()
            staging.mkdir()
            outside.mkdir()
            (outside / "configuration.yaml").write_text("new: true\n", encoding="utf-8")
            (staging / "packages").symlink_to(outside, target_is_directory=True)
            source = staging / "packages" / "configuration.yaml"
            digest = hashlib.sha256(b"new: true\n").hexdigest()

            with self.assertRaisesRegex(LiveFilesystemError, "unsafe replacement source parent"):
                LiveFilesystem(live).replace_from(
                    "packages/configuration.yaml", source, digest
                )

            self.assertFalse((live / "packages" / "configuration.yaml").exists())
            self.assertEqual((outside / "configuration.yaml").read_text(), "new: true\n")

    def test_byte_identical_regular_source_still_replaces_normally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            live.mkdir()
            staging.mkdir()
            (staging / "packages").mkdir()
            source = staging / "packages" / "configuration.yaml"
            source.write_text("new: true\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()

            LiveFilesystem(live).replace_from("packages/configuration.yaml", source, digest)

            self.assertEqual(
                (live / "packages" / "configuration.yaml").read_text(encoding="utf-8"),
                "new: true\n",
            )


if __name__ == "__main__":
    unittest.main()
