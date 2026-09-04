from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from syncapp.git_repo import GitError, GitRepository


def repository(path: Path) -> GitRepository:
    return GitRepository(
        path=path,
        remote_url="https://github.com/example/home-assistant-config.git",
        branch="main",
        token=None,
        user_name="SyncApp Test",
        user_email="syncapp-test@example.invalid",
    )


class GitMetadataBootstrapConfinementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_bootstrap_init_is_started_with_already_bound_metadata_descriptor(self) -> None:
        managed = self.root / "managed"
        managed_repository = repository(managed)
        real_run = subprocess.run
        observed = False

        def inspecting_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
            nonlocal observed
            command = args[0]
            if isinstance(command, list) and command[:2] == ["git", "init"]:
                observed = True
                env = kwargs.get("env")
                pass_fds = kwargs.get("pass_fds")
                self.assertIsInstance(env, dict)
                self.assertIsInstance(pass_fds, tuple)
                assert isinstance(env, dict)
                assert isinstance(pass_fds, tuple)
                self.assertTrue(str(env["GIT_DIR"]).startswith("/proc/self/fd/"))
                self.assertTrue(str(env["GIT_WORK_TREE"]).startswith("/proc/self/fd/"))
                self.assertEqual(len(pass_fds), 2)
                self.assertTrue((managed / ".git").is_dir())
            return real_run(*args, **kwargs)

        with mock.patch("syncapp.git_repo.subprocess.run", side_effect=inspecting_run):
            managed_repository._initialize_repository()

        self.assertTrue(observed)
        self.assertTrue((managed / ".git" / "HEAD").is_file())

    def test_bootstrap_metadata_replacement_during_init_fails_closed(self) -> None:
        managed = self.root / "managed"
        managed_repository = repository(managed)
        real_run = subprocess.run
        injected = False
        detached = managed / ".git.detached"

        def swapping_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[object]:
            nonlocal injected
            command = args[0]
            if (
                not injected
                and isinstance(command, list)
                and command[:2] == ["git", "init"]
            ):
                injected = True
                (managed / ".git").rename(detached)
                replacement = managed / ".git"
                replacement.mkdir()
                (replacement / "sentinel.txt").write_text(
                    "replacement\n", encoding="utf-8"
                )
            return real_run(*args, **kwargs)

        with mock.patch("syncapp.git_repo.subprocess.run", side_effect=swapping_run):
            with self.assertRaisesRegex(GitError, "metadata was replaced during Git operation"):
                managed_repository._initialize_repository()

        self.assertTrue(injected)
        self.assertEqual(
            (managed / ".git" / "sentinel.txt").read_text(encoding="utf-8"),
            "replacement\n",
        )
        self.assertTrue((detached / "HEAD").is_file())

    def test_bootstrap_refuses_metadata_that_appears_before_binding(self) -> None:
        managed = self.root / "managed"
        managed.mkdir()
        managed_repository = repository(managed)
        real_mkdir = __import__("os").mkdir
        injected = False

        def racing_mkdir(path: object, *args: object, **kwargs: object) -> None:
            nonlocal injected
            if path == ".git" and not injected:
                injected = True
                (managed / ".git").mkdir()
                (managed / ".git" / "sentinel.txt").write_text(
                    "preserve\n", encoding="utf-8"
                )
            real_mkdir(path, *args, **kwargs)

        with mock.patch("syncapp.git_repo.os.mkdir", side_effect=racing_mkdir):
            with self.assertRaisesRegex(GitError, "appeared during bootstrap"):
                managed_repository._create_and_bind_git_metadata()

        self.assertTrue(injected)
        self.assertEqual(
            (managed / ".git" / "sentinel.txt").read_text(encoding="utf-8"),
            "preserve\n",
        )


if __name__ == "__main__":
    unittest.main()
