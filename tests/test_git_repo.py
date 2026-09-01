from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitRepository


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

    def test_equal_after_clone(self) -> None:
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
