from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitError, GitRepository


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


class PushRemoteVerificationTests(unittest.TestCase):
    def test_remote_move_after_push_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            remote.mkdir()
            git(remote, "init", "--bare")

            repository_path = root / "repository"
            repository = GitRepository(
                path=repository_path,
                remote_url=str(remote),
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.ensure()

            candidate = repository_path / "configuration.yaml"
            candidate.write_text("homeassistant:\n  name: Expected\n", encoding="utf-8")
            repository.add_all()
            expected = repository.commit("expected")

            candidate.write_text("homeassistant:\n  name: Concurrent\n", encoding="utf-8")
            repository.add_all()
            concurrent = repository.commit("concurrent")
            git(repository_path, "push", str(remote), f"{concurrent}:refs/heads/concurrent")

            original_run = repository._run

            def run_with_remote_move(*args: str, **kwargs: object):
                result = original_run(*args, **kwargs)
                if args and args[0] == "push" and str(remote) in args:
                    git(remote, "update-ref", "refs/heads/main", concurrent)
                return result

            with patch.object(repository, "_run", side_effect=run_with_remote_move):
                with self.assertRaisesRegex(
                    GitError,
                    "authoritative remote branch does not identify the expected commit",
                ):
                    repository.push(expected)

            self.assertEqual(git(remote, "rev-parse", "refs/heads/main"), concurrent)


if __name__ == "__main__":
    unittest.main()
