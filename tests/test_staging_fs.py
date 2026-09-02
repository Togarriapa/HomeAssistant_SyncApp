import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from syncapp.staging_fs import StagingFilesystem, StagingFilesystemError


class StagingFilesystemTests(unittest.TestCase):
    def test_nested_regular_write_is_descriptor_confined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "staging.new"
            root.mkdir()
            content = b"automation: []\n"
            digest = hashlib.sha256(content).hexdigest()

            with StagingFilesystem(root) as filesystem:
                filesystem.write_new("packages/remote.yaml", content, digest)
                filesystem.assert_path_identity()

            self.assertEqual((root / "packages" / "remote.yaml").read_bytes(), content)

    def test_symlink_parent_is_rejected_without_outside_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging.new"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "packages").symlink_to(outside, target_is_directory=True)
            content = b"automation: []\n"
            digest = hashlib.sha256(content).hexdigest()

            with StagingFilesystem(root) as filesystem:
                with self.assertRaisesRegex(
                    StagingFilesystemError, "unsafe staging parent"
                ):
                    filesystem.write_new("packages/remote.yaml", content, digest)

            self.assertFalse((outside / "remote.yaml").exists())

    def test_preexisting_leaf_symlink_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging.new"
            outside = base / "outside.yaml"
            root.mkdir()
            outside.write_bytes(b"outside\n")
            (root / "configuration.yaml").symlink_to(outside)
            content = b"homeassistant:\n"
            digest = hashlib.sha256(content).hexdigest()

            with StagingFilesystem(root) as filesystem:
                with self.assertRaisesRegex(
                    StagingFilesystemError, "pre-existing staging leaf"
                ):
                    filesystem.write_new("configuration.yaml", content, digest)

            self.assertEqual(outside.read_bytes(), b"outside\n")

    def test_root_path_swap_cannot_redirect_open_descriptor_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging.new"
            opened = base / "staging-opened"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            content = b"homeassistant:\n"
            digest = hashlib.sha256(content).hexdigest()

            with StagingFilesystem(root) as filesystem:
                root.rename(opened)
                root.symlink_to(outside, target_is_directory=True)
                filesystem.write_new("configuration.yaml", content, digest)

                self.assertEqual((opened / "configuration.yaml").read_bytes(), content)
                self.assertFalse((outside / "configuration.yaml").exists())
                with self.assertRaisesRegex(
                    StagingFilesystemError, "pathname was replaced"
                ):
                    filesystem.assert_path_identity()
                filesystem.assert_path_identity(opened)

    def test_parent_path_swap_before_open_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "staging.new"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "packages").mkdir()
            content = b"automation: []\n"
            digest = hashlib.sha256(content).hexdigest()
            real_open = os.open
            swapped = False

            def swap_then_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if path == "packages" and dir_fd is not None and not swapped:
                    swapped = True
                    packages = root / "packages"
                    moved = root / "packages-opened"
                    packages.rename(moved)
                    packages.symlink_to(outside, target_is_directory=True)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with StagingFilesystem(root) as filesystem:
                with unittest.mock.patch("syncapp.staging_fs.os.open", side_effect=swap_then_open):
                    with self.assertRaisesRegex(
                        StagingFilesystemError, "unsafe staging parent"
                    ):
                        filesystem.write_new("packages/remote.yaml", content, digest)

            self.assertTrue(swapped)
            self.assertFalse((outside / "remote.yaml").exists())
            self.assertFalse((root / "packages-opened" / "remote.yaml").exists())


if __name__ == "__main__":
    unittest.main()
