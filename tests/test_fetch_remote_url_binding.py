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


def configure_identity(cwd: Path) -> None:
    git(cwd, "config", "user.name", "SyncApp Test")
    git(cwd, "config", "user.email", "syncapp-test@example.invalid")


class FetchRemoteUrlBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "expected.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare")

        seed = self.root / "seed"
        seed.mkdir()
        git(seed, "init", "-b", "main")
        configure_identity(seed)
        (seed / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        git(seed, "add", "configuration.yaml")
        git(seed, "commit", "-m", "initial")
        git(seed, "remote", "add", "origin", str(self.remote))
        git(seed, "push", "-u", "origin", "main")

        self.work = self.root / "work"
        self.repository = GitRepository(
            path=self.work,
            remote_url=str(self.remote),
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )
        self.repository.ensure()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _other_clone(self) -> Path:
        other = self.root / "other"
        git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        configure_identity(other)
        return other

    def test_origin_retarget_after_provenance_check_cannot_redirect_fetch(self) -> None:
        other = self._other_clone()
        (other / "scripts.yaml").write_text("{}\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "expected remote advance")
        git(other, "push", "origin", "main")
        expected = git(other, "rev-parse", "HEAD")

        attacker = self.root / "attacker.git"
        attacker.mkdir()
        git(attacker, "init", "--bare")

        original_assert = self.repository._assert_remote_provenance

        def assert_then_retarget() -> None:
            original_assert()
            git(self.work, "remote", "set-url", "origin", str(attacker))

        with patch.object(
            self.repository,
            "_assert_remote_provenance",
            side_effect=assert_then_retarget,
        ):
            self.repository.fetch()

        self.assertEqual(self.repository.remote_head(), expected)
        self.assertEqual(
            git(self.remote, "rev-parse", "refs/heads/main"),
            expected,
        )
        attacker_ref = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"],
            cwd=attacker,
            check=False,
        )
        self.assertNotEqual(attacker_ref.returncode, 0)

    def test_deleted_remote_branch_removes_only_managed_tracking_ref(self) -> None:
        git(self.remote, "update-ref", "-d", "refs/heads/main")

        self.repository.fetch()

        self.assertIsNone(self.repository.remote_head())
        self.assertEqual(self.repository.relationship(), "local_only")

    def test_remote_move_after_fetch_is_rejected(self) -> None:
        other = self._other_clone()
        (other / "scripts.yaml").write_text("one: true\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "first remote advance")
        first = git(other, "rev-parse", "HEAD")
        git(other, "push", "origin", "main")

        (other / "scripts.yaml").write_text("two: true\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "second remote advance")
        second = git(other, "rev-parse", "HEAD")
        git(other, "push", "origin", "main")
        git(self.remote, "update-ref", "refs/heads/main", first)

        original_run = self.repository._run
        moved = False

        def run_with_remote_move(*args: str, **kwargs: object):
            nonlocal moved
            result = original_run(*args, **kwargs)
            if args and args[0] == "fetch" and not moved:
                moved = True
                git(self.remote, "update-ref", "refs/heads/main", second)
            return result

        with patch.object(self.repository, "_run", side_effect=run_with_remote_move):
            with self.assertRaisesRegex(GitError, "remote moved during fetch"):
                self.repository.fetch()

        self.assertEqual(self.repository.remote_head(), first)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/main"), second)


if __name__ == "__main__":
    unittest.main()
