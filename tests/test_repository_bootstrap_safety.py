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


def repository(path: Path, remote: Path) -> GitRepository:
    return GitRepository(
        path=path,
        remote_url=str(remote),
        branch="main",
        token=None,
        user_name="SyncApp Test",
        user_email="syncapp-test@example.invalid",
    )


class RepositoryBootstrapSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_symlinked_repository_root_is_refused_without_touching_target(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        managed = self.root / "managed"
        managed.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(GitError, "not a real directory"):
            repository(managed, self.remote).ensure()

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
        self.assertFalse((outside / ".git").exists())

    def test_nonempty_unmanaged_directory_is_preserved_and_refused(self) -> None:
        managed = self.root / "managed"
        managed.mkdir()
        sentinel = managed / "unknown-state.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")

        with self.assertRaisesRegex(GitError, "contains unmanaged state"):
            repository(managed, self.remote).ensure()

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
        self.assertFalse((managed / ".git").exists())

    def test_symlinked_git_metadata_is_refused_without_following_it(self) -> None:
        managed = self.root / "managed"
        managed.mkdir()
        outside = self.root / "outside-git"
        outside.mkdir()
        sentinel = outside / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        (managed / ".git").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(GitError, "metadata is not a real directory"):
            repository(managed, self.remote).ensure()

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")

    def test_empty_directory_bootstraps_without_clone_cleanup(self) -> None:
        seed = self.root / "seed"
        seed.mkdir()
        git(seed, "init", "-b", "main")
        git(seed, "config", "user.name", "SyncApp Test")
        git(seed, "config", "user.email", "syncapp-test@example.invalid")
        (seed / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
        git(seed, "add", "configuration.yaml")
        git(seed, "commit", "-m", "initial")
        expected_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=seed,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        git(seed, "remote", "add", "origin", str(self.remote))
        git(seed, "push", "origin", "main")

        managed = self.root / "managed"
        managed.mkdir()
        managed_repository = repository(managed, self.remote)
        managed_repository.ensure()

        self.assertEqual(managed_repository.relationship(), "equal")
        self.assertEqual(managed_repository.head(), expected_commit)
        self.assertEqual(managed_repository.remote_head(), expected_commit)
        self.assertTrue((managed / ".git").is_dir())
        self.assertFalse((managed / "configuration.yaml").exists())
        entries = managed_repository.index_tree_entries()
        self.assertEqual([entry.path for entry in entries], ["configuration.yaml"])
        self.assertEqual(
            managed_repository.read_blob(entries[0].object_id),
            b"homeassistant:\n",
        )


if __name__ == "__main__":
    unittest.main()
