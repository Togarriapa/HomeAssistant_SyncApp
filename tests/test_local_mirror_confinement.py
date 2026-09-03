from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from syncapp.mirror import ManifestError, mirror_local_configuration


class LocalMirrorConfinementTests(unittest.TestCase):
    def test_regular_nested_configuration_is_mirrored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live"
            destination = root / "repository"
            (source / "packages").mkdir(parents=True)
            destination.mkdir()
            payload = b"automation: []\n"
            (source / "packages" / "remote.yaml").write_bytes(payload)

            managed = mirror_local_configuration(source, destination, set())

            self.assertEqual(managed, {"packages/remote.yaml"})
            self.assertEqual((destination / "packages" / "remote.yaml").read_bytes(), payload)

    def test_symlinked_live_parent_is_rejected_without_copying_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live"
            destination = root / "repository"
            outside = root / "outside"
            source.mkdir()
            destination.mkdir()
            outside.mkdir()
            (outside / "secret.yaml").write_text("secret: outside\n", encoding="utf-8")
            (source / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ManifestError, "not a regular file"):
                mirror_local_configuration(source, destination, set())

            self.assertFalse((destination / "packages").exists())
            self.assertEqual((outside / "secret.yaml").read_text(), "secret: outside\n")

    def test_live_leaf_swap_during_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live"
            destination = root / "repository"
            source.mkdir()
            destination.mkdir()
            leaf = source / "configuration.yaml"
            leaf.write_text("safe: true\n", encoding="utf-8")
            original_read = os.read
            swapped = False

            def swapping_read(fd: int, size: int) -> bytes:
                nonlocal swapped
                data = original_read(fd, size)
                if data and not swapped:
                    swapped = True
                    leaf.rename(source / "detached.yaml")
                    leaf.write_text("secret: changed\n", encoding="utf-8")
                return data

            with mock.patch("syncapp.read_evidence.os.read", side_effect=swapping_read):
                with self.assertRaisesRegex(ManifestError, "changed while being read|replaced while being read"):
                    mirror_local_configuration(source, destination, set())

            self.assertFalse((destination / "configuration.yaml").exists())

    def test_symlinked_mirror_parent_cannot_redirect_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live"
            destination = root / "repository"
            outside = root / "outside"
            (source / "packages").mkdir(parents=True)
            destination.mkdir()
            outside.mkdir()
            (source / "packages" / "config.yaml").write_text("safe: true\n", encoding="utf-8")
            (destination / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(ManifestError, "unsafe mirror parent"):
                mirror_local_configuration(source, destination, set())

            self.assertFalse((outside / "config.yaml").exists())

    def test_nonregular_mirror_leaf_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live"
            destination = root / "repository"
            outside = root / "outside.yaml"
            source.mkdir()
            destination.mkdir()
            (source / "configuration.yaml").write_text("safe: true\n", encoding="utf-8")
            outside.write_text("must survive\n", encoding="utf-8")
            (destination / "configuration.yaml").symlink_to(outside)

            with self.assertRaisesRegex(ManifestError, "non-regular mirror leaf"):
                mirror_local_configuration(source, destination, set())

            self.assertEqual(outside.read_text(), "must survive\n")


if __name__ == "__main__":
    unittest.main()
