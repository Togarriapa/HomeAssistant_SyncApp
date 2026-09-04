from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

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


class PublicationRemoteUrlBindingTests(unittest.TestCase):
    def test_origin_retarget_after_provenance_check_cannot_redirect_push(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected_remote = root / "expected.git"
            attacker_remote = root / "attacker.git"
            expected_remote.mkdir()
            attacker_remote.mkdir()
            git(expected_remote, "init", "--bare")
            git(attacker_remote, "init", "--bare")

            repository_path = root / "repository"
            repository = GitRepository(
                path=repository_path,
                remote_url=str(expected_remote),
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.ensure()

            candidate = repository_path / "configuration.yaml"
            candidate.write_text("homeassistant:\n  name: Expected\n", encoding="utf-8")
            repository.add_all()
            expected_commit = repository.commit("expected")

            original_assert = repository._assert_remote_provenance

            def assert_then_retarget() -> None:
                original_assert()
                git(repository_path, "remote", "set-url", "origin", str(attacker_remote))

            with patch.object(
                repository,
                "_assert_remote_provenance",
                side_effect=assert_then_retarget,
            ):
                repository.push(expected_commit)

            self.assertEqual(
                git(expected_remote, "rev-parse", "refs/heads/main"),
                expected_commit,
            )
            self.assertEqual(repository.remote_head(), expected_commit)
            self.assertEqual(repository.relationship(), "equal")
            attacker_ref = subprocess.run(
                ["git", "rev-parse", "--verify", "refs/heads/main"],
                cwd=attacker_remote,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(attacker_ref.returncode, 0)


if __name__ == "__main__":
    unittest.main()
