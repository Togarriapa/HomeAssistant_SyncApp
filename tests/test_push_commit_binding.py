from pathlib import Path
import subprocess
import tempfile
import unittest

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


class PushCommitBindingTests(unittest.TestCase):
    def test_push_publishes_expected_commit_even_if_head_advanced(self) -> None:
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
            candidate.write_text("homeassistant:\n  name: Validated\n", encoding="utf-8")
            repository.add_all()
            validated_commit = repository.commit("validated candidate")

            candidate.write_text("homeassistant:\n  name: LaterHead\n", encoding="utf-8")
            repository.add_all()
            later_commit = repository.commit("later local head")
            self.assertNotEqual(validated_commit, later_commit)
            self.assertEqual(repository.head(), later_commit)

            repository.push(validated_commit)

            self.assertEqual(
                git(remote, "rev-parse", "refs/heads/main"),
                validated_commit,
            )
            self.assertEqual(repository.head(), later_commit)


if __name__ == "__main__":
    unittest.main()
