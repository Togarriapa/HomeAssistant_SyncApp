from io import BytesIO
import json
from pathlib import Path
import tarfile
import unittest

from canary import run_canary


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_backup_archive(
    name: str,
    *,
    slug: str = "backup-slug",
    homeassistant_version: str = "2026.9.0",
) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        _add_bytes(inner, "./homeassistant.json", b'{"version":"2026.9.0"}\n')
        _add_bytes(inner, "./data/configuration.yaml", b"homeassistant:\n")

    metadata = json.dumps(
        {
            "slug": slug,
            "name": name,
            "type": "partial",
            "homeassistant": {
                "version": homeassistant_version,
                "exclude_database": True,
            },
        }
    ).encode("utf-8")
    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        _add_bytes(outer, "./backup.json", metadata)
        _add_bytes(outer, "./homeassistant.tar.gz", inner_buffer.getvalue())
    return outer_buffer.getvalue()


class ArchiveCanaryClient:
    def __init__(self, archive: bytes | None = None):
        self.calls: list[str] = []
        self.backup_name: str | None = None
        self.archive_override = archive
        self.download_limit: int | None = None
        self.inventory_size: object = 1.5
        self.detail_size: object = "1.5"

    def core_info(self) -> dict:
        self.calls.append("core-info")
        return {"version": "2026.9.0"}

    def supervisor_info(self) -> dict:
        self.calls.append("supervisor-info")
        return {"version": "2026.09.0"}

    def host_info(self) -> dict:
        self.calls.append("host-info")
        return {"operating_system": "Home Assistant OS 17.0"}

    def core_api_health(self) -> dict:
        self.calls.append("health")
        return {"message": "API running."}

    def check_core_configuration(self) -> dict:
        self.calls.append("check")
        return {}

    def create_homeassistant_backup(self, name: str) -> str:
        self.calls.append("backup")
        self.backup_name = name
        return "backup-slug"

    def list_backups(self) -> list[dict]:
        self.calls.append("backup-inventory")
        return [
            {
                "slug": "backup-slug",
                "name": self.backup_name,
                "type": "partial",
                "size": self.inventory_size,
                "content": {"homeassistant": True},
            }
        ]

    def backup_info(self, slug: str) -> dict:
        self.calls.append("backup-info")
        return {
            "slug": slug,
            "name": self.backup_name,
            "type": "partial",
            "size": self.detail_size,
            "homeassistant": "2026.9.0",
            "homeassistant_exclude_database": True,
        }

    def download_backup(self, slug: str, destination: Path, *, max_bytes: int) -> int:
        self.calls.append("backup-download")
        self.download_limit = max_bytes
        if self.backup_name is None:
            raise AssertionError("backup name must exist before archive download")
        archive = self.archive_override or make_backup_archive(self.backup_name)
        if len(archive) > max_bytes:
            raise RuntimeError("fake archive exceeds limit")
        destination.write_bytes(archive)
        return len(archive)

    def restart_core(self) -> None:
        self.calls.append("restart")

    def wait_for_core_api(self, timeout_seconds: int) -> dict:
        self.calls.append(f"wait:{timeout_seconds}")
        return {"message": "API running."}


class CanaryBackupArchiveTests(unittest.TestCase):
    def test_archive_probe_requires_fresh_backup(self):
        client = ArchiveCanaryClient()
        with self.assertRaisesRegex(RuntimeError, "without a fresh canary backup"):
            run_canary(client, backup_archive_probe=True)  # type: ignore[arg-type]
        self.assertEqual(client.calls, [])

    def test_archive_is_downloaded_identity_bound_and_verified_before_restart(self):
        client = ArchiveCanaryClient()
        result = run_canary(  # type: ignore[arg-type]
            client,
            create_backup=True,
            backup_archive_probe=True,
            backup_archive_max_bytes=16 * 1024 * 1024,
            restart=True,
            timeout_seconds=90,
        )
        self.assertLess(client.calls.index("backup-info"), client.calls.index("backup-download"))
        self.assertLess(client.calls.index("backup-download"), client.calls.index("restart"))
        self.assertEqual(client.download_limit, 16 * 1024 * 1024)
        backup = result["backup"]  # type: ignore[assignment]
        self.assertTrue(backup["backup_size_verified"])  # type: ignore[index]
        self.assertEqual(backup["backup_size_mb"], "1.5")  # type: ignore[index]
        archive = result["backup_archive"]  # type: ignore[assignment]
        self.assertTrue(archive["download_verified"])  # type: ignore[index]
        self.assertTrue(archive["outer_tar_readable"])  # type: ignore[index]
        self.assertTrue(archive["backup_identity_verified"])  # type: ignore[index]
        self.assertTrue(archive["homeassistant_archive_readable"])  # type: ignore[index]
        self.assertTrue(archive["homeassistant_metadata_present"])  # type: ignore[index]
        self.assertTrue(archive["homeassistant_version_matches_api"])  # type: ignore[index]
        self.assertEqual(archive["homeassistant_data_files"], 1)  # type: ignore[index]
        self.assertTrue(archive["temporary_download_removed"])  # type: ignore[index]

    def test_zero_size_metadata_blocks_download_and_restart(self):
        client = ArchiveCanaryClient()
        client.inventory_size = 0
        with self.assertRaisesRegex(RuntimeError, "non-zero size"):
            run_canary(  # type: ignore[arg-type]
                client,
                create_backup=True,
                backup_archive_probe=True,
                restart=True,
            )
        self.assertNotIn("backup-info", client.calls)
        self.assertNotIn("backup-download", client.calls)
        self.assertNotIn("restart", client.calls)

    def test_mismatched_downloaded_archive_identity_blocks_restart(self):
        archive = make_backup_archive("different backup name")
        client = ArchiveCanaryClient(archive=archive)
        with self.assertRaisesRegex(RuntimeError, "name does not match"):
            run_canary(  # type: ignore[arg-type]
                client,
                create_backup=True,
                backup_archive_probe=True,
                restart=True,
            )
        self.assertIn("backup-download", client.calls)
        self.assertNotIn("restart", client.calls)

    def test_corrupt_download_blocks_restart(self):
        client = ArchiveCanaryClient(archive=b"not a tar archive")
        with self.assertRaisesRegex(RuntimeError, "downloaded backup archive canary failed"):
            run_canary(  # type: ignore[arg-type]
                client,
                create_backup=True,
                backup_archive_probe=True,
                restart=True,
            )
        self.assertIn("backup-download", client.calls)
        self.assertNotIn("restart", client.calls)


if __name__ == "__main__":
    unittest.main()
