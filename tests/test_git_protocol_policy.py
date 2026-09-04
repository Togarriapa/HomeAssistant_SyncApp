import os
from pathlib import Path
from unittest import mock
import unittest

from syncapp.git_repo import GitRepository


def command_scope_config(environment: dict[str, str]) -> list[tuple[str, str]]:
    count = int(environment["GIT_CONFIG_COUNT"])
    return [
        (
            environment[f"GIT_CONFIG_KEY_{index}"],
            environment[f"GIT_CONFIG_VALUE_{index}"],
        )
        for index in range(count)
    ]


class GitProtocolPolicyTests(unittest.TestCase):
    def repository(self, remote_url: str) -> GitRepository:
        return GitRepository(
            path=Path("/unused"),
            remote_url=remote_url,
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

    def test_github_transport_denies_every_protocol_except_https(self) -> None:
        environment = self.repository(
            "https://github.com/example/home-assistant-config.git"
        )._environment()
        config = command_scope_config(environment)

        self.assertIn(("protocol.allow", "never"), config)
        self.assertIn(("protocol.https.allow", "always"), config)
        self.assertLess(
            config.index(("protocol.allow", "never")),
            config.index(("protocol.https.allow", "always")),
        )

    def test_ambient_git_config_cannot_reenable_external_protocols(self) -> None:
        poisoned = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "protocol.allow",
            "GIT_CONFIG_VALUE_0": "always",
            "GIT_CONFIG_KEY_1": "protocol.ext.allow",
            "GIT_CONFIG_VALUE_1": "always",
        }
        with mock.patch.dict(os.environ, poisoned, clear=False):
            environment = self.repository(
                "https://github.com/example/home-assistant-config.git"
            )._environment()

        config = command_scope_config(environment)
        self.assertIn(("protocol.allow", "never"), config)
        self.assertIn(("protocol.https.allow", "always"), config)
        self.assertNotIn(("protocol.allow", "always"), config)
        self.assertNotIn(("protocol.ext.allow", "always"), config)

    def test_literal_test_remotes_keep_existing_local_transport_behavior(self) -> None:
        environment = self.repository("/tmp/syncapp-test-remote.git")._environment()
        config = command_scope_config(environment)

        self.assertNotIn(("protocol.allow", "never"), config)
        self.assertNotIn(("protocol.https.allow", "always"), config)


if __name__ == "__main__":
    unittest.main()
