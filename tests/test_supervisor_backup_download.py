from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from syncapp.supervisor import SupervisorClient, SupervisorError


class FakeBinaryResponse:
    def __init__(self, payload: bytes, *, content_length: str | None = None):
        self.stream = BytesIO(payload)
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


class SupervisorBackupDownloadTests(unittest.TestCase):
    def test_download_streams_to_new_file_verifies_length_and_fsyncs(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        payload = b"tar-bytes" * 1024
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(
                    payload,
                    content_length=str(len(payload)),
                ),
            ), mock.patch("syncapp.supervisor.os.fsync") as fsync:
                size = client.download_backup(
                    "safe_slug",
                    destination,
                    max_bytes=len(payload) + 1,
                )
            self.assertEqual(size, len(payload))
            self.assertEqual(destination.read_bytes(), payload)
            fsync.assert_called_once()

    def test_download_without_content_length_still_uses_streaming_limit(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        payload = b"tar-bytes"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(payload),
            ):
                size = client.download_backup(
                    "safe_slug",
                    destination,
                    max_bytes=1024,
                )
            self.assertEqual(size, len(payload))
            self.assertEqual(destination.read_bytes(), payload)

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

    def test_declared_oversize_fails_before_body_stream_and_removes_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        response = FakeBinaryResponse(b"would not be consumed", content_length="4096")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch("syncapp.supervisor.urlopen", return_value=response):
                with self.assertRaisesRegex(SupervisorError, "Content-Length exceeds"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertEqual(response.stream.tell(), 0)
            self.assertFalse(destination.exists())

    def test_malformed_content_length_fails_and_removes_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(b"payload", content_length="not-a-number"),
            ):
                with self.assertRaisesRegex(SupervisorError, "invalid Content-Length"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertFalse(destination.exists())

    def test_nonpositive_content_length_fails_and_removes_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(b"payload", content_length="0"),
            ):
                with self.assertRaisesRegex(SupervisorError, "non-positive Content-Length"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertFalse(destination.exists())

    def test_truncated_body_vs_content_length_fails_and_removes_file(self):
        client = SupervisorClient(token="token", base_url="http://supervisor")
        payload = b"short"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "backup.tar"
            with mock.patch(
                "syncapp.supervisor.urlopen",
                return_value=FakeBinaryResponse(payload, content_length="100"),
            ):
                with self.assertRaisesRegex(SupervisorError, "did not match Content-Length"):
                    client.download_backup("safe_slug", destination, max_bytes=1024)
            self.assertFalse(destination.exists())

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
