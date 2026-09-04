import os
import unittest
from unittest.mock import patch

from syncapp.runtime_environment import (
    lock_git_tls_negotiation_defaults,
    scrub_ambient_git_tls_client_credentials,
    scrub_ambient_proxy_environment,
    scrub_legacy_git_curl_verbose,
)


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_scrubs_all_supported_ambient_proxy_spellings(self) -> None:
        environment = {
            "http_proxy": "http://attacker.invalid:8001",
            "https_proxy": "http://attacker.invalid:8002",
            "all_proxy": "socks5://attacker.invalid:8003",
            "no_proxy": "github.com",
            "HTTP_PROXY": "http://attacker.invalid:8011",
            "HTTPS_PROXY": "http://attacker.invalid:8012",
            "ALL_PROXY": "socks5://attacker.invalid:8013",
            "NO_PROXY": "github.com",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        scrub_ambient_proxy_environment(environment)

        self.assertEqual(environment, {"SYNCAPP_SENTINEL": "preserve-me"})

    def test_default_target_scrubs_process_environment(self) -> None:
        poisoned = {
            "http_proxy": "http://attacker.invalid:9001",
            "HTTPS_PROXY": "http://attacker.invalid:9002",
            "NO_PROXY": "github.com",
            "SYNCAPP_SENTINEL": "preserve-me",
        }
        with patch.dict(os.environ, poisoned, clear=True):
            scrub_ambient_proxy_environment()
            self.assertEqual(os.environ.get("SYNCAPP_SENTINEL"), "preserve-me")
            self.assertNotIn("http_proxy", os.environ)
            self.assertNotIn("HTTPS_PROXY", os.environ)
            self.assertNotIn("NO_PROXY", os.environ)

    def test_tls_negotiation_overrides_are_replaced_with_default_sentinels(self) -> None:
        environment = {
            "GIT_SSL_VERSION": "sslv3",
            "GIT_SSL_CIPHER_LIST": "attacker-cipher-policy",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        lock_git_tls_negotiation_defaults(environment)

        self.assertEqual(environment["GIT_SSL_VERSION"], "")
        self.assertEqual(environment["GIT_SSL_CIPHER_LIST"], "")
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_tls_negotiation_defaults_are_applied_to_process_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GIT_SSL_VERSION": "tlsv1.0",
                "GIT_SSL_CIPHER_LIST": "legacy-policy",
            },
            clear=True,
        ):
            lock_git_tls_negotiation_defaults()
            self.assertEqual(os.environ["GIT_SSL_VERSION"], "")
            self.assertEqual(os.environ["GIT_SSL_CIPHER_LIST"], "")

    def test_scrubs_ambient_git_tls_client_credential_selectors(self) -> None:
        environment = {
            "GIT_SSL_CERT": "/tmp/attacker-cert.pem",
            "GIT_SSL_KEY": "/tmp/attacker-key.pem",
            "GIT_SSL_CERT_PASSWORD_PROTECTED": "1",
            "GIT_SSL_CERT_TYPE": "P12",
            "GIT_SSL_KEY_TYPE": "ENG",
            "GIT_PROXY_SSL_CERT": "/tmp/attacker-proxy-cert.pem",
            "GIT_PROXY_SSL_KEY": "/tmp/attacker-proxy-key.pem",
            "GIT_PROXY_SSL_CERT_PASSWORD_PROTECTED": "1",
            "GIT_SSL_CAINFO": "/tmp/trusted-custom-ca.pem",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        scrub_ambient_git_tls_client_credentials(environment)

        self.assertEqual(environment["GIT_SSL_CAINFO"], "/tmp/trusted-custom-ca.pem")
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")
        for key in (
            "GIT_SSL_CERT",
            "GIT_SSL_KEY",
            "GIT_SSL_CERT_PASSWORD_PROTECTED",
            "GIT_SSL_CERT_TYPE",
            "GIT_SSL_KEY_TYPE",
            "GIT_PROXY_SSL_CERT",
            "GIT_PROXY_SSL_KEY",
            "GIT_PROXY_SSL_CERT_PASSWORD_PROTECTED",
        ):
            self.assertNotIn(key, environment)

    def test_tls_client_credential_scrub_targets_process_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GIT_SSL_CERT": "/tmp/attacker-cert.pem",
                "GIT_SSL_KEY": "/tmp/attacker-key.pem",
            },
            clear=True,
        ):
            scrub_ambient_git_tls_client_credentials()
            self.assertNotIn("GIT_SSL_CERT", os.environ)
            self.assertNotIn("GIT_SSL_KEY", os.environ)

    def test_legacy_curl_verbose_is_removed_without_touching_unrelated_state(self) -> None:
        environment = {
            "GIT_CURL_VERBOSE": "1",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        scrub_legacy_git_curl_verbose(environment)

        self.assertNotIn("GIT_CURL_VERBOSE", environment)
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_legacy_curl_verbose_scrub_targets_process_environment(self) -> None:
        with patch.dict(os.environ, {"GIT_CURL_VERBOSE": "1"}, clear=True):
            scrub_legacy_git_curl_verbose()
            self.assertNotIn("GIT_CURL_VERBOSE", os.environ)


if __name__ == "__main__":
    unittest.main()
