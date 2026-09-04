import os
from pathlib import Path
import subprocess
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
        self.assertEqual(environment["GIT_CONFIG_KEY_12"], f"url.{remote_url}.insteadOf")
        self.assertEqual(environment["GIT_CONFIG_VALUE_12"], transport_alias)
        self.assertEqual(
            environment["GIT_CONFIG_KEY_13"], f"url.{remote_url}.pushInsteadOf"
        )
        self.assertEqual(environment["GIT_CONFIG_VALUE_13"], transport_alias)

    def _assert_execution_controls(self, environment: dict[str, str]) -> None:
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "core.hooksPath")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "core.fsmonitor")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "false")
        self.assertEqual(environment["GIT_CONFIG_KEY_2"], "core.gitProxy")
        self.assertEqual(environment["GIT_CONFIG_VALUE_2"], "none")
        self.assertEqual(environment["GIT_CONFIG_KEY_3"], "credential.helper")
        self.assertEqual(environment["GIT_CONFIG_VALUE_3"], "")
        self.assertEqual(environment["GIT_CONFIG_KEY_4"], "core.attributesFile")
        self.assertEqual(environment["GIT_CONFIG_VALUE_4"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_KEY_5"], "http.sslVerify")
        self.assertEqual(environment["GIT_CONFIG_VALUE_5"], "true")
        self.assertEqual(environment["GIT_CONFIG_KEY_6"], "http.proxySSLVerify")
        self.assertEqual(environment["GIT_CONFIG_VALUE_6"], "true")
        self.assertEqual(environment["GIT_CONFIG_KEY_7"], "http.followRedirects")
        self.assertEqual(environment["GIT_CONFIG_VALUE_7"], "initial")
        self.assertEqual(environment["GIT_CONFIG_KEY_8"], "http.extraHeader")
        self.assertEqual(environment["GIT_CONFIG_VALUE_8"], "")
        self.assertEqual(environment["GIT_CONFIG_KEY_9"], "http.cookieFile")
        self.assertEqual(environment["GIT_CONFIG_VALUE_9"], "")
        self.assertEqual(environment["GIT_CONFIG_KEY_10"], "http.saveCookies")
        self.assertEqual(environment["GIT_CONFIG_VALUE_10"], "false")
        self.assertEqual(environment["GIT_CONFIG_KEY_11"], "http.curloptResolve")
        self.assertEqual(environment["GIT_CONFIG_VALUE_11"], "")
        self.assertEqual(environment["GIT_ATTR_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_ASKPASS"], os.devnull)
        self.assertEqual(environment["SSH_ASKPASS"], os.devnull)
        self.assertEqual(environment["GIT_SSH_COMMAND"], "ssh")

    def test_token_is_refused_for_non_github_remote(self) -> None:
        repository = self._repository("https://example.com/config.git", "secret-token")
        with self.assertRaisesRegex(GitError, "non-GitHub"):
            repository._environment()

    def test_github_remote_receives_host_scoped_authorization_header(self) -> None:
        remote_url = "https://github.com/example/config.git"
        repository = self._repository(remote_url, "secret-token")
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "15")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertEqual(
            environment["GIT_CONFIG_KEY_14"],
            "http.https://github.com/.extraHeader",
        )
        self.assertTrue(environment["GIT_CONFIG_VALUE_14"].startswith("Authorization: Basic "))
        self.assertNotIn("secret-token", environment["GIT_CONFIG_VALUE_14"])

    def test_no_token_still_disables_repository_execution_helpers(self) -> None:
        remote_url = "/tmp/local.git"
        repository = self._repository(remote_url, None)
        environment = repository._environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "14")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertFalse(
            any(
                value.startswith("Authorization: Basic ")
                for key, value in environment.items()
                if key.startswith("GIT_CONFIG_VALUE_")
            )
        )

    def test_ambient_git_overrides_are_scrubbed_before_safe_helpers_are_installed(self) -> None:
        remote_url = "https://github.com/example/config.git"
        repository = self._repository(remote_url, None)
        poisoned = {
            "GIT_DIR": "/tmp/attacker-dir",
            "GIT_WORK_TREE": "/tmp/attacker-worktree",
            "GIT_TEMPLATE_DIR": "/tmp/attacker-template",
            "GIT_ASKPASS": "/tmp/attacker-askpass",
            "SSH_ASKPASS": "/tmp/attacker-ssh-askpass",
            "GIT_SSH_COMMAND": "/tmp/attacker-ssh",
            "GIT_PROXY_COMMAND": "/tmp/attacker-proxy",
            "GIT_SSL_NO_VERIFY": "1",
            "GIT_ATTR_SOURCE": "attacker-treeish",
            "GIT_ATTR_NOSYSTEM": "0",
            "GIT_TRACE": "1",
            "GIT_TRACE_CURL": "/tmp/attacker-curl-trace",
            "GIT_TRACE_CURL_NO_DATA": "0",
            "GIT_TRACE_REDACT": "0",
            "GIT_TRACE2": "/tmp/attacker-trace2",
            "GIT_TRACE2_EVENT": "/tmp/attacker-trace2-event",
            "GIT_TRACE2_PERF": "/tmp/attacker-trace2-perf",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.https://example.invalid/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
            "GIT_CONFIG_GLOBAL": "/tmp/attacker-global-config",
        }
        with patch.dict(os.environ, poisoned, clear=False):
            environment = repository._environment()

        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_TEMPLATE_DIR",
            "GIT_PROXY_COMMAND",
            "GIT_SSL_NO_VERIFY",
            "GIT_ATTR_SOURCE",
            "GIT_TRACE",
            "GIT_TRACE_CURL",
            "GIT_TRACE_CURL_NO_DATA",
            "GIT_TRACE_REDACT",
            "GIT_TRACE2",
            "GIT_TRACE2_EVENT",
            "GIT_TRACE2_PERF",
        ):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_ATTR_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "14")
        self._assert_execution_controls(environment)
        self._assert_transport_rewrite_lock(environment, remote_url)
        self.assertNotIn("attacker", " ".join(environment.values()))
        self.assertNotIn("example.invalid", " ".join(environment.values()))

    def test_repository_local_git_proxy_is_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "core.gitProxy", "/tmp/attacker-proxy"],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            effective = repository._run("config", "--get", "core.gitProxy").stdout.strip()

            self.assertEqual(effective, "none")

    def test_repository_local_attributes_file_is_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "core.attributesFile",
                    "/tmp/attacker-attributes",
                ],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            effective = repository._run(
                "config", "--get", "core.attributesFile"
            ).stdout.strip()

            self.assertEqual(effective, os.devnull)

    def test_repository_local_tls_verification_disables_are_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "http.sslVerify", "false"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "http.proxySSLVerify", "false"],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            ssl_verify = repository._run("config", "--get", "http.sslVerify").stdout.strip()
            proxy_ssl_verify = repository._run(
                "config", "--get", "http.proxySSLVerify"
            ).stdout.strip()

            self.assertEqual(ssl_verify, "true")
            self.assertEqual(proxy_ssl_verify, "true")

    def test_repository_local_unrestricted_redirects_are_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "http.followRedirects", "true"],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            follow_redirects = repository._run(
                "config", "--get", "http.followRedirects"
            ).stdout.strip()

            self.assertEqual(follow_redirects, "initial")

    def test_repository_local_http_extra_headers_are_reset_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            injected = "X-SyncApp-Attacker: injected"
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "--add",
                    "http.extraHeader",
                    injected,
                ],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            headers = repository._run("config", "--get-all", "http.extraHeader")
            values = headers.stdout.splitlines()

            self.assertEqual(headers.returncode, 0)
            self.assertIn(injected, values)
            self.assertTrue(values)
            self.assertEqual(values[-1], "")

    def test_repository_local_http_cookie_persistence_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "http.cookieFile",
                    "/tmp/syncapp-attacker-cookies",
                ],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "http.saveCookies", "true"],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            cookie_file = repository._run("config", "--get", "http.cookieFile")
            save_cookies = repository._run(
                "config", "--get", "http.saveCookies"
            ).stdout.strip()

            self.assertEqual(cookie_file.returncode, 0)
            self.assertEqual(cookie_file.stdout.strip(), "")
            self.assertEqual(save_cookies, "false")

    def test_repository_local_http_dns_overrides_are_reset_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            injected = "+github.com:443:127.0.0.1"
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "--add",
                    "http.curloptResolve",
                    injected,
                ],
                check=True,
            )
            repository = GitRepository(
                path=root,
                remote_url="https://github.com/example/config.git",
                branch="main",
                token=None,
                user_name="SyncApp Test",
                user_email="syncapp-test@example.invalid",
            )

            resolves = repository._run("config", "--get-all", "http.curloptResolve")
            values = resolves.stdout.splitlines()

            self.assertEqual(resolves.returncode, 0)
            self.assertIn(injected, values)
            self.assertTrue(values)
            self.assertEqual(values[-1], "")


if __name__ == "__main__":
    unittest.main()
