from pathlib import Path
import tempfile
import unittest
from unittest import mock

from syncapp.git_repo import GitTreeEntry
import syncapp.staging as staging_module
from syncapp.staging import StagingValidationError, stage_remote_configuration


class SingleBlobRepository:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def remote_head(self) -> str:
        return "f" * 40

    def remote_tree_entries(self) -> list[GitTreeEntry]:
        return [GitTreeEntry("100644", "blob", "blob-config", "configuration.yaml")]

    def blob_size(self, object_id: str) -> int:
        if object_id != "blob-config":
            raise AssertionError("unexpected object id")
        return len(self.content)

    def read_blob(self, object_id: str) -> bytes:
        if object_id != "blob-config":
            raise AssertionError("unexpected object id")
        return self.content


class StagingGitBlobBindingTests(unittest.TestCase):
    def test_same_size_substitution_during_materialization_cannot_become_validated_candidate(self) -> None:
        original = b"homeassistant:\n  name: OriginalA\n"
        tampered = b"homeassistant:\n  name: TamperedA\n"
        self.assertEqual(len(original), len(tampered))
        repository = SingleBlobRepository(original)
        original_validate = staging_module.validate_configuration_directory

        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary) / "staging"
            staging.mkdir()
            marker = staging / "known-good.txt"
            marker.write_text("preserve", encoding="utf-8")

            def substitute_before_validation(root: Path):
                (root / "configuration.yaml").write_bytes(tampered)
                return original_validate(root)

            with mock.patch.object(
                staging_module,
                "validate_configuration_directory",
                side_effect=substitute_before_validation,
            ):
                with self.assertRaisesRegex(
                    StagingValidationError,
                    "materialized staging bytes do not match the fetched Git blobs",
                ):
                    stage_remote_configuration(repository, staging)  # type: ignore[arg-type]

            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
            self.assertFalse(staging.with_name("staging.new").exists())


if __name__ == "__main__":
    unittest.main()
