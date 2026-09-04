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


class GitFilterIndependentCandidateDiscardTests(unittest.TestCase):
    def test_discard_resets_index_without_executing_smudge_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "SyncApp Test")
            git(root, "config", "user.email", "syncapp-test@example.invalid")

            managed = root / "configuration.yaml"
            managed.write_text("version: baseline\n", encoding="utf-8")
            git(root, "add", "configuration.yaml")
            git(root, "commit", "-qm", "baseline")
            baseline = git(root, "rev-parse", "HEAD")

            marker = Path(tmp) / "smudge-ran"
            helper = Path(tmp) / "smudge.sh"
            helper.write_text(
                f"#!/bin/sh\nprintf ran >> {marker!s}\ncat\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)
            (root / ".git" / "info" / "attributes").write_text(
                "*.yaml filter=attacker\n",
                encoding="utf-8",
            )
            git(root, "config", "filter.attacker.smudge", str(helper))

            managed.write_text("version: candidate\n", encoding="utf-8")
            git(root, "reset", "--hard", "HEAD")
            self.assertTrue(marker.exists())

            marker.unlink()
            managed.write_text("version: candidate\n", encoding="utf-8")
            stale = root / "new-untracked.yaml"
            stale.write_text("new: true\n", encoding="utf-8")

            repository = GitRepository(
                path=root,
                remote_url="/tmp/syncapp-test-remote.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.add_all()
            self.assertTrue(repository.staged_paths())

            repository.discard_worktree_changes()

            self.assertFalse(marker.exists())
            self.assertEqual(repository.head(), baseline)
            self.assertEqual(repository.staged_paths(), [])
            self.assertEqual(managed.read_text(encoding="utf-8"), "version: candidate\n")
            self.assertFalse(stale.exists())
            self.assertEqual(
                repository.read_blob(repository.index_tree_entries()[0].object_id),
                b"version: baseline\n",
            )


if __name__ == "__main__":
    unittest.main()
