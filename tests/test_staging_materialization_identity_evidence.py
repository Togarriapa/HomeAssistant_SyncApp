from pathlib import Path
import tempfile
import unittest
from unittest import mock

from syncapp.git_repo import GitTreeEntry
from syncapp.staging import StagingValidationError, stage_remote_configuration
from syncapp.staging_fs import StagingFilesystem


class SingleFileRepository:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def remote_head(self) -> str:
        return "2" * 40

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


class StagingMaterializationIdentityEvidenceTests(unittest.TestCase):
    def test_real_directory_root_replacement_is_preserved_not_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            staging = base / "staging"
            staging.mkdir()
            marker = staging / "known-good.txt"
            marker.write_text("keep", encoding="utf-8")
            replacement_marker = b"do-not-delete\n"
            content = b"homeassistant:\n  name: Remote\n"
            repository = SingleFileRepository(content)
            real_write_new = StagingFilesystem.write_new
            swapped = False

            def replace_root_then_write(
                filesystem: StagingFilesystem,
                relative: str,
                data: bytes,
                expected_sha256: str,
            ) -> None:
                nonlocal swapped
                if not swapped:
                    swapped = True
                    opened = base / "staging.new-opened"
                    filesystem.root.rename(opened)
                    filesystem.root.mkdir()
                    (filesystem.root / "replacement-marker").write_bytes(replacement_marker)
                real_write_new(filesystem, relative, data, expected_sha256)

            with mock.patch.object(
                StagingFilesystem, "write_new", new=replace_root_then_write
            ):
                with self.assertRaisesRegex(
                    StagingValidationError,
                    "staging filesystem confinement failed: .*pathname was replaced",
                ):
                    stage_remote_configuration(repository, staging)  # type: ignore[arg-type]

            self.assertTrue(swapped)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual(
                (base / "staging.new" / "replacement-marker").read_bytes(),
                replacement_marker,
            )
            self.assertEqual(
                (base / "staging.new-opened" / "configuration.yaml").read_bytes(),
                content,
            )


if __name__ == "__main__":
    unittest.main()
