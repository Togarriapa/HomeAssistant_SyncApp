from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitError, GitRepository


class GitFilterIndependentIndexTests(unittest.TestCase):
    def repository(self, root: Path) -> GitRepository:
        return GitRepository(
            path=root,
            remote_url="/tmp/syncapp-test-remote.git",
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

    def init_repository(self, root: Path) -> None:
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "SyncApp Test"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "syncapp-test@example.invalid"],
            check=True,
        )

    def test_info_attributes_clean_filter_never_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            self.init_repository(root)
            marker = Path(tmp) / "filter-ran"
            helper = Path(tmp) / "filter.sh"
            helper.write_text(
                f"#!/bin/sh\nprintf ran >> {marker!s}\ncat\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)

            managed = root / "configuration.yaml"
            expected = b"homeassistant:\n  name: Safe\n"
            managed.write_bytes(expected)
            info_attributes = root / ".git" / "info" / "attributes"
            info_attributes.write_text("*.yaml filter=attacker\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "config", "filter.attacker.clean", str(helper)],
                check=True,
            )

            # Prove the repository-local attribute really can execute the configured filter
            # for an ordinary staging operation, then clear that evidence before SyncApp runs.
            subprocess.run(["git", "-C", str(root), "add", "configuration.yaml"], check=True)
            self.assertTrue(marker.exists())
            subprocess.run(["git", "-C", str(root), "reset", "-q"], check=True)
            marker.unlink()

            repository = self.repository(root)
            repository.add_all()

            self.assertFalse(marker.exists())
            entries = repository.index_tree_entries()
            self.assertEqual([entry.path for entry in entries], ["configuration.yaml"])
            self.assertEqual(entries[0].mode, "100644")
            self.assertEqual(repository.read_blob(entries[0].object_id), expected)

    def test_exact_index_preserves_baseline_mode_and_stages_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            self.init_repository(root)
            executable = root / "shell_command.sh"
            executable.write_text("#!/bin/sh\necho old\n", encoding="utf-8")
            executable.chmod(0o755)
            removed = root / "old.yaml"
            removed.write_text("old: true\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)

            executable.write_text("#!/bin/sh\necho new\n", encoding="utf-8")
            removed.unlink()

            repository = self.repository(root)
            repository.add_all()

            entries = {entry.path: entry for entry in repository.index_tree_entries()}
            self.assertEqual(set(entries), {"shell_command.sh"})
            self.assertEqual(entries["shell_command.sh"].mode, "100755")
            self.assertIn("old.yaml", repository.staged_paths())
            self.assertIn("shell_command.sh", repository.staged_paths())

    def test_blocked_baseline_entry_is_rejected_before_index_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            self.init_repository(root)
            blocked = root / "secrets.yaml"
            blocked.write_text("password: never-publish\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "secrets.yaml"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "unsafe baseline"], check=True)

            repository = self.repository(root)
            with self.assertRaisesRegex(GitError, "unsafe entry"):
                repository.add_all()

            self.assertEqual(repository.tracked_paths(), ["secrets.yaml"])


if __name__ == "__main__":
    unittest.main()
