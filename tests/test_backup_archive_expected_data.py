from io import BytesIO
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from syncapp.backup_archive import BackupArchiveError, verify_backup_archive


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_archive(files: list[tuple[str, bytes]]) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        add_bytes(inner, "homeassistant.json", b'{"version":"2026.9.0"}\n')
        for relative, data in files:
            add_bytes(inner, f"data/{relative}", data)
    metadata = json.dumps(
        {
            "slug": "backup-slug",
            "name": "SyncApp test",
            "type": "partial",
            "homeassistant": {"version": "2026.9.0", "exclude_database": True},
        }
    ).encode()
    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        add_bytes(outer, "backup.json", metadata)
        add_bytes(outer, "homeassistant.tar.gz", inner_buffer.getvalue())
    return outer_buffer.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ExpectedBackupDataTests(unittest.TestCase):
    def verify(self, payload: bytes, expected: dict[str, str]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backup.tar"
            path.write_bytes(payload)
            return verify_backup_archive(path, expected_data_sha256=expected)

    def test_exact_bytes_for_all_expected_paths_are_verified(self):
        config = b"homeassistant:\n"
        package = b"sensor:\n"
        result = self.verify(
            make_archive([("configuration.yaml", config), ("packages/test.yaml", package)]),
            {"configuration.yaml": sha(config), "packages/test.yaml": sha(package)},
        )
        self.assertEqual(result["expected_live_files"], 2)
        self.assertTrue(result["expected_live_files_byte_verified"])
        self.assertFalse(any("sha" in key.lower() for key in result))

    def test_missing_or_mismatched_expected_bytes_fail_closed(self):
        config = b"homeassistant:\n"
        with self.assertRaisesRegex(BackupArchiveError, "missing one or more expected"):
            self.verify(
                make_archive([("configuration.yaml", config)]),
                {"configuration.yaml": sha(config), "packages/test.yaml": sha(b"sensor:\n")},
            )
        with self.assertRaisesRegex(BackupArchiveError, "does not match live file bytes"):
            self.verify(
                make_archive([("configuration.yaml", b"different:\n")]),
                {"configuration.yaml": sha(config)},
            )

    def test_duplicate_expected_archive_path_fails_closed(self):
        config = b"homeassistant:\n"
        with self.assertRaisesRegex(BackupArchiveError, "duplicate expected data path"):
            self.verify(
                make_archive([("configuration.yaml", config), ("configuration.yaml", config)]),
                {"configuration.yaml": sha(config)},
            )

    def test_expected_path_and_digest_are_validated(self):
        payload = make_archive([("configuration.yaml", b"homeassistant:\n")])
        with self.assertRaisesRegex(BackupArchiveError, "path is unsafe"):
            self.verify(payload, {"../configuration.yaml": "0" * 64})
        with self.assertRaisesRegex(BackupArchiveError, "digest is invalid"):
            self.verify(payload, {"configuration.yaml": "bad"})


if __name__ == "__main__":
    unittest.main()
