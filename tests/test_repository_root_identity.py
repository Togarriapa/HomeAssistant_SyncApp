from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from syncapp.git_repo import GitError, GitRepository


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def repository(path: Path) -> GitRepository:
    return GitRepository(
        path=path,
        remote_url="https://github.com/example/home-assistant-config.git",
        branch="main",
        token=None,
        user_name="SyncApp Test",
        user_email="syncapp-test@example.invalid",
    )


class RepositoryRootIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        git(self.managed, "init", "-b", "main")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_repository_replacement_between_git_operations_is_refused(self) -> None:
        managed_repository = repository(self.managed)
        self.assertIsNone(managed_repository.head())

        detached = self.root / "detached"
        self.managed.rename(detached)
        self.managed.mkdir()
        sentinel = self.managed / "sentinel.txt"
        sentinel.write_text("replacement\n", encoding="utf-8")

        with self.assertRaisesRegex(GitError, "identity changed between Git operations"):
            managed_repository.head()

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "replacement\n")
        self.assertTrue((detached / ".git").is_dir())

    def test_repository_replacement_during_git_operation_uses_pinned_root_and_fails_closed(self) -> None:
        managed_repository = repository(self.managed)
        detached = self.root / "detached"
        real_run = subprocess.run
        injected = False

        def swapping_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
            nonlocal injected
            if not injected:
                injected = True
                self.managed.rename(detached)
                self.managed.mkdir()
                (self.managed / "sentinel.txt").write_text(
                    "replacement\n", encoding="utf-8"
                )
            return real_run(*args, **kwargs)

        with mock.patch("syncapp.git_repo.subprocess.run", side_effect=swapping_run):
            with self.assertRaisesRegex(GitError, "root was replaced during Git operation"):
                managed_repository.head()

        self.assertTrue(injected)
        self.assertEqual(
            (self.managed / "sentinel.txt").read_text(encoding="utf-8"),
            "replacement\n",
        )
        self.assertTrue((detached / ".git").is_dir())

    def test_git_subprocess_is_started_from_inherited_root_descriptor(self) -> None:
        managed_repository = repository(self.managed)
        real_run = subprocess.run
        observed_cwd: object | None = None
        observed_pass_fds: object | None = None

        def inspecting_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
            nonlocal observed_cwd, observed_pass_fds
            observed_cwd = kwargs.get("cwd")
            observed_pass_fds = kwargs.get("pass_fds")
            return real_run(*args, **kwargs)

        with mock.patch("syncapp.git_repo.subprocess.run", side_effect=inspecting_run):
            self.assertIsNone(managed_repository.head())

        self.assertIsInstance(observed_cwd, str)
        self.assertTrue(str(observed_cwd).startswith("/proc/self/fd/"))
        self.assertIsInstance(observed_pass_fds, tuple)
        self.assertEqual(len(observed_pass_fds), 1)


if __name__ == "__main__":
    unittest.main()
