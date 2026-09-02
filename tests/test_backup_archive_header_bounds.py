from io import BytesIO
import gzip
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from syncapp.backup_archive import (
    BackupArchiveError,
    MAX_HOMEASSISTANT_MEMBER_BYTES,
    MAX_OUTER_MEMBER_BYTES,
    verify_backup_archive,
)


def _declared_member_header(name: str, size: int) -> bytes:
    member = tarfile.TarInfo(name)
    member.size = size
    return member.tobuf(format=tarfile.USTAR_FORMAT)


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    member = tarfile.TarInfo(name)
    member.size = len(data)
    archive.addfile(member, BytesIO(data))


class BackupArchiveHeaderBoundTests(unittest.TestCase):
    def _verify_bytes(self, payload: bytes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backup.tar"
            path.write_bytes(payload)
            verify_backup_archive(path)

    def test_compressed_outer_oversized_header_fails_before_missing_payload(self):
        payload = gzip.compress(
            _declared_member_header("unrelated.bin", MAX_OUTER_MEMBER_BYTES + 1)
        )

        with self.assertRaisesRegex(BackupArchiveError, "logical member limit"):
            self._verify_bytes(payload)

    def test_nested_oversized_header_fails_before_missing_payload(self):
        inner = gzip.compress(
            _declared_member_header(
                "data/impossibly-large.yaml",
                MAX_HOMEASSISTANT_MEMBER_BYTES + 1,
            )
        )
        metadata = json.dumps(
            {
                "slug": "backup-slug",
                "name": "SyncApp canary test",
                "type": "partial",
                "homeassistant": {
                    "version": "2026.9.0",
                    "exclude_database": True,
                },
            }
        ).encode("utf-8")
        outer_buffer = BytesIO()
        with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
            _add_bytes(outer, "backup.json", metadata)
            _add_bytes(outer, "homeassistant.tar.gz", inner)

        with self.assertRaisesRegex(BackupArchiveError, "logical member limit"):
            self._verify_bytes(outer_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
