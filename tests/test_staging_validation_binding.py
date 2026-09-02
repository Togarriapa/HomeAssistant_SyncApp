from pathlib import Path
import tempfile
import unittest

from syncapp.git_repo import GitTreeEntry
from syncapp.staging import (
    StagingValidationError,
    assert_staging_integrity,
    stage_remote_configuration,
)


class FakeRepository:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.objects = {
            f"blob-{index}": content for index, content in enumerate(files.values())
        }
        self.paths = dict(zip(files.keys(), self.objects.keys(), strict=True))

    def remote_head(self) -> str:
        return "d" * 40

    def remote_tree_entries(self) -> list[GitTreeEntry]:
        return [
            GitTreeEntry("100644", "blob", object_id, path)
            for path, object_id in self.paths.items()
        ]

    def blob_size(self, object_id: str) -> int:
        return len(self.objects[object_id])

    def read_blob(self, object_id: str) -> bytes:
        return self.objects[object_id]


class StagingValidationBindingTests(unittest.TestCase):
    def test_stage_result_binds_exact_validated_bytes(self) -> None:
        repository = FakeRepository(
            {
                "configuration.yaml": b"homeassistant:\n  name: Canary\n",
                "packages/lights.yaml": b"light:\n  - platform: group\n",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            result = stage_remote_configuration(repository, staging)

            self.assertTrue(result.integrity_bound)
            self.assertEqual(result.file_count, 2)
            self.assertEqual(set(result.file_hashes), {"configuration.yaml", "packages/lights.yaml"})
            assert_staging_integrity(staging, result)

    def test_valid_to_valid_yaml_tamper_is_rejected(self) -> None:
        repository = FakeRepository(
            {"configuration.yaml": b"homeassistant:\n  name: Original\n"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            result = stage_remote_configuration(repository, staging)
            (staging / "configuration.yaml").write_text(
                "homeassistant:\n  name: Tampered\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                StagingValidationError, "path/content hash manifest changed"
            ):
                assert_staging_integrity(staging, result)

    def test_invalid_yaml_tamper_is_revalidated_and_rejected(self) -> None:
        repository = FakeRepository(
            {"configuration.yaml": b"homeassistant:\n  name: Original\n"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            result = stage_remote_configuration(repository, staging)
            (staging / "configuration.yaml").write_text(
                "homeassistant: [\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(StagingValidationError, "invalid YAML"):
                assert_staging_integrity(staging, result)

    def test_empty_validated_tree_rejects_later_added_file(self) -> None:
        repository = FakeRepository({})
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            result = stage_remote_configuration(repository, staging)
            self.assertTrue(result.integrity_bound)
            self.assertEqual(result.file_sha256, ())

            (staging / "configuration.yaml").write_text(
                "homeassistant:\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(StagingValidationError, "file count changed"):
                assert_staging_integrity(staging, result)

    def test_symlink_parent_replacement_changes_bound_file_set(self) -> None:
        repository = FakeRepository(
            {"packages/remote.yaml": b"automation: []\n"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            outside = root / "outside"
            outside.mkdir()
            (outside / "remote.yaml").write_text("automation: []\n", encoding="utf-8")
            result = stage_remote_configuration(repository, staging)

            (staging / "packages" / "remote.yaml").unlink()
            (staging / "packages").rmdir()
            (staging / "packages").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(StagingValidationError, "file count changed"):
                assert_staging_integrity(staging, result)


if __name__ == "__main__":
    unittest.main()
