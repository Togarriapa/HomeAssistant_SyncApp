import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitRepository


class GitUiHelperSafetyTests(unittest.TestCase):
    def test_ambient_ui_and_diff_helpers_are_replaced_with_fixed_system_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = GitRepository(
                path=Path(tmp) / "repository",
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )
            poisoned = {
                "GIT_PAGER": "/tmp/attacker-git-pager",
                "PAGER": "/tmp/attacker-pager",
                "GIT_EDITOR": "/tmp/attacker-git-editor",
                "GIT_SEQUENCE_EDITOR": "/tmp/attacker-sequence-editor",
                "EDITOR": "/tmp/attacker-editor",
                "VISUAL": "/tmp/attacker-visual",
                "GIT_EXTERNAL_DIFF": "/tmp/attacker-diff",
                "GIT_DIFF_OPTS": "--attacker-option",
            }
            with patch.dict(os.environ, poisoned, clear=False):
                environment = repository._environment()

            self.assertEqual(environment["GIT_PAGER"], "/bin/cat")
            self.assertEqual(environment["PAGER"], "/bin/cat")
            self.assertEqual(environment["GIT_EDITOR"], "/bin/false")
            self.assertEqual(environment["GIT_SEQUENCE_EDITOR"], "/bin/false")
            self.assertEqual(environment["EDITOR"], "/bin/false")
            self.assertEqual(environment["VISUAL"], "/bin/false")
            self.assertEqual(environment["GIT_EXTERNAL_DIFF"], "/bin/false")
            self.assertNotIn("GIT_DIFF_OPTS", environment)
            self.assertNotIn("attacker", " ".join(environment.values()))


if __name__ == "__main__":
    unittest.main()
