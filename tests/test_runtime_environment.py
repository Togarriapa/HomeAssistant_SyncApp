import os
import unittest
from unittest.mock import patch

from syncapp.runtime_environment import scrub_ambient_proxy_environment


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


if __name__ == "__main__":
    unittest.main()
