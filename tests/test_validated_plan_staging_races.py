import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock

from syncapp.apply import apply_staged_initial_remote
from syncapp.config import Settings
from syncapp.git_repo import GitTreeEntry
from syncapp.staging import assert_staging_integrity, stage_remote_configuration
from syncapp.transaction import TransactionError


class SingleBlobRepository:
    def __init__(self, content: bytes, commit: str = "3" * 40) -> None:
        self.content = content
        self.commit = commit

    def remote_head(self) -> str:
        return self.commit

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


class ValidatedPlanStagingRaceTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            repository_url="https://github.com/example/config.git",
            branch="main",
            github_token="token",
            poll_interval_seconds=60,
            dry_run=False,
            remote_apply_enabled=True,
            verify_timeout_seconds=120,
            git_user_name="SyncApp",
            git_user_email="syncapp@example.invalid",
            initial_remote_apply_enabled=True,
            source_dir=root / "homeassistant",
            repository_dir=root / "repository",
            staging_dir=root / "staging",
            transaction_dir=root / "transaction",
            manifest_path=root / "managed_paths.json",
        )

    def _stage(self, settings: Settings, content: bytes):
        return stage_remote_configuration(
            SingleBlobRepository(content), settings.staging_dir  # type: ignore[arg-type]
        )

    def test_disappearing_staged_file_cannot_be_inferred_as_remote_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            desired = b"homeassistant:\n  name: Same\n"
            (settings.source_dir / "configuration.yaml").write_bytes(desired)
            staged = self._stage(settings, desired)
            repository = MagicMock()
            repository.head.return_value = staged.commit
            supervisor = MagicMock()
            supervisor.check_core_configuration.return_value = {}

            def validate_then_remove(staging_root: Path, result) -> None:
                assert_staging_integrity(staging_root, result)
                (staging_root / "configuration.yaml").unlink()

            with mock.patch(
                "syncapp.apply.assert_staging_integrity",
                side_effect=validate_then_remove,
            ), mock.patch("syncapp.apply.SupervisorClient", return_value=supervisor):
                affected = apply_staged_initial_remote(repository, settings, staged)

            self.assertEqual(affected, ())
            self.assertEqual(
                (settings.source_dir / "configuration.yaml").read_bytes(), desired
            )
            repository.fetch.assert_called_once_with()
            repository.adopt_remote.assert_called_once_with(staged.commit)
            self.assertEqual(
                json.loads(settings.manifest_path.read_text(encoding="utf-8")),
                ["configuration.yaml"],
            )
            self.assertFalse(settings.transaction_dir.exists())

    def test_missing_staged_write_source_aborts_before_supervisor_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            old = b"homeassistant:\n  name: Old\n"
            desired = b"homeassistant:\n  name: New\n"
            (settings.source_dir / "configuration.yaml").write_bytes(old)
            staged = self._stage(settings, desired)
            repository = MagicMock()
            repository.head.return_value = staged.commit
            supervisor = MagicMock()

            def validate_then_remove(staging_root: Path, result) -> None:
                assert_staging_integrity(staging_root, result)
                (staging_root / "configuration.yaml").unlink()

            with mock.patch(
                "syncapp.apply.assert_staging_integrity",
                side_effect=validate_then_remove,
            ), mock.patch("syncapp.apply.SupervisorClient", return_value=supervisor):
                with self.assertRaisesRegex(
                    TransactionError, "staged source is not a regular file"
                ):
                    apply_staged_initial_remote(repository, settings, staged)

            supervisor.create_homeassistant_backup.assert_not_called()
            repository.fetch.assert_not_called()
            repository.adopt_remote.assert_not_called()
            self.assertFalse(settings.transaction_dir.exists())
            self.assertEqual(
                (settings.source_dir / "configuration.yaml").read_bytes(), old
            )

    def test_same_length_post_plan_tamper_is_discarded_before_supervisor_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            old = b"homeassistant:\n  name: LiveOldAA\n"
            desired = b"homeassistant:\n  name: RemoteAAAA\n"
            tampered = b"homeassistant:\n  name: TamperAAAA\n"
            self.assertEqual(len(desired), len(tampered))
            (settings.source_dir / "configuration.yaml").write_bytes(old)
            staged = self._stage(settings, desired)
            repository = MagicMock()
            repository.head.return_value = staged.commit
            supervisor = MagicMock()

            def validate_then_tamper(staging_root: Path, result) -> None:
                assert_staging_integrity(staging_root, result)
                (staging_root / "configuration.yaml").write_bytes(tampered)

            with mock.patch(
                "syncapp.apply.assert_staging_integrity",
                side_effect=validate_then_tamper,
            ), mock.patch("syncapp.apply.SupervisorClient", return_value=supervisor):
                with self.assertRaisesRegex(
                    TransactionError,
                    "staged source bytes changed after validated planning",
                ):
                    apply_staged_initial_remote(repository, settings, staged)

            supervisor.create_homeassistant_backup.assert_not_called()
            repository.fetch.assert_not_called()
            repository.adopt_remote.assert_not_called()
            self.assertFalse(settings.transaction_dir.exists())
            self.assertEqual(
                (settings.source_dir / "configuration.yaml").read_bytes(), old
            )


if __name__ == "__main__":
    unittest.main()
