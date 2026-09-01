from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.config import Settings
from syncapp.engine import SyncEngine
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
