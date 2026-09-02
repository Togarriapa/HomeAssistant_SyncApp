from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from syncapp.backup_archive import (
    BackupArchiveError,
    MAX_HOMEASSISTANT_LOGICAL_BYTES,
    MAX_HOMEASSISTANT_MEMBER_BYTES,
    _bounded_regular_size,
    verify_backup_archive,
)


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_backup_archive(
    *,
    slug: str = "backup-slug",
    backup_name: str = "SyncApp canary test",
    backup_type: str = "partial",
    homeassistant_version: str = "2026.9.0",
    exclude_database: bool = True,
    include_homeassistant: bool = True,
    inner_metadata_name: str = "./homeassistant.json",
    inner_data_name: str = "./data/configuration.yaml",
) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        _add_bytes(inner, inner_metadata_name, b'{"version":"2026.9.0"}\n')
        _add_bytes(inner, inner_data_name, b"homeassistant:\n")
    inner_bytes = inner_buffer.getvalue()

    metadata = json.dumps(
        {
            "slug": slug,
            "name": backup_name,
            "type": backup_type,
            "homeassistant": {
                "version": homeassistant_version,
                "exclude_database": exclude_database,
            },
        }
    ).encode("utf-8")
    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        _add_bytes(outer, "./backup.json", metadata)
        if include_homeassistant:
            _add_bytes(outer, "./homeassistant.tar.gz", inner_bytes)
    return outer_buffer.getvalue()


class BackupArchiveTests(unittest.TestCase):
    def _verify(self, payload: bytes, **expected: str) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "backup.tar"
            archive.write_bytes(payload)
            return verify_backup_archive(archive, **expected)

    def test_valid_supervisor_backup_is_structurally_verified_without_extracting(self):
        evidence = self._verify(
            make_backup_archive(),
            expected_slug="backup-slug",
            expected_name="SyncApp canary test",
            expected_homeassistant_version="2026.9.0",
        )
        self.assertTrue(evidence["outer_tar_readable"])
        self.assertTrue(evidence["backup_metadata_present"])
        self.assertTrue(evidence["backup_identity_verified"])
        self.assertTrue(evidence["partial_backup_verified"])
        self.assertTrue(evidence["homeassistant_database_excluded"])
        self.assertTrue(evidence["homeassistant_archive_present"])
        self.assertTrue(evidence["homeassistant_archive_readable"])
        self.assertTrue(evidence["homeassistant_logical_size_bounded"])
        self.assertGreater(evidence["homeassistant_logical_bytes"], 0)
        self.assertTrue(evidence["homeassistant_metadata_present"])
        self.assertTrue(evidence["homeassistant_version_matches_api"])
        self.assertEqual(evidence["homeassistant_data_files"], 1)

    def test_downloaded_backup_slug_must_match_fresh_backup(self):
        with self.assertRaisesRegex(BackupArchiveError, "slug does not match"):
            self._verify(
                make_backup_archive(slug="different"),
                expected_slug="backup-slug",
                expected_name="SyncApp canary test",
            )

    def test_downloaded_backup_name_must_match_fresh_backup(self):
        with self.assertRaisesRegex(BackupArchiveError, "name does not match"):
            self._verify(
                make_backup_archive(backup_name="different"),
                expected_slug="backup-slug",
                expected_name="SyncApp canary test",
            )

    def test_downloaded_backup_must_be_partial(self):
        with self.assertRaisesRegex(BackupArchiveError, "requested partial backup"):
            self._verify(make_backup_archive(backup_type="full"))

    def test_downloaded_backup_must_confirm_database_exclusion(self):
        with self.assertRaisesRegex(BackupArchiveError, "database exclusion"):
            self._verify(make_backup_archive(exclude_database=False))

    def test_downloaded_homeassistant_version_must_match_api_evidence(self):
        with self.assertRaisesRegex(BackupArchiveError, "version does not match"):
            self._verify(
                make_backup_archive(homeassistant_version="2026.8.0"),
                expected_slug="backup-slug",
                expected_name="SyncApp canary test",
                expected_homeassistant_version="2026.9.0",
            )

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

    def test_empty_normalized_member_path_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "empty normalized member path"):
            self._verify(make_backup_archive(inner_data_name="."))

    def test_missing_homeassistant_metadata_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "exactly one homeassistant.json"):
            self._verify(make_backup_archive(inner_metadata_name="./other.json"))

    def test_missing_homeassistant_data_tree_fails_closed(self):
        with self.assertRaisesRegex(BackupArchiveError, "configuration data files"):
            self._verify(make_backup_archive(inner_data_name="./other/configuration.yaml"))

    def test_single_declared_regular_member_size_is_bounded_before_payload_read(self):
        member = tarfile.TarInfo("data/huge.yaml")
        member.size = MAX_HOMEASSISTANT_MEMBER_BYTES + 1
        with self.assertRaisesRegex(BackupArchiveError, "logical member limit"):
            _bounded_regular_size(0, member)

    def test_cumulative_declared_logical_size_is_bounded(self):
        member = tarfile.TarInfo("data/large.yaml")
        member.size = 2
        with self.assertRaisesRegex(BackupArchiveError, "logical payload limit"):
            _bounded_regular_size(MAX_HOMEASSISTANT_LOGICAL_BYTES - 1, member)

    def test_non_regular_members_do_not_inflate_logical_payload_budget(self):
        member = tarfile.TarInfo("data/")
        member.type = tarfile.DIRTYPE
        member.size = MAX_HOMEASSISTANT_LOGICAL_BYTES + 1
        self.assertEqual(_bounded_regular_size(123, member), 123)


if __name__ == "__main__":
    unittest.main()
