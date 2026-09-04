from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from syncapp.git_repo import GitRepository


def git(cwd: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return process.stdout.strip()


def refs(cwd: Path) -> str:
    return subprocess.run(
        ["git", "show-ref"],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()


def configure_identity(cwd: Path) -> None:
    git(cwd, "config", "user.name", "SyncApp Test")
    git(cwd, "config", "user.email", "syncapp-test@example.invalid")


class GitTransportUrlRewriteTests(unittest.TestCase):
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

        self.attacker = self.root / "attacker.git"
        self.attacker.mkdir()
        git(self.attacker, "init", "--bare")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _inject_fetch_rewrite_after_provenance(self) -> None:
        self.repository._assert_remote_provenance()
        git(
            self.work,
            "config",
            "--add",
            f"url.{self.attacker}.insteadOf",
            str(self.remote),
        )

    def _inject_push_rewrite_after_provenance(self) -> None:
        self.repository._assert_remote_provenance()
        git(
            self.work,
            "config",
            "--add",
            f"url.{self.attacker}.pushInsteadOf",
            str(self.remote),
        )
        git(
            self.work,
            "config",
            "--add",
            f"url.{self.attacker}.insteadOf",
            str(self.remote),
        )

    def test_fetch_transport_ignores_rewrite_inserted_after_provenance_check(self) -> None:
        other = self.root / "other"
        git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        configure_identity(other)
        (other / "scripts.yaml").write_text("{}\n", encoding="utf-8")
        git(other, "add", "scripts.yaml")
        git(other, "commit", "-m", "remote update")
        expected = git(other, "rev-parse", "HEAD")
        git(other, "push", "origin", "main")

        self._inject_fetch_rewrite_after_provenance()
        with mock.patch.object(self.repository, "_assert_remote_provenance", return_value=None):
            self.repository.fetch()

        self.assertEqual(self.repository.remote_head(), expected)
        self.assertEqual(self.repository.relationship(), "remote_ahead")
        self.assertEqual(refs(self.attacker), "")

    def test_push_transport_ignores_rewrite_inserted_after_provenance_check(self) -> None:
        (self.work / "automations.yaml").write_text("[]\n", encoding="utf-8")
        self.repository.add_all()
        expected = self.repository.commit("local update")

        self._inject_push_rewrite_after_provenance()
        with mock.patch.object(self.repository, "_assert_remote_provenance", return_value=None):
            self.repository.push(expected)

        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/main"), expected)
        self.assertEqual(refs(self.attacker), "")
        self.assertEqual(self.repository.relationship(), "equal")


if __name__ == "__main__":
    unittest.main()
