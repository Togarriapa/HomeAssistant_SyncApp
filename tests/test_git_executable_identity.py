import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitRepository


class GitExecutableIdentityTests(unittest.TestCase):
    def test_git_subprocesses_ignore_hostile_path_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attacker_bin = root / "attacker-bin"
            attacker_bin.mkdir()
            marker = root / "attacker-git-ran"
            fake_git = attacker_bin / "git"
            fake_git.write_text(
                f"#!/bin/sh\necho ran > {marker}\nexit 97\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)

            work = root / "work"
            work.mkdir()
            repository = GitRepository(
                path=work,
                remote_url="https://github.com/example/syncapp-test.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            with patch.dict(os.environ, {"PATH": str(attacker_bin)}, clear=False):
                text_result = repository._run("--version", cwd=root)
                bytes_result = repository._run_bytes("--version")

            self.assertEqual(text_result.returncode, 0)
            self.assertTrue(text_result.stdout.startswith("git version "))
            self.assertEqual(bytes_result.returncode, 0)
            self.assertTrue(bytes_result.stdout.startswith(b"git version "))
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
