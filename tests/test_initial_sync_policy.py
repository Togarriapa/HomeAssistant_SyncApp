from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from syncapp.config import Settings
from syncapp.engine import SyncEngine
from syncapp.staging import StagingResult


class InitialSyncPolicyTests(unittest.TestCase):
    def _settings(self, root: Path, **overrides: object) -> Settings:
        values = {
            "repository_url": "https://github.com/example/config.git",
            "branch": "main",
            "github_token": None,
            "poll_interval_seconds": 60,
            "dry_run": True,
            "remote_apply_enabled": False,
            "verify_timeout_seconds": 120,
            "git_user_name": "SyncApp",
            "git_user_email": "syncapp@example.invalid",
            "source_dir": root / "homeassistant",
            "repository_dir": root / "repository",
            "staging_dir": root / "staging",
            "transaction_dir": root / "transaction",
            "manifest_path": root / "managed_paths.json",
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    def test_populated_remote_is_blocked_before_local_mirroring_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            engine = SyncEngine(settings)
            repository = MagicMock()
            repository.relationship.return_value = "equal"
            repository.remote_head.return_value = "a" * 40
            engine.repository = repository

            with (
                patch("syncapp.engine.recover_interrupted_apply", return_value=False),
                patch("syncapp.engine.mirror_local_configuration") as mirror,
            ):
                engine.run_once()

            repository.ensure.assert_called_once_with()
            repository.fetch.assert_called_once_with()
            mirror.assert_not_called()

    def test_non_equal_populated_initial_state_stays_blocked_even_with_local_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root, initial_local_publish_enabled=True)
            engine = SyncEngine(settings)
            repository = MagicMock()
            repository.relationship.return_value = "remote_ahead"
            repository.remote_head.return_value = "b" * 40
            engine.repository = repository

            with (
                patch("syncapp.engine.recover_interrupted_apply", return_value=False),
                patch("syncapp.engine.stage_remote_configuration") as stage,
                patch("syncapp.engine.mirror_local_configuration") as mirror,
            ):
                engine.run_once()

            stage.assert_not_called()
            mirror.assert_not_called()

    def test_remote_bootstrap_stages_but_does_not_apply_while_global_apply_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root, initial_remote_apply_enabled=True)
            engine = SyncEngine(settings)
            repository = MagicMock()
            repository.relationship.return_value = "equal"
            repository.remote_head.return_value = "c" * 40
            engine.repository = repository
            staged = StagingResult(commit="c" * 40, file_count=2, total_bytes=100)

            with (
                patch("syncapp.engine.recover_interrupted_apply", return_value=False),
                patch("syncapp.engine.stage_remote_configuration", return_value=staged) as stage,
                patch("syncapp.engine.apply_staged_initial_remote") as apply,
                patch("syncapp.engine.mirror_local_configuration") as mirror,
            ):
                engine.run_once()

            stage.assert_called_once_with(repository, settings.staging_dir)
            apply.assert_not_called()
            mirror.assert_not_called()

    def test_remote_bootstrap_uses_dedicated_transaction_when_all_opt_ins_are_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(
                root,
                github_token="token",
                dry_run=False,
                remote_apply_enabled=True,
                initial_remote_apply_enabled=True,
            )
            engine = SyncEngine(settings)
            repository = MagicMock()
            repository.relationship.return_value = "equal"
            repository.remote_head.return_value = "d" * 40
            engine.repository = repository
            staged = StagingResult(commit="d" * 40, file_count=2, total_bytes=100)

            with (
                patch("syncapp.engine.recover_interrupted_apply", return_value=False),
                patch("syncapp.engine.stage_remote_configuration", return_value=staged),
                patch("syncapp.engine.apply_staged_initial_remote", return_value=("configuration.yaml",)) as apply,
                patch("syncapp.engine.apply_staged_remote") as ordinary_apply,
                patch("syncapp.engine.mirror_local_configuration") as mirror,
            ):
                engine.run_once()

            apply.assert_called_once_with(repository, settings, staged)
            ordinary_apply.assert_not_called()
            mirror.assert_not_called()

    def test_remote_bootstrap_stays_blocked_when_git_relationship_is_not_equal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root, initial_remote_apply_enabled=True)
            engine = SyncEngine(settings)
            repository = MagicMock()
            repository.relationship.return_value = "remote_ahead"
            repository.remote_head.return_value = "e" * 40
            engine.repository = repository

            with (
                patch("syncapp.engine.recover_interrupted_apply", return_value=False),
                patch("syncapp.engine.stage_remote_configuration") as stage,
                patch("syncapp.engine.apply_staged_initial_remote") as apply,
            ):
                engine.run_once()

            stage.assert_not_called()
            apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
