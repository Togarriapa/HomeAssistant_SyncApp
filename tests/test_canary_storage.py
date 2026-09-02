from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

from syncapp.canary_storage import CanaryStorageError, run_backup_storage_probe
from syncapp.supervisor import SupervisorError


def _add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_backup_archive(name: str) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        _add_bytes(inner, "./homeassistant.json", b'{"version":"2026.9.0"}\n')
        _add_bytes(inner, "./data/configuration.yaml", b"homeassistant:\n")

    metadata = json.dumps(
        {
            "slug": "backup-slug",
            "name": name,
            "type": "partial",
            "homeassistant": {
                "version": "2026.9.0",
                "exclude_database": True,
            },
        }
    ).encode("utf-8")
    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        _add_bytes(outer, "./backup.json", metadata)
        _add_bytes(outer, "./homeassistant.tar.gz", inner_buffer.getvalue())
    return outer_buffer.getvalue()


class StorageCanaryClient:
    def __init__(self, *, archive: bytes | None = None):
        self.calls: list[str] = []
        self.backup_name: str | None = None
        self.archive = archive
        self.download_parent: Path | None = None

    def create_homeassistant_backup(self, name: str) -> str:
        self.calls.append("backup")
        self.backup_name = name
        return "backup-slug"

    def verify_homeassistant_backup(self, slug: str, expected_name: str) -> dict[str, object]:
        self.calls.append("verify")
        if slug != "backup-slug" or expected_name != self.backup_name:
            raise AssertionError("storage probe must verify the backup it just created")
        return {
            "slug": slug,
            "name_matches_request": True,
            "inventory_verified": True,
            "detail_verified": True,
            "homeassistant_content_verified": True,
            "homeassistant_database_excluded": True,
            "backup_size_verified": True,
            "backup_size_mb": "1.5",
            "homeassistant_version": "2026.9.0",
        }

    def download_backup(self, slug: str, destination: Path, *, max_bytes: int) -> int:
        self.calls.append("download")
        self.download_parent = destination.parent
        if self.backup_name is None:
            raise AssertionError("backup must be created before download")
        payload = self.archive if self.archive is not None else make_backup_archive(self.backup_name)
        if len(payload) > max_bytes:
            raise SupervisorError("fake backup exceeded limit")
        destination.write_bytes(payload)
        return len(payload)


class CanaryStorageTests(unittest.TestCase):
    def test_success_uses_data_root_records_phase_timings_and_removes_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = StorageCanaryClient()
            clock_values = iter([0.0, 2.0, 2.0, 3.25, 3.25, 7.75, 7.75, 9.0])

            result = run_backup_storage_probe(  # type: ignore[arg-type]
                client,
                data_root=root,
                max_bytes=1024 * 1024,
                reserve_bytes=1024 * 1024,
                clock=lambda: next(clock_values),
            )

            self.assertEqual(client.calls, ["backup", "verify", "download"])
            self.assertIsNotNone(client.download_parent)
            self.assertEqual(client.download_parent.parent, root)  # type: ignore[union-attr]
            self.assertFalse(client.download_parent.exists())  # type: ignore[union-attr]
            self.assertTrue(result["archive"]["download_verified"])  # type: ignore[index]
            self.assertTrue(result["archive"]["temporary_download_removed"])  # type: ignore[index]
            self.assertEqual(
                result["timings_seconds"],
                {
                    "backup_create": 2.0,
                    "backup_metadata_verify": 1.25,
                    "backup_download": 4.5,
                    "archive_verify": 1.25,
                },
            )
            storage = result["storage"]  # type: ignore[assignment]
            self.assertEqual(storage["data_root"], str(root))  # type: ignore[index]
            self.assertEqual(storage["archive_max_bytes"], 1024 * 1024)  # type: ignore[index]
            self.assertEqual(storage["free_reserve_bytes"], 1024 * 1024)  # type: ignore[index]

    def test_initial_free_space_gate_blocks_before_backup_creation(self):
        client = StorageCanaryClient()
        with tempfile.TemporaryDirectory() as temporary, mock.patch(
            "syncapp.canary_storage._available_bytes", return_value=100
        ):
            with self.assertRaisesRegex(CanaryStorageError, "ceiling plus reserve"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=Path(temporary),
                    max_bytes=80,
                    reserve_bytes=30,
                )
        self.assertEqual(client.calls, [])

    def test_free_space_is_rechecked_after_backup_verification_before_download(self):
        client = StorageCanaryClient()
        with tempfile.TemporaryDirectory() as temporary, mock.patch(
            "syncapp.canary_storage._available_bytes", side_effect=[1000, 100]
        ):
            with self.assertRaisesRegex(CanaryStorageError, "no longer has"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=Path(temporary),
                    max_bytes=100,
                    reserve_bytes=100,
                )
        self.assertEqual(client.calls, ["backup", "verify"])

    def test_symlink_data_root_is_rejected(self):
        client = StorageCanaryClient()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            link = root / "data"
            link.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(CanaryStorageError, "must not be a symlink"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=link,
                    max_bytes=1,
                    reserve_bytes=1,
                )
        self.assertEqual(client.calls, [])

    def test_corrupt_archive_fails_and_temporary_directory_is_removed(self):
        client = StorageCanaryClient(archive=b"not a tar")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(CanaryStorageError, "downloaded backup archive canary failed"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=root,
                    max_bytes=1024 * 1024,
                    reserve_bytes=1024 * 1024,
                )
            self.assertEqual(list(root.iterdir()), [])

    def test_download_failure_still_removes_temporary_directory(self):
        client = StorageCanaryClient()

        def fail_download(slug: str, destination: Path, *, max_bytes: int) -> int:
            client.calls.append("download")
            destination.write_bytes(b"partial")
            raise SupervisorError("injected download failure")

        client.download_backup = fail_download  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(CanaryStorageError, "Supervisor backup download failed"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=root,
                    max_bytes=1024 * 1024,
                    reserve_bytes=1024 * 1024,
                )
            self.assertEqual(list(root.iterdir()), [])

    def test_negative_elapsed_time_fails_closed(self):
        client = StorageCanaryClient()
        with tempfile.TemporaryDirectory() as temporary:
            clock_values = iter([5.0, 4.0])
            with self.assertRaisesRegex(CanaryStorageError, "clock moved backwards"):
                run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=Path(temporary),
                    max_bytes=1,
                    reserve_bytes=1,
                    clock=lambda: next(clock_values),
                )
        self.assertEqual(client.calls, ["backup"])


if __name__ == "__main__":
    unittest.main()
