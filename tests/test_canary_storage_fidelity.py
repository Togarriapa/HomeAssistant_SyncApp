from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

from syncapp.canary_storage import CanaryStorageError, run_backup_storage_probe


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, BytesIO(data))


def make_archive(name: str, files: list[tuple[str, bytes]]) -> bytes:
    inner_buffer = BytesIO()
    with tarfile.open(fileobj=inner_buffer, mode="w:gz") as inner:
        add_bytes(inner, "homeassistant.json", b'{"version":"2026.9.0"}\n')
        for relative, data in files:
            add_bytes(inner, f"data/{relative}", data)
    metadata = json.dumps(
        {
            "slug": "backup-slug",
            "name": name,
            "type": "partial",
            "homeassistant": {"version": "2026.9.0", "exclude_database": True},
        }
    ).encode()
    outer_buffer = BytesIO()
    with tarfile.open(fileobj=outer_buffer, mode="w") as outer:
        add_bytes(outer, "backup.json", metadata)
        add_bytes(outer, "homeassistant.tar.gz", inner_buffer.getvalue())
    return outer_buffer.getvalue()


class FidelityClient:
    def __init__(self, live_root: Path, files: list[tuple[str, bytes]], mutate: bool = False):
        self.live_root = live_root
        self.files = files
        self.mutate = mutate
        self.name = ""

    def create_homeassistant_backup(self, name: str) -> str:
        self.name = name
        return "backup-slug"

    def verify_homeassistant_backup(self, slug: str, expected_name: str) -> dict[str, object]:
        return {"homeassistant_version": "2026.9.0", "backup_size_verified": True}

    def download_backup(self, slug: str, destination: Path, *, max_bytes: int) -> int:
        payload = make_archive(self.name, self.files)
        destination.write_bytes(payload)
        if self.mutate:
            (self.live_root / "configuration.yaml").write_text("changed:\n", encoding="utf-8")
        return len(payload)


class StorageFidelityTests(unittest.TestCase):
    def test_real_fidelity_mode_covers_allowed_files_but_not_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            live = root / "live"
            data.mkdir()
            (live / "packages").mkdir(parents=True)
            config = b"homeassistant:\n"
            package = b"sensor:\n"
            (live / "configuration.yaml").write_bytes(config)
            (live / "packages" / "test.yaml").write_bytes(package)
            (live / "secrets.yaml").write_bytes(b"password: private\n")
            client = FidelityClient(
                live,
                [("configuration.yaml", config), ("packages/test.yaml", package)],
            )
            with mock.patch("syncapp.canary_storage._available_bytes", return_value=10_000_000):
                result = run_backup_storage_probe(  # type: ignore[arg-type]
                    client,
                    data_root=data,
                    live_root=live,
                    max_bytes=1_000_000,
                    reserve_bytes=1_000_000,
                )
            archive = result["archive"]  # type: ignore[assignment]
            self.assertEqual(archive["expected_live_files"], 2)  # type: ignore[index]
            self.assertTrue(archive["expected_live_files_byte_verified"])  # type: ignore[index]
            self.assertTrue(archive["live_file_set_stable"])  # type: ignore[index]
            self.assertEqual((live / "secrets.yaml").read_bytes(), b"password: private\n")

    def test_live_drift_during_measurement_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            live = root / "live"
            data.mkdir()
            live.mkdir()
            original = b"homeassistant:\n"
            (live / "configuration.yaml").write_bytes(original)
            client = FidelityClient(live, [("configuration.yaml", original)], mutate=True)
            with mock.patch("syncapp.canary_storage._available_bytes", return_value=10_000_000):
                with self.assertRaisesRegex(CanaryStorageError, "changed during backup fidelity"):
                    run_backup_storage_probe(  # type: ignore[arg-type]
                        client,
                        data_root=data,
                        live_root=live,
                        max_bytes=1_000_000,
                        reserve_bytes=1_000_000,
                    )


if __name__ == "__main__":
    unittest.main()
