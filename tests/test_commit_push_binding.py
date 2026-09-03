from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.config import Settings
from syncapp.engine import SyncEngine
from syncapp.git_repo import GitRepository


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
    def __init__(self) -> None:
        self.checks = 0

    def check_core_configuration(self) -> dict:
        self.checks += 1
        return {}


class CommitPushBindingTests(unittest.TestCase):
    def test_commit_tree_substitution_after_final_index_check_is_not_pushed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            remote.mkdir()
            git(remote, "init", "--bare")
            live = root / "live"
            live.mkdir()
            live_file = live / "configuration.yaml"
            live_file.write_text("homeassistant:\n  name: Validated\n", encoding="utf-8")
            repository_dir = root / "repository"
            settings = Settings(
                repository_url=str(remote),
                branch="main",
                github_token=None,
                poll_interval_seconds=60,
                dry_run=False,
                remote_apply_enabled=False,
                verify_timeout_seconds=30,
                git_user_name="SyncApp Test",
                git_user_email="syncapp-test@example.invalid",
                source_dir=live,
                repository_dir=repository_dir,
                staging_dir=root / "staging",
                transaction_dir=root / "transaction",
                manifest_path=root / "managed.json",
            )
            engine = SyncEngine(settings)
            supervisor = FakeSupervisor()
            original_commit = GitRepository.commit

            def substituted_commit(repository: GitRepository, message: str) -> str:
                (repository.path / "configuration.yaml").write_text(
                    "homeassistant:\n  name: SubstitutedAtCommit\n",
                    encoding="utf-8",
                )
                repository.add_all()
                return original_commit(repository, message)

            with patch("syncapp.engine.SupervisorClient", return_value=supervisor), patch.object(
                GitRepository,
                "commit",
                new=substituted_commit,
            ):
                engine.run_once()

            self.assertEqual(supervisor.checks, 1)
            self.assertIsNotNone(engine.repository.head())
            self.assertIsNone(engine.repository.remote_head())
            self.assertEqual(engine.repository.relationship(), "local_only")
            self.assertEqual(
                live_file.read_text(encoding="utf-8"),
                "homeassistant:\n  name: Validated\n",
            )

            retry_supervisor = FakeSupervisor()
            with patch("syncapp.engine.SupervisorClient", return_value=retry_supervisor):
                engine.run_once()

            self.assertEqual(retry_supervisor.checks, 0)
            self.assertIsNone(engine.repository.remote_head())
            self.assertEqual(engine.repository.relationship(), "local_only")


if __name__ == "__main__":
    unittest.main()
