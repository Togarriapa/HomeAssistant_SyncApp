from pathlib import Path
import tempfile
import unittest

from syncapp.drift import detect_live_drift
from syncapp.git_repo import GitTreeEntry


class FakeRepository:
    def __init__(self, baseline: dict[str, bytes]):
        self.baseline = baseline
        self.objects = {f"oid-{index}": value for index, value in enumerate(baseline.values())}
        self.entries = [
            GitTreeEntry("100644", "blob", f"oid-{index}", path)
            for index, path in enumerate(baseline)
        ]

    def head(self) -> str:
        return "head"

    def tree_entries(self, ref: str) -> list[GitTreeEntry]:
        return self.entries

    def read_blob(self, object_id: str) -> bytes:
        return self.objects[object_id]


class DriftTests(unittest.TestCase):
    def test_clean_live_configuration_matches_git_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configuration.yaml").write_bytes(b"homeassistant: {}\n")
            repository = FakeRepository({"configuration.yaml": b"homeassistant: {}\n"})
            self.assertTrue(detect_live_drift(repository, root).clean)  # type: ignore[arg-type]

    def test_modified_file_is_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configuration.yaml").write_bytes(b"changed: true\n")
            repository = FakeRepository({"configuration.yaml": b"homeassistant: {}\n"})
            result = detect_live_drift(repository, root)  # type: ignore[arg-type]
            self.assertEqual(result.changed, ("configuration.yaml",))

    def test_local_only_allowed_file_is_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configuration.yaml").write_bytes(b"homeassistant: {}\n")
            (root / "automations.yaml").write_bytes(b"[]\n")
            repository = FakeRepository({"configuration.yaml": b"homeassistant: {}\n"})
            result = detect_live_drift(repository, root)  # type: ignore[arg-type]
            self.assertEqual(result.changed, ("automations.yaml",))

    def test_blocked_secret_does_not_count_as_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "configuration.yaml").write_bytes(b"homeassistant: {}\n")
            (root / "secrets.yaml").write_bytes(b"password: local-only\n")
            repository = FakeRepository({"configuration.yaml": b"homeassistant: {}\n"})
            self.assertTrue(detect_live_drift(repository, root).clean)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
