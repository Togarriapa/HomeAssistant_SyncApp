from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.live_fs import LiveFilesystem, LiveFilesystemError


class SnapshotCaptureWriteConfinementTests(unittest.TestCase):
    @staticmethod
    def _identity(path: Path) -> tuple[int, int]:
        info = os.stat(path, follow_symlinks=False)
        return info.st_dev, info.st_ino

    @staticmethod
    def _live_with_nested_file(root: Path) -> tuple[Path, bytes]:
        live = root / "live"
        source = live / "custom_components" / "demo.py"
        source.parent.mkdir(parents=True)
        content = b"VALUE = 'safe'\n"
        source.write_bytes(content)
        return live, content

    def test_nested_snapshot_parent_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, _ = self._live_with_nested_file(root)
            snapshot = root / "snapshot"
            outside = root / "outside"
            snapshot.mkdir()
            outside.mkdir()
            (snapshot / "custom_components").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(
                LiveFilesystemError,
                "unsafe rollback snapshot parent",
            ):
                LiveFilesystem(live).copy_to(
                    "custom_components/demo.py",
                    snapshot / "custom_components" / "demo.py",
                    expected_destination_root_identity=self._identity(snapshot),
                )

            self.assertTrue((snapshot / "custom_components").is_symlink())
            self.assertFalse((outside / "demo.py").exists())

    def test_replaced_snapshot_root_is_rejected_before_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, _ = self._live_with_nested_file(root)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            expected_identity = self._identity(snapshot)

            original = root / "snapshot.original"
            snapshot.rename(original)
            snapshot.mkdir()
            sentinel = snapshot / "sentinel"
            sentinel.write_text("replacement\n", encoding="utf-8")

            with self.assertRaisesRegex(
                LiveFilesystemError,
                "root no longer identifies prepared evidence",
            ):
                LiveFilesystem(live).copy_to(
                    "custom_components/demo.py",
                    snapshot / "custom_components" / "demo.py",
                    expected_destination_root_identity=expected_identity,
                )

            self.assertTrue(sentinel.exists())
            self.assertFalse((snapshot / "custom_components").exists())
            self.assertEqual(list(original.iterdir()), [])

    def test_root_swap_after_destination_open_fails_and_removes_only_owned_leaf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, _ = self._live_with_nested_file(root)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            expected_identity = self._identity(snapshot)
            destination = snapshot / "custom_components" / "demo.py"
            original_context = LiveFilesystem._open_snapshot_destination
            moved = root / "snapshot.original"
            swapped = False

            @contextmanager
            def swap_after_open(
                filesystem: LiveFilesystem,
                relative: str,
                target: Path,
                expected_root_identity: tuple[int, int] | None = None,
            ):
                nonlocal swapped
                with original_context(
                    filesystem,
                    relative,
                    target,
                    expected_root_identity,
                ) as target_fd:
                    snapshot.rename(moved)
                    snapshot.mkdir()
                    (snapshot / "sentinel").write_text("replacement\n", encoding="utf-8")
                    swapped = True
                    yield target_fd

            with patch.object(
                LiveFilesystem,
                "_open_snapshot_destination",
                new=swap_after_open,
            ):
                with self.assertRaisesRegex(
                    LiveFilesystemError,
                    "root changed while being captured",
                ):
                    LiveFilesystem(live).copy_to(
                        "custom_components/demo.py",
                        destination,
                        expected_destination_root_identity=expected_identity,
                    )

            self.assertTrue(swapped)
            self.assertEqual((snapshot / "sentinel").read_text(), "replacement\n")
            self.assertFalse((snapshot / "custom_components").exists())
            self.assertFalse((moved / "custom_components" / "demo.py").exists())

    def test_normal_nested_capture_returns_exact_copied_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, content = self._live_with_nested_file(root)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            destination = snapshot / "custom_components" / "demo.py"

            digest = LiveFilesystem(live).copy_to(
                "custom_components/demo.py",
                destination,
                expected_destination_root_identity=self._identity(snapshot),
            )

            self.assertEqual(destination.read_bytes(), content)
            self.assertEqual(digest, hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
