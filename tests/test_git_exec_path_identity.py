import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitRepository


class GitExecPathIdentityTests(unittest.TestCase):
    def test_ambient_git_exec_path_is_replaced_with_image_owned_helper_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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

            with patch.dict(
                os.environ,
                {"GIT_EXEC_PATH": str(root / "attacker-git-core")},
                clear=False,
            ):
                environment = repository._environment()
                reported = repository._run("--exec-path", cwd=root).stdout.strip()

            self.assertEqual(environment["GIT_EXEC_PATH"], "/usr/libexec/git-core")
            self.assertEqual(reported, "/usr/libexec/git-core")
            self.assertNotIn("attacker", " ".join(environment.values()))


if __name__ == "__main__":
    unittest.main()
