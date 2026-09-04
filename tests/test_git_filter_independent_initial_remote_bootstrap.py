from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitRepository


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def configure_filter(repository: Path, helper: Path) -> None:
    (repository / ".git" / "info" / "attributes").write_text(
        "*.yaml filter=attacker\n",
        encoding="utf-8",
    )
    git(repository, "config", "filter.attacker.smudge", str(helper))


class GitFilterIndependentInitialRemoteBootstrapTests(unittest.TestCase):
    def test_ensure_binds_populated_remote_without_smudge_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            remote.mkdir()
            git(remote, "init", "-q", "--bare")

            seed = root / "seed"
            seed.mkdir()
            git(seed, "init", "-q", "-b", "main")
            git(seed, "config", "user.name", "SyncApp Test")
            git(seed, "config", "user.email", "syncapp-test@example.invalid")
            (seed / "configuration.yaml").write_text("remote: true\n", encoding="utf-8")
            git(seed, "add", "configuration.yaml")
            git(seed, "commit", "-qm", "remote baseline")
            expected_commit = git(seed, "rev-parse", "HEAD")
            git(seed, "remote", "add", "origin", str(remote))
            git(seed, "push", "-q", "origin", "main")

            marker = root / "smudge-ran"
            helper = root / "smudge.sh"
            helper.write_text(
                f"#!/bin/sh\nprintf ran >> {marker!s}\ncat\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)

            # Demonstrate the exact bootstrap operation being removed can execute the
            # repository-local smudge helper.
            ordinary = root / "ordinary"
            ordinary.mkdir()
            git(ordinary, "init", "-q", "-b", "main")
            git(ordinary, "remote", "add", "origin", str(remote))
            configure_filter(ordinary, helper)
            git(ordinary, "fetch", "-q", "origin", "main")
            git(ordinary, "checkout", "-q", "-B", "main", "origin/main")
            self.assertTrue(marker.exists())
            marker.unlink()

            work = root / "work"
            work.mkdir()
            git(work, "init", "-q", "-b", "main")
            git(work, "remote", "add", "origin", str(remote))
            configure_filter(work, helper)

            repository = GitRepository(
                path=work,
                remote_url=str(remote),
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.ensure()

            self.assertFalse(marker.exists())
            self.assertEqual(repository.head(), expected_commit)
            self.assertEqual(repository.remote_head(), expected_commit)
            self.assertEqual(repository.relationship(), "equal")
            self.assertFalse((work / "configuration.yaml").exists())
            entries = repository.index_tree_entries()
            self.assertEqual([entry.path for entry in entries], ["configuration.yaml"])
            self.assertEqual(repository.read_blob(entries[0].object_id), b"remote: true\n")


if __name__ == "__main__":
    unittest.main()
