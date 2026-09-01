from pathlib import Path
import tempfile
import unittest

from syncapp.git_repo import GitTreeEntry
from syncapp.staging import StagingValidationError, stage_remote_configuration


class FakeRepository:
    def __init__(self, files: dict[str, bytes], modes: dict[str, str] | None = None) -> None:
        self.files = files
        self.modes = modes or {}
        self.objects = {f"blob-{index}": content for index, content in enumerate(files.values())}
        self.paths = dict(zip(files.keys(), self.objects.keys(), strict=True))

    def remote_head(self) -> str:
        return "remote-commit"

    def remote_tree_entries(self) -> list[GitTreeEntry]:
        return [
            GitTreeEntry(
                self.modes.get(path, "100644"),
                "blob",
                object_id,
                path,
            )
            for path, object_id in self.paths.items()
        ]

    def blob_size(self, object_id: str) -> int:
        return len(self.objects[object_id])

    def read_blob(self, object_id: str) -> bytes:
        return self.objects[object_id]


class StagingTests(unittest.TestCase):
    def test_stages_valid_home_assistant_yaml_with_custom_tags(self) -> None:
        repo = FakeRepository(
            {
                "configuration.yaml": b"homeassistant:\n  name: Test\nfoo: !include foo.yaml\n",
                "foo.yaml": b"bar: baz\n",
            }
        )
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp) / "staging"
            result = stage_remote_configuration(repo, staging)
            self.assertEqual(result.commit, "remote-commit")
            self.assertEqual(result.file_count, 2)
            self.assertTrue((staging / "configuration.yaml").is_file())

    def test_rejects_secret_file(self) -> None:
        repo = FakeRepository({"secrets.yaml": b"password: nope\n"})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(StagingValidationError, "blocked by policy"):
                stage_remote_configuration(repo, Path(temp) / "staging")

    def test_rejects_git_symlink(self) -> None:
        repo = FakeRepository(
            {"configuration.yaml": b"/etc/passwd"},
            modes={"configuration.yaml": "120000"},
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(StagingValidationError, "unsupported Git mode"):
                stage_remote_configuration(repo, Path(temp) / "staging")

    def test_rejects_malformed_yaml_and_keeps_previous_staging(self) -> None:
        repo = FakeRepository({"configuration.yaml": b"homeassistant: [\n"})
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp) / "staging"
            staging.mkdir()
            marker = staging / "known-good.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(StagingValidationError, "invalid YAML"):
                stage_remote_configuration(repo, staging)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse(Path(temp, "staging.new").exists())


if __name__ == "__main__":
    unittest.main()
