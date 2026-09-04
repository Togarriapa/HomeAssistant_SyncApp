from pathlib import Path
import subprocess
import tempfile
import unittest

from syncapp.git_repo import GitRepository


class GitIgnoreIndependentStagingTests(unittest.TestCase):
    def repository(self, root: Path) -> GitRepository:
        return GitRepository(
            path=root,
            remote_url="/tmp/syncapp-test-remote.git",
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

    def test_info_exclude_cannot_hide_managed_file_from_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            info_exclude = root / ".git" / "info" / "exclude"
            info_exclude.write_text("automations.yaml\n", encoding="utf-8")
            managed = root / "automations.yaml"
            managed.write_text("[]\n", encoding="utf-8")

            ignored = subprocess.run(
                ["git", "check-ignore", "-q", "automations.yaml"],
                cwd=root,
                check=False,
            )
            self.assertEqual(ignored.returncode, 0)

            repository = self.repository(root)
            repository.add_all()

            self.assertIn("automations.yaml", repository.tracked_paths())
            self.assertIn("automations.yaml", repository.staged_paths())

    def test_worktree_gitignore_cannot_hide_managed_file_from_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            (root / ".gitignore").write_text("scripts.yaml\n", encoding="utf-8")
            (root / "scripts.yaml").write_text("{}\n", encoding="utf-8")

            repository = self.repository(root)
            repository.add_all()

            self.assertIn("scripts.yaml", repository.tracked_paths())
            self.assertIn("scripts.yaml", repository.staged_paths())


if __name__ == "__main__":
    unittest.main()
