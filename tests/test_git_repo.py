from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitError, GitRepository


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def configure_identity(cwd: Path) -> None:
    git(cwd, "config", "user.name", "SyncApp Test")
    git(cwd, "config", "user.email", "syncapp-test@example.invalid")


class GitRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
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

    def _other_remote(self) -> Path:
        other_remote = self.root / "other-remote.git"
        other_remote.mkdir()
        git(other_remote, "init", "--bare")
        return other_remote

    def test_equal_after_clone(self) -> None:
        self.assertEqual(self.repository.relationship(), "equal")

    def test_existing_clone_refuses_implicit_retarget(self) -> None:
        other_remote = self._other_remote()
        original_origin = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.work,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

        retargeted = GitRepository(
            path=self.work,
            remote_url=str(other_remote),
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

        with self.assertRaisesRegex(GitError, "refusing implicit retargeting"):
            retargeted.ensure()

        current_origin = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.work,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(current_origin, original_origin)
        self.assertEqual(self.repository.relationship(), "equal")

    def test_existing_clone_without_origin_fails_closed(self) -> None:
        git(self.work, "remote", "remove", "origin")

        with self.assertRaisesRegex(GitError, "no readable origin fetch URL"):
            self.repository.ensure()

    def test_existing_clone_refuses_unapproved_push_url(self) -> None:
        other_remote = self._other_remote()
        git(self.work, "remote", "set-url", "--push", "origin", str(other_remote))

        with self.assertRaisesRegex(GitError, "push URL differs"):
            self.repository.ensure()

        push_url = subprocess.run(
            ["git", "remote", "get-url", "--push", "origin"],
            cwd=self.work,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(push_url, str(other_remote))

    def test_push_rechecks_remote_provenance_after_startup(self) -> None:
        other_remote = self._other_remote()
        git(self.work, "remote", "set-url", "--push", "origin", str(other_remote))
        (self.work / "automations.yaml").write_text("[]\n", encoding="utf-8")
        self.repository.add_all()
        self.repository.commit("local")

        with self.assertRaisesRegex(GitError, "unapproved Git target"):
            self.repository.push()

        self.assertEqual(self.repository.relationship(), "local_ahead")

    def test_fetch_rechecks_remote_provenance_after_startup(self) -> None:
        other_remote = self._other_remote()
        git(self.work, "remote", "set-url", "origin", str(other_remote))

        with self.assertRaisesRegex(GitError, "refusing implicit retargeting"):
            self.repository.fetch()

    def test_existing_clone_refuses_multiple_fetch_urls(self) -> None:
        other_remote = self._other_remote()
        git(self.work, "remote", "set-url", "--add", "origin", str(other_remote))

        with self.assertRaisesRegex(GitError, "refusing implicit retargeting"):
            self.repository.ensure()

    def test_existing_clone_refuses_implicit_branch_retarget(self) -> None:
        retargeted = GitRepository(
            path=self.work,
            remote_url=str(self.remote),
            branch="different-branch",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

        with self.assertRaisesRegex(GitError, "refusing implicit branch retargeting"):
            retargeted.ensure()

        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.work,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(current_branch, "main")
        self.assertEqual(self.repository.relationship(), "equal")

    def test_local_ahead(self) -> None:
        (self.work / "automations.yaml").write_text("[]\n", encoding="utf-8")
        self.repository.add_all()
        self.repository.commit("local")
        self.assertEqual(self.repository.relationship(), "local_ahead")

    def test_remote_ahead(self) -> None:
        other = self._other_clone()
        (other / "scripts.yaml").write_text("{}\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "remote")
        git(other, "push", "origin", "main")

        self.repository.fetch()
        self.assertEqual(self.repository.relationship(), "remote_ahead")

    def test_diverged(self) -> None:
        (self.work / "automations.yaml").write_text("[]\n", encoding="utf-8")
        self.repository.add_all()
        self.repository.commit("local")

        other = self._other_clone()
        (other / "scripts.yaml").write_text("{}\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "remote")
        git(other, "push", "origin", "main")

        self.repository.fetch()
        self.assertEqual(self.repository.relationship(), "diverged")

    def test_empty_remote(self) -> None:
        empty = self.root / "empty.git"
        empty.mkdir()
        git(empty, "init", "--bare")
        empty_work = self.root / "empty-work"
        repository = GitRepository(
            path=empty_work,
            remote_url=str(empty),
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )
        repository.ensure()
        self.assertEqual(repository.relationship(), "empty")


if __name__ == "__main__":
    unittest.main()
