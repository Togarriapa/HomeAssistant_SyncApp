from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.config import Settings
from syncapp.engine import SyncEngine
from syncapp.git_repo import GitError, GitRepository
from syncapp.supervisor import SupervisorError


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


class FakeSupervisor:
    def __init__(self, *, valid: bool = True):
        self.valid = valid
        self.checks = 0

    def check_core_configuration(self) -> dict:
        self.checks += 1
        if not self.valid:
            raise SupervisorError("configuration invalid")
        return {}


class MutatingSupervisor(FakeSupervisor):
    def __init__(self, live_file: Path) -> None:
        super().__init__()
        self.live_file = live_file

    def check_core_configuration(self) -> dict:
        result = super().check_core_configuration()
        self.live_file.write_text(
            "homeassistant:\n  name: ChangedDuringCheck\n",
            encoding="utf-8",
        )
        return result


class IndexMutatingSupervisor(FakeSupervisor):
    def __init__(self, repository_file: Path) -> None:
        super().__init__()
        self.repository_file = repository_file

    def check_core_configuration(self) -> dict:
        result = super().check_core_configuration()
        self.repository_file.write_text(
            "homeassistant:\n  name: IndexInjected\n",
            encoding="utf-8",
        )
        git(self.repository_file.parent, "add", "-A")
        return result


class LocalPrepushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare")
        self.live = self.root / "live"
        self.live.mkdir()
        self.repository_dir = self.root / "repository"
        self.settings = Settings(
            repository_url=str(self.remote),
            branch="main",
            github_token=None,
            poll_interval_seconds=60,
            dry_run=False,
            remote_apply_enabled=False,
            verify_timeout_seconds=30,
            git_user_name="SyncApp Test",
            git_user_email="syncapp-test@example.invalid",
            source_dir=self.live,
            repository_dir=self.repository_dir,
            staging_dir=self.root / "staging",
            transaction_dir=self.root / "transaction",
            manifest_path=self.root / "managed.json",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _engine(self, *, dry_run: bool = False) -> SyncEngine:
        settings = self.settings
        if dry_run:
            settings = Settings(
                repository_url=settings.repository_url,
                branch=settings.branch,
                github_token=settings.github_token,
                poll_interval_seconds=settings.poll_interval_seconds,
                dry_run=True,
                remote_apply_enabled=False,
                verify_timeout_seconds=settings.verify_timeout_seconds,
                git_user_name=settings.git_user_name,
                git_user_email=settings.git_user_email,
                source_dir=settings.source_dir,
                repository_dir=settings.repository_dir,
                staging_dir=settings.staging_dir,
                transaction_dir=settings.transaction_dir,
                manifest_path=settings.manifest_path,
            )
        return SyncEngine(settings)

    def _publish_initial(self, content: str = "homeassistant:\n  name: Initial\n") -> SyncEngine:
        (self.live / "configuration.yaml").write_text(content, encoding="utf-8")
        engine = self._engine()
        supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()
        self.assertEqual(supervisor.checks, 1)
        self.assertEqual(engine.repository.relationship(), "equal")
        return engine

    def test_valid_local_configuration_initializes_empty_remote(self) -> None:
        (self.live / "configuration.yaml").write_text("homeassistant:\n  name: Test\n", encoding="utf-8")
        supervisor = FakeSupervisor()
        engine = self._engine()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 1)
        remote_head = git(self.remote, "rev-parse", "refs/heads/main")
        self.assertTrue(remote_head)
        self.assertEqual(engine.repository.relationship(), "equal")

    def test_first_push_failure_recovers_local_only_after_revalidation(self) -> None:
        live_file = self.live / "configuration.yaml"
        live_file.write_text("homeassistant:\n  name: FirstPublish\n", encoding="utf-8")
        engine = self._engine()
        first_supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=first_supervisor), patch.object(
            GitRepository,
            "push",
            side_effect=GitError("simulated push failure"),
        ):
            with self.assertRaisesRegex(GitError, "simulated push failure"):
                engine.run_once()

        self.assertEqual(first_supervisor.checks, 1)
        self.assertEqual(engine.repository.relationship(), "local_only")
        self.assertIsNone(engine.repository.remote_head())

        retry_supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=retry_supervisor):
            engine.run_once()

        self.assertEqual(retry_supervisor.checks, 1)
        self.assertEqual(engine.repository.relationship(), "equal")
        self.assertEqual(engine.repository.remote_head(), engine.repository.head())
        self.assertTrue(self.settings.manifest_path.exists())

    def test_failed_incremental_push_revalidates_local_ahead_before_retry(self) -> None:
        engine = self._publish_initial()
        old_remote = engine.repository.remote_head()
        (self.live / "configuration.yaml").write_text(
            "homeassistant:\n  name: RetryCandidate\n",
            encoding="utf-8",
        )
        first_supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=first_supervisor), patch.object(
            GitRepository,
            "push",
            side_effect=GitError("simulated push failure"),
        ):
            with self.assertRaisesRegex(GitError, "simulated push failure"):
                engine.run_once()

        self.assertEqual(first_supervisor.checks, 1)
        self.assertEqual(engine.repository.relationship(), "local_ahead")
        self.assertEqual(engine.repository.remote_head(), old_remote)

        retry_supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=retry_supervisor):
            engine.run_once()

        self.assertEqual(retry_supervisor.checks, 1)
        self.assertEqual(engine.repository.relationship(), "equal")
        self.assertNotEqual(engine.repository.remote_head(), old_remote)

    def test_stale_local_ahead_commit_is_not_retried(self) -> None:
        engine = self._publish_initial()
        remote_before = engine.repository.remote_head()
        repository_file = self.repository_dir / "configuration.yaml"
        repository_file.write_text(
            "homeassistant:\n  name: StaleCommit\n",
            encoding="utf-8",
        )
        git(self.repository_dir, "add", "-A")
        git(self.repository_dir, "commit", "-m", "test: stale local commit")
        self.assertEqual(engine.repository.relationship(), "local_ahead")

        supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 0)
        self.assertEqual(engine.repository.remote_head(), remote_before)
        self.assertEqual(engine.repository.relationship(), "local_ahead")

    def test_multiple_unpushed_commits_hide_no_intermediate_secret_history(self) -> None:
        engine = self._publish_initial()
        remote_before = engine.repository.remote_head()
        secret = self.repository_dir / "secrets.yaml"
        secret.write_text("password: must-not-push\n", encoding="utf-8")
        git(self.repository_dir, "add", "-A")
        git(self.repository_dir, "commit", "-m", "test: unsafe intermediate secret")

        secret.unlink()
        final = "homeassistant:\n  name: FinalSafe\n"
        (self.repository_dir / "configuration.yaml").write_text(final, encoding="utf-8")
        (self.live / "configuration.yaml").write_text(final, encoding="utf-8")
        git(self.repository_dir, "add", "-A")
        git(self.repository_dir, "commit", "-m", "test: safe-looking final commit")
        self.assertEqual(engine.repository.unpushed_commit_count(), 2)

        supervisor = FakeSupervisor()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 0)
        self.assertEqual(engine.repository.remote_head(), remote_before)
        self.assertEqual(engine.repository.relationship(), "local_ahead")

    def test_live_change_during_semantic_validation_blocks_commit_and_push(self) -> None:
        live_file = self.live / "configuration.yaml"
        live_file.write_text("homeassistant:\n  name: Original\n", encoding="utf-8")
        supervisor = MutatingSupervisor(live_file)
        engine = self._engine()

        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 1)
        self.assertIsNone(engine.repository.head())
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])
        self.assertEqual(
            live_file.read_text(encoding="utf-8"),
            "homeassistant:\n  name: ChangedDuringCheck\n",
        )

    def test_staged_index_change_during_semantic_validation_blocks_push(self) -> None:
        live_file = self.live / "configuration.yaml"
        live_file.write_text("homeassistant:\n  name: Original\n", encoding="utf-8")
        repository_file = self.repository_dir / "configuration.yaml"
        supervisor = IndexMutatingSupervisor(repository_file)
        engine = self._engine()

        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 1)
        self.assertIsNone(engine.repository.head())
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])
        self.assertEqual(
            live_file.read_text(encoding="utf-8"),
            "homeassistant:\n  name: Original\n",
        )

    def test_invalid_yaml_is_not_committed_or_pushed(self) -> None:
        (self.live / "configuration.yaml").write_text("broken: [\n", encoding="utf-8")
        supervisor = FakeSupervisor()
        engine = self._engine()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 0)
        self.assertIsNone(engine.repository.head())
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])
        self.assertEqual(list(self.repository_dir.glob("*.yaml")), [])

    def test_supervisor_rejection_prevents_push(self) -> None:
        (self.live / "configuration.yaml").write_text("homeassistant:\n  name: Test\n", encoding="utf-8")
        supervisor = FakeSupervisor(valid=False)
        engine = self._engine()
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 1)
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])

    def test_dry_run_validates_but_leaves_isolated_git_clean(self) -> None:
        (self.live / "configuration.yaml").write_text("homeassistant:\n  name: Test\n", encoding="utf-8")
        supervisor = FakeSupervisor()
        engine = self._engine(dry_run=True)
        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 1)
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])
        self.assertEqual(git(self.repository_dir, "status", "--porcelain"), "")

    def test_corrupt_manifest_blocks_local_mirror_commit_and_push(self) -> None:
        (self.live / "configuration.yaml").write_text("homeassistant:\n  name: Test\n", encoding="utf-8")
        self.settings.manifest_path.write_text('["../outside.yaml"]', encoding="utf-8")
        supervisor = FakeSupervisor()
        engine = self._engine()

        with patch("syncapp.engine.SupervisorClient", return_value=supervisor):
            engine.run_once()

        self.assertEqual(supervisor.checks, 0)
        self.assertIsNone(engine.repository.head())
        self.assertIsNone(engine.repository.remote_head())
        self.assertEqual(engine.repository.staged_paths(), [])
        self.assertFalse((self.repository_dir / "configuration.yaml").exists())


if __name__ == "__main__":
    unittest.main()
