from io import BytesIO
from pathlib import Path
import tarfile
import tempfile
import unittest

from syncapp.backup_archive import BackupArchiveError, verify_backup_archive


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_backup_archive(
    *,
    include_homeassistant: bool = True,
    inner_metadata_name: str = "./homeassistant.json",
    inner_data_name: str = "./data/configuration.yaml",
) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        _add_bytes(inner, inner_metadata_name, b'{"version":"2026.9.0"}\n')
        _add_bytes(inner, inner_data_name, b"homeassistant:\n")
    inner_bytes = inner_buffer.getvalue()

    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        _add_bytes(outer, "./backup.json", b'{"slug":"backup-slug"}\n')
        if include_homeassistant:
            _add_bytes(outer, "./homeassistant.tar.gz", inner_bytes)
    return outer_buffer.getvalue()


class BackupArchiveTests(unittest.TestCase):
    def _verify(self, payload: bytes) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "backup.tar"
            archive.write_bytes(payload)
            return verify_backup_archive(archive)

    def test_valid_supervisor_backup_is_structurally_verified_without_extracting(self):
        evidence = self._verify(make_backup_archive())
        self.assertTrue(evidence["outer_tar_readable"])
        self.assertTrue(evidence["backup_metadata_present"])
        self.assertTrue(evidence["homeassistant_archive_present"])
        self.assertTrue(evidence["homeassistant_archive_readable"])
        self.assertTrue(evidence["homeassistant_metadata_present"])
        self.assertEqual(evidence["homeassistant_data_files"], 1)

    def test_missing_homeassistant_component_archive_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "exactly one Home Assistant archive"):
            self._verify(make_backup_archive(include_homeassistant=False))

    def test_truncated_outer_tar_fails_closed(self):
        payload = make_backup_archive()
        with self.assertRaisesRegex(BackupArchiveError, "structurally readable"):
            self._verify(payload[:700])

    def test_unsafe_inner_member_path_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "unsafe member path"):
            self._verify(make_backup_archive(inner_data_name="../configuration.yaml"))

    def test_missing_homeassistant_metadata_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "exactly one homeassistant.json"):
            self._verify(make_backup_archive(inner_metadata_name="./other.json"))

    def test_missing_homeassistant_data_tree_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "configuration data files"):
            self._verify(make_backup_archive(inner_data_name="./other/configuration.yaml"))


if __name__ == "__main__":
    unittest.main()
