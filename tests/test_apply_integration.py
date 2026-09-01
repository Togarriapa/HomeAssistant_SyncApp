from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.apply import apply_staged_remote
from syncapp.config import Settings
from syncapp.git_repo import GitRepository
from syncapp.staging import stage_remote_configuration
from syncapp.transaction import TransactionError


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def configure_identity(cwd: Path) -> None:
    git(cwd, "config", "user.name", "SyncApp Integration Test")
    git(cwd, "config", "user.email", "syncapp-test@example.invalid")


class FakeSupervisor:
    def __init__(self, health_hook=None):
        self.health_hook = health_hook
        self.backups = 0
        self.checks = 0
        self.restarts = 0
        self.health_checks = 0

    def create_homeassistant_backup(self, name: str) -> str:
        self.backups += 1
        return "backup-integration"

    def check_core_configuration(self) -> dict:
        self.checks += 1
        return {}

    def restart_core(self) -> None:
        self.restarts += 1

    def wait_for_core_api(self, timeout_seconds: int, poll_seconds: float = 2.0) -> dict:
        self.health_checks += 1
        if self.health_hook is not None:
            hook, self.health_hook = self.health_hook, None
            hook()
        return {"message": "API running."}


class ApplyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare")

        self.seed = self.root / "seed"
        self.seed.mkdir()
        git(self.seed, "init", "-b", "main")
        configure_identity(self.seed)
        (self.seed / "configuration.yaml").write_text("version: old\n", encoding="utf-8")
        (self.seed / "obsolete.yaml").write_text("remove: true\n", encoding="utf-8")
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-m", "initial")
        git(self.seed, "remote", "add", "origin", str(self.remote))
        git(self.seed, "push", "-u", "origin", "main")

        self.repository_dir = self.root / "repository"
        self.repository = GitRepository(
            path=self.repository_dir,
            remote_url=str(self.remote),
            branch="main",
            token=None,
            user_name="SyncApp Integration Test",
            user_email="syncapp-test@example.invalid",
        )
        self.repository.ensure()

        self.live = self.root / "live"
        self.live.mkdir()
        (self.live / "configuration.yaml").write_text("version: old\n", encoding="utf-8")
        (self.live / "obsolete.yaml").write_text("remove: true\n", encoding="utf-8")

        self.staging = self.root / "staging"
        self.transaction = self.root / "transaction"
        self.manifest = self.root / "managed_paths.json"
        self.settings = Settings(
            repository_url="https://example.invalid/config.git",
            branch="main",
            github_token=None,
            poll_interval_seconds=60,
            dry_run=False,
            remote_apply_enabled=True,
            verify_timeout_seconds=30,
            git_user_name="SyncApp Integration Test",
            git_user_email="syncapp-test@example.invalid",
            source_dir=self.live,
            repository_dir=self.repository_dir,
            staging_dir=self.staging,
            transaction_dir=self.transaction,
            manifest_path=self.manifest,
        )

        self.other = self.root / "other"
        git(self.root, "clone", "--branch", "main", str(self.remote), str(self.other))
        configure_identity(self.other)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _push_remote_candidate(self) -> str:
        (self.other / "configuration.yaml").write_text("version: new\n", encoding="utf-8")
        (self.other / "obsolete.yaml").unlink()
        (self.other / "automations.yaml").write_text("[]\n", encoding="utf-8")
        git(self.other, "add", "-A")
        git(self.other, "commit", "-m", "remote candidate")
        git(self.other, "push", "origin", "main")
        self.repository.fetch()
        remote = self.repository.remote_head()
        assert remote is not None
        return remote

    def test_successful_apply_advances_live_files_and_local_baseline(self) -> None:
        remote = self._push_remote_candidate()
        staged = stage_remote_configuration(self.repository, self.staging)
        self.assertEqual(staged.commit, remote)
        supervisor = FakeSupervisor()

        with patch("syncapp.apply.SupervisorClient", return_value=supervisor):
            affected = apply_staged_remote(self.repository, self.settings, staged)

        self.assertEqual((self.live / "configuration.yaml").read_text(), "version: new\n")
        self.assertEqual((self.live / "automations.yaml").read_text(), "[]\n")
        self.assertFalse((self.live / "obsolete.yaml").exists())
        self.assertEqual(self.repository.head(), remote)
        self.assertEqual(self.repository.relationship(), "equal")
        self.assertFalse(self.transaction.exists())
        self.assertEqual(supervisor.backups, 1)
        self.assertEqual(supervisor.restarts, 1)
        self.assertIn("configuration.yaml", affected)
        self.assertIn("obsolete.yaml", affected)

    def test_remote_move_during_restart_window_rolls_live_files_back(self) -> None:
        candidate = self._push_remote_candidate()
        staged = stage_remote_configuration(self.repository, self.staging)
        self.assertEqual(staged.commit, candidate)

        def move_remote() -> None:
            (self.other / "scripts.yaml").write_text("{}\n", encoding="utf-8")
            git(self.other, "add", "scripts.yaml")
            git(self.other, "commit", "-m", "remote moved")
            git(self.other, "push", "origin", "main")

        supervisor = FakeSupervisor(health_hook=move_remote)
        with patch("syncapp.apply.SupervisorClient", return_value=supervisor):
            with self.assertRaisesRegex(TransactionError, "remote apply failed safely"):
                apply_staged_remote(self.repository, self.settings, staged)

        self.assertEqual((self.live / "configuration.yaml").read_text(), "version: old\n")
        self.assertEqual((self.live / "obsolete.yaml").read_text(), "remove: true\n")
        self.assertFalse((self.live / "automations.yaml").exists())
        self.assertFalse(self.transaction.exists())
        self.assertNotEqual(self.repository.remote_head(), candidate)
        self.assertEqual(supervisor.restarts, 2)
        self.assertEqual(supervisor.health_checks, 2)

    def test_unsynced_live_drift_blocks_apply_before_backup(self) -> None:
        self._push_remote_candidate()
        staged = stage_remote_configuration(self.repository, self.staging)
        (self.live / "configuration.yaml").write_text("locally edited: true\n", encoding="utf-8")
        supervisor = FakeSupervisor()

        with patch("syncapp.apply.SupervisorClient", return_value=supervisor):
            with self.assertRaisesRegex(TransactionError, "refusing remote apply"):
                apply_staged_remote(self.repository, self.settings, staged)

        self.assertEqual((self.live / "configuration.yaml").read_text(), "locally edited: true\n")
        self.assertEqual(supervisor.backups, 0)
        self.assertFalse(self.transaction.exists())


if __name__ == "__main__":
    unittest.main()
