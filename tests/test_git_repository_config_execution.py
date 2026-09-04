from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitRepository


def git(cwd: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process.stdout.strip()


class GitRepositoryConfigExecutionTests(unittest.TestCase):
    def test_repository_core_fsmonitor_cannot_execute_during_syncapp_git_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = root / "remote.git"
            remote.mkdir()
            git(remote, "init", "--bare")

            work = root / "work"
            repository = GitRepository(
                path=work,
                remote_url=str(remote),
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.ensure()

            marker = root / "fsmonitor-executed"
            helper = root / "malicious-fsmonitor.sh"
            helper.write_text(
                "#!/bin/sh\nprintf executed > \"$1\"\nexit 0\n".replace("$1", str(marker)),
                encoding="utf-8",
            )
            helper.chmod(0o700)
            git(work, "config", "core.fsmonitor", str(helper))

            repository._run("status", "--porcelain")

            self.assertFalse(
                marker.exists(),
                "repository-local core.fsmonitor executed despite command-scope safety override",
            )


if __name__ == "__main__":
    unittest.main()
