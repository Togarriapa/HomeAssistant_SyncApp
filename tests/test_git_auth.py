import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitError, GitRepository


class GitAuthTests(unittest.TestCase):
    def _repository(self, remote_url: str, token: str | None) -> GitRepository:
        return GitRepository(
            path=Path(tempfile.gettempdir()) / "syncapp-auth-test",
            remote_url=remote_url,
            branch="main",
            token=token,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

    def test_token_is_refused_for_non_github_remote(self) -> None:
        repository = self._repository("https://example.com/config.git", "secret-token")
        with self.assertRaisesRegex(GitError, "non-GitHub"):
            repository._environment()

    def test_github_remote_receives_host_scoped_authorization_header(self) -> None:
        repository = self._repository("https://github.com/example/config.git", "secret-token")
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "3")
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "core.hooksPath")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "credential.helper")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "")
        self.assertEqual(
            environment["GIT_CONFIG_KEY_2"],
            "http.https://github.com/.extraHeader",
        )
        self.assertTrue(environment["GIT_CONFIG_VALUE_2"].startswith("Authorization: Basic "))
        self.assertNotIn("secret-token", environment["GIT_CONFIG_VALUE_2"])

    def test_no_token_still_disables_hooks_and_credential_helpers(self) -> None:
        repository = self._repository("/tmp/local.git", None)
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "core.hooksPath")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "credential.helper")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "")
        self.assertFalse(
            any(
                value.startswith("Authorization: Basic ")
                for key, value in environment.items()
                if key.startswith("GIT_CONFIG_VALUE_")
            )
        )

    def test_ambient_git_overrides_are_scrubbed(self) -> None:
        repository = self._repository("https://github.com/example/config.git", None)
        poisoned = {
            "GIT_DIR": "/tmp/attacker-dir",
            "GIT_WORK_TREE": "/tmp/attacker-worktree",
            "GIT_TEMPLATE_DIR": "/tmp/attacker-template",
            "GIT_ASKPASS": "/tmp/attacker-askpass",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.https://example.invalid/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
            "GIT_CONFIG_GLOBAL": "/tmp/attacker-global-config",
        }
        with patch.dict(os.environ, poisoned, clear=False):
            environment = repository._environment()

        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_TEMPLATE_DIR", "GIT_ASKPASS"):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "core.hooksPath")
        self.assertNotIn("insteadOf", " ".join(environment.values()))


if __name__ == "__main__":
    unittest.main()
