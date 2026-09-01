from pathlib import Path
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from syncapp.live_fs import LiveFilesystem, LiveFilesystemError


class LiveFilesystemTests(unittest.TestCase):
    def test_replace_and_delete_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            source = root / "source.yaml"
            live.mkdir()
            (live / "packages").mkdir()
            (live / "packages" / "old.yaml").write_text("old: true\n", encoding="utf-8")
            source.write_text("new: true\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()

            fs = LiveFilesystem(live)
            fs.replace_from("packages/new.yaml", source, digest)
            self.assertEqual((live / "packages" / "new.yaml").read_text(), "new: true\n")
            self.assertTrue(fs.delete("packages/old.yaml"))
            self.assertFalse((live / "packages" / "old.yaml").exists())

    def test_symlink_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            outside = root / "outside"
            live.mkdir()
            outside.mkdir()
            (live / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(LiveFilesystemError):
                LiveFilesystem(live).exists_regular("packages/test.yaml")

    def test_symlink_leaf_is_not_treated_as_regular(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            outside = root / "outside.yaml"
            live.mkdir()
            outside.write_text("secret: true\n", encoding="utf-8")
            (live / "configuration.yaml").symlink_to(outside)

            with self.assertRaisesRegex(LiveFilesystemError, "regular file"):
                LiveFilesystem(live).exists_regular("configuration.yaml")

    def test_replace_refuses_preexisting_transaction_temp_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            outside = root / "outside.yaml"
            source = root / "source.yaml"
            live.mkdir()
            outside.write_text("outside: true\n", encoding="utf-8")
            source.write_text("new: true\n", encoding="utf-8")
            (live / ".configuration.yaml.syncapp-new").symlink_to(outside)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()

            with self.assertRaisesRegex(LiveFilesystemError, "pre-existing"):
                LiveFilesystem(live).replace_from("configuration.yaml", source, digest)
            self.assertEqual(outside.read_text(), "outside: true\n")

    def test_replace_and_delete_use_parent_dir_fd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            source = root / "source.yaml"
            live.mkdir()
            source.write_text("new: true\n", encoding="utf-8")
            (live / "old.yaml").write_text("old: true\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            real_replace = os.replace
            real_unlink = os.unlink
            replace_calls = []
            unlink_calls = []

            def tracked_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
                replace_calls.append((src, dst, src_dir_fd, dst_dir_fd))
                return real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

            def tracked_unlink(path, *, dir_fd=None):
                unlink_calls.append((path, dir_fd))
                return real_unlink(path, dir_fd=dir_fd)

            fs = LiveFilesystem(live)
            with mock.patch("syncapp.live_fs.os.replace", side_effect=tracked_replace), mock.patch(
                "syncapp.live_fs.os.unlink", side_effect=tracked_unlink
            ):
                fs.replace_from("configuration.yaml", source, digest)
                fs.delete("old.yaml")

            self.assertTrue(any(src_fd is not None and dst_fd is not None for _, _, src_fd, dst_fd in replace_calls))
            self.assertTrue(any(path == "old.yaml" and dir_fd is not None for path, dir_fd in unlink_calls))


if __name__ == "__main__":
    unittest.main()
