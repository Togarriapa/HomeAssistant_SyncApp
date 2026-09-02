from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from syncapp.apply import apply_staged_initial_remote
from syncapp.config import Settings
from syncapp.staging import StagingResult
from syncapp.transaction import TransactionError


class InitialRemoteApplyTests(unittest.TestCase):
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

    def test_bootstrap_uses_all_allowed_live_files_as_reversible_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            (settings.source_dir / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            (settings.source_dir / "automations.yaml").write_text("[]\n", encoding="utf-8")
            (settings.source_dir / "secrets.yaml").write_text("password: secret\n", encoding="utf-8")
            storage = settings.source_dir / ".storage"
            storage.mkdir()
            (storage / "core.config").write_text("runtime", encoding="utf-8")

            commit = "a" * 40
            staged = StagingResult(commit=commit, file_count=1, total_bytes=10)
            repository = MagicMock()
            repository.head.return_value = commit

            with patch("syncapp.apply._execute_staged_apply", return_value=("configuration.yaml",)) as execute:
                affected = apply_staged_initial_remote(repository, settings, staged)

            self.assertEqual(affected, ("configuration.yaml",))
            execute.assert_called_once_with(
                repository,
                settings,
                staged,
                {"configuration.yaml", "automations.yaml"},
                verify_noop=True,
            )

    def test_noop_bootstrap_requires_supervisor_semantic_validation_before_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            settings.staging_dir.mkdir(parents=True)
            content = "homeassistant:\n"
            (settings.source_dir / "configuration.yaml").write_text(content, encoding="utf-8")
            (settings.staging_dir / "configuration.yaml").write_text(content, encoding="utf-8")

            commit = "c" * 40
            staged = StagingResult(commit=commit, file_count=1, total_bytes=len(content))
            repository = MagicMock()
            repository.head.return_value = commit
            supervisor = MagicMock()
            supervisor.check_core_configuration.return_value = {}

            with patch("syncapp.apply.SupervisorClient", return_value=supervisor):
                affected = apply_staged_initial_remote(repository, settings, staged)

            self.assertEqual(affected, ())
            supervisor.check_core_configuration.assert_called_once_with()
            repository.fetch.assert_called_once_with()
            repository.adopt_remote.assert_called_once_with(commit)
            self.assertTrue(settings.manifest_path.exists())

    def test_symlink_parent_cannot_hide_matching_bytes_as_noop_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            settings.staging_dir.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (settings.staging_dir / "packages").mkdir()
            content = "same: true\n"
            (outside / "same.yaml").write_text(content, encoding="utf-8")
            (settings.staging_dir / "packages" / "same.yaml").write_text(content, encoding="utf-8")
            (settings.source_dir / "packages").symlink_to(outside, target_is_directory=True)

            commit = "e" * 40
            staged = StagingResult(commit=commit, file_count=1, total_bytes=len(content))
            repository = MagicMock()
            repository.head.return_value = commit

            with patch("syncapp.apply.SupervisorClient") as supervisor_factory:
                with self.assertRaisesRegex(TransactionError, "compare staged candidate.*safely"):
                    apply_staged_initial_remote(repository, settings, staged)

            supervisor_factory.assert_not_called()
            repository.fetch.assert_not_called()
            repository.adopt_remote.assert_not_called()
            self.assertFalse(settings.manifest_path.exists())
            self.assertEqual((outside / "same.yaml").read_text(), content)

    def test_noop_bootstrap_does_not_establish_baseline_when_semantic_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            settings.staging_dir.mkdir(parents=True)
            content = "homeassistant:\n"
            (settings.source_dir / "configuration.yaml").write_text(content, encoding="utf-8")
            (settings.staging_dir / "configuration.yaml").write_text(content, encoding="utf-8")

            commit = "d" * 40
            staged = StagingResult(commit=commit, file_count=1, total_bytes=len(content))
            repository = MagicMock()
            repository.head.return_value = commit
            supervisor = MagicMock()
            supervisor.check_core_configuration.side_effect = RuntimeError("invalid configuration")

            with patch("syncapp.apply.SupervisorClient", return_value=supervisor):
                with self.assertRaisesRegex(TransactionError, "no-op adoption failed safely"):
                    apply_staged_initial_remote(repository, settings, staged)

            repository.adopt_remote.assert_not_called()
            self.assertFalse(settings.manifest_path.exists())

    def test_bootstrap_refuses_when_managed_baseline_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.manifest_path.write_text("[]", encoding="utf-8")
            staged = StagingResult(commit="a" * 40, file_count=1, total_bytes=10)

            with self.assertRaisesRegex(TransactionError, "only valid before"):
                apply_staged_initial_remote(MagicMock(), settings, staged)

    def test_bootstrap_refuses_if_isolated_head_does_not_match_staged_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            staged = StagingResult(commit="a" * 40, file_count=1, total_bytes=10)
            repository = MagicMock()
            repository.head.return_value = "b" * 40

            with self.assertRaisesRegex(TransactionError, "HEAD to equal"):
                apply_staged_initial_remote(repository, settings, staged)


if __name__ == "__main__":
    unittest.main()
