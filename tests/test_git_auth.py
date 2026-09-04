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

    def _assert_transport_rewrite_lock(
        self, environment: dict[str, str], remote_url: str
    ) -> None:
        transport_alias = f"{remote_url}#syncapp-authoritative-transport"
        self.assertEqual(environment["GIT_CONFIG_KEY_3"], f"url.{remote_url}.insteadOf")
        self.assertEqual(environment["GIT_CONFIG_VALUE_3"], transport_alias)
        self.assertEqual(
            environment["GIT_CONFIG_KEY_4"], f"url.{remote_url}.pushInsteadOf"
        )
        self.assertEqual(environment["GIT_CONFIG_VALUE_4"], transport_alias)

    def _assert_execution_controls(self, environment: dict[str, str]) -> None:
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "core.hooksPath")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "core.fsmonitor")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "false")
        self.assertEqual(environment["GIT_CONFIG_KEY_2"], "credential.helper")
        self.assertEqual(environment["GIT_CONFIG_VALUE_2"], "")

    def test_token_is_refused_for_non_github_remote(self) -> None:
        repository = self._repository("https://example.com/config.git", "secret-token")
        with self.assertRaisesRegex(GitError, "non-GitHub"):
            repository._environment()

    def test_github_remote_receives_host_scoped_authorization_header(self) -> None:
        remote_url = "https://github.com/example/config.git"
        repository = self._repository(remote_url, "secret-token")
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "6")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertEqual(
            environment["GIT_CONFIG_KEY_5"],
            "http.https://github.com/.extraHeader",
        )
        self.assertTrue(environment["GIT_CONFIG_VALUE_5"].startswith("Authorization: Basic "))
        self.assertNotIn("secret-token", environment["GIT_CONFIG_VALUE_5"])

    def test_no_token_still_disables_repository_execution_helpers(self) -> None:
        remote_url = "/tmp/local.git"
        repository = self._repository(remote_url, None)
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "5")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertFalse(
            any(
                value.startswith("Authorization: Basic ")
                for key, value in environment.items()
                if key.startswith("GIT_CONFIG_VALUE_")
            )
        )

    def test_ambient_git_overrides_are_scrubbed(self) -> None:
        remote_url = "https://github.com/example/config.git"
        repository = self._repository(remote_url, None)
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
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "5")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertNotIn("example.invalid", " ".join(environment.values()))


if __name__ == "__main__":
    unittest.main()