from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from syncapp.supervisor import SupervisorClient, SupervisorError


class FakeBinaryResponse:
    def __init__(self, payload: bytes):
        self.stream = BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class SupervisorBackupDownloadTests(unittest.TestCase):
    def test_download_streams_to_new_file_and_fsyncs(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        payload = b"tar-bytes" * 1024
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(payload),
            ), mock.patch("syncapp.supervisor.os.fsync") as fsync:
                size = client.download_backup(
                    "safe_slug",
                    destination,
                    max_bytes=len(payload) + 1,
                )
            self.assertEqual(size, len(payload))
            self.assertEqual(destination.read_bytes(), payload)
            fsync.assert_called_once()

    def test_download_refuses_existing_destination_before_network_request(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            destination.write_bytes(b"preserve")
            with mock.patch("syncapp.supervisor.urlopen") as urlopen:
                with self.assertRaisesRegex(SupervisorError, "refusing to overwrite"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            urlopen.assert_not_called()
            self.assertEqual(destination.read_bytes(), b"preserve")

    def test_download_limit_failure_removes_partial_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        payload = b"x" * 4096
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(payload),
            ):
                with self.assertRaisesRegex(SupervisorError, "exceeded.*byte limit"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertFalse(destination.exists())

    def test_empty_download_fails_and_removes_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(b""),
            ):
                with self.assertRaisesRegex(SupervisorError, "returned no bytes"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertFalse(destination.exists())

    def test_invalid_slug_is_rejected_before_destination_creation(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with self.assertRaisesRegex(SupervisorError, "invalid backup slug"):
                client.download_backup("../escape", destination, max_bytes=1024)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
