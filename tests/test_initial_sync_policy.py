from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from syncapp.config import Settings
from syncapp.engine import SyncEngine


class InitialSyncPolicyTests(unittest.TestCase):
    def test_populated_remote_is_blocked_before_local_mirroring_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = Settings(
                repository_url="https://github.com/example/config.git",
                branch="main",
                github_token=None,
                poll_interval_seconds=60,
                dry_run=True,
                remote_apply_enabled=False,
                verify_timeout_seconds=120,
                git_user_name="SyncApp",
                git_user_email="syncapp@example.invalid",
                source_dir=root / "homeassistant",
                repository_dir=root / "repository",
                staging_dir=root / "staging",
                transaction_dir=root / "transaction",
                manifest_path=root / "managed_paths.json",
            )
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
            settings = Settings(
                repository_url="https://github.com/example/config.git",
                branch="main",
                github_token=None,
                poll_interval_seconds=60,
                dry_run=True,
                remote_apply_enabled=False,
                verify_timeout_seconds=120,
                git_user_name="SyncApp",
                git_user_email="syncapp@example.invalid",
                initial_local_publish_enabled=True,
                source_dir=root / "homeassistant",
                repository_dir=root / "repository",
                staging_dir=root / "staging",
                transaction_dir=root / "transaction",
                manifest_path=root / "managed_paths.json",
            )
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


if __name__ == "__main__":
    unittest.main()
