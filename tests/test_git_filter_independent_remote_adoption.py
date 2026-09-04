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


class GitFilterIndependentRemoteAdoptionTests(unittest.TestCase):
    def test_adopt_remote_does_not_execute_info_attributes_smudge_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "SyncApp Test")
            git(root, "config", "user.email", "syncapp-test@example.invalid")

            managed = root / "configuration.yaml"
            managed.write_text("version: old\n", encoding="utf-8")
            git(root, "add", "configuration.yaml")
            git(root, "commit", "-qm", "old")
            old_commit = git(root, "rev-parse", "HEAD")

            managed.write_text("version: remote\n", encoding="utf-8")
            git(root, "add", "configuration.yaml")
            git(root, "commit", "-qm", "remote")
            expected_commit = git(root, "rev-parse", "HEAD")

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

            # Demonstrate that the metadata-local attributes source really can execute
            # the configured helper during a normal hard reset.
            git(root, "reset", "--hard", old_commit)
            git(root, "reset", "--hard", expected_commit)
            self.assertTrue(marker.exists())

            # Return to an old worktree without checkout/smudge, then make the remote
            # tracking ref identify the already-fetched verified commit.
            git(root, "reset", "--mixed", old_commit)
            managed.write_text("version: old\n", encoding="utf-8")
            marker.unlink()
            stale = root / "stale-untracked.yaml"
            stale.write_text("stale: true\n", encoding="utf-8")
            git(root, "update-ref", "refs/remotes/origin/main", expected_commit)

            repository = GitRepository(
                path=root,
                remote_url="/tmp/syncapp-test-remote.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            repository.adopt_remote(expected_commit)

            self.assertFalse(marker.exists())
            self.assertEqual(repository.head(), expected_commit)
            self.assertEqual(repository.relationship(), "equal")
            self.assertEqual(managed.read_text(encoding="utf-8"), "version: old\n")
            self.assertFalse(stale.exists())
            self.assertEqual(
                {entry.path for entry in repository.index_tree_entries()},
                {"configuration.yaml"},
            )


if __name__ == "__main__":
    unittest.main()
