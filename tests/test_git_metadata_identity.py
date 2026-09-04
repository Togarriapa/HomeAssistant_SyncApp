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


class GitMetadataIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.managed = self.root / "managed"
        self.managed.mkdir()
        git(self.managed, "init", "-b", "main")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_git_metadata_replacement_between_commands_is_refused(self) -> None:
        managed_repository = repository(self.managed)
        self.assertIsNone(managed_repository.head())

        detached = self.managed / ".git.detached"
        (self.managed / ".git").rename(detached)
        replacement = self.managed / ".git"
        replacement.mkdir()
        sentinel = replacement / "sentinel.txt"
        sentinel.write_text("replacement\n", encoding="utf-8")

        with self.assertRaisesRegex(GitError, "metadata identity changed between Git operations"):
            managed_repository.head()

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "replacement\n")
        self.assertTrue((detached / "HEAD").is_file())

    def test_git_metadata_replacement_during_command_uses_pinned_metadata_and_fails_closed(self) -> None:
        managed_repository = repository(self.managed)
        detached = self.managed / ".git.detached"
        real_run = subprocess.run
        injected = False

        def swapping_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
            nonlocal injected
            if not injected:
                injected = True
                (self.managed / ".git").rename(detached)
                replacement = self.managed / ".git"
                replacement.mkdir()
                (replacement / "sentinel.txt").write_text(
                    "replacement\n", encoding="utf-8"
                )
            return real_run(*args, **kwargs)

        with mock.patch("syncapp.git_repo.subprocess.run", side_effect=swapping_run):
            with self.assertRaisesRegex(GitError, "metadata was replaced during Git operation"):
                managed_repository.head()

        self.assertTrue(injected)
        self.assertEqual(
            (self.managed / ".git" / "sentinel.txt").read_text(encoding="utf-8"),
            "replacement\n",
        )
        self.assertTrue((detached / "HEAD").is_file())


if __name__ == "__main__":
    unittest.main()
