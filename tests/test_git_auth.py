from pathlib import Path
import tempfile
import unittest

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

    def test_github_remote_receives_authorization_header(self) -> None:
        repository = self._repository("https://github.com/example/config.git", "secret-token")
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "http.extraHeader")
        self.assertTrue(environment["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic "))
        self.assertNotIn("secret-token", environment["GIT_CONFIG_VALUE_0"])

    def test_no_token_adds_no_auth_header(self) -> None:
        repository = self._repository("/tmp/local.git", None)
        environment = repository._environment()
        self.assertNotIn("GIT_CONFIG_COUNT", environment)


if __name__ == "__main__":
    unittest.main()
