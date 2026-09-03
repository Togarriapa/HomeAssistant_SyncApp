from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.mirror import ManifestError, load_manifest, save_manifest


class ManifestDurabilityTests(unittest.TestCase):
    def test_manifest_file_and_parent_directory_are_fsynced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed_paths.json"
            with patch("syncapp.mirror.os.fsync") as fsync:
                save_manifest(path, {"configuration.yaml"})

            self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual(load_manifest(path), {"configuration.yaml"})

    def test_replace_failure_preserves_previous_manifest_and_cleans_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed_paths.json"
            save_manifest(path, {"configuration.yaml"})

            with patch("syncapp.mirror.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(ManifestError, "persisted durably"):
                    save_manifest(path, {"automations.yaml"})

            self.assertEqual(load_manifest(path), {"configuration.yaml"})
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_directory_fsync_failure_is_not_reported_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed_paths.json"

            with patch(
                "syncapp.mirror._fsync_directory",
                side_effect=OSError("directory fsync failed"),
            ):
                with self.assertRaisesRegex(ManifestError, "persisted durably"):
                    save_manifest(path, {"configuration.yaml"})

            # The rename may already have occurred, but callers are told durability
            # was not proven so verified transaction evidence can be preserved/retried.
            self.assertTrue(path.exists())

    def test_preexisting_temporary_symlink_cannot_redirect_manifest_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "managed_paths.json"
            outside = root / "outside.yaml"
            outside.write_text("must survive\n", encoding="utf-8")
            temporary_path = path.with_suffix(".tmp")
            temporary_path.symlink_to(outside)

            with self.assertRaisesRegex(ManifestError, "pre-existing.*temporary"):
                save_manifest(path, {"configuration.yaml"})

            self.assertEqual(outside.read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(temporary_path.is_symlink())
            self.assertFalse(path.exists())

    def test_manifest_symlink_is_refused_without_reading_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "managed_paths.json"
            outside = root / "outside.json"
            outside.write_text('["configuration.yaml"]\n', encoding="utf-8")
            path.symlink_to(outside)

            with self.assertRaisesRegex(ManifestError, "opened safely"):
                load_manifest(path)

            self.assertEqual(outside.read_text(encoding="utf-8"), '["configuration.yaml"]\n')


if __name__ == "__main__":
    unittest.main()
