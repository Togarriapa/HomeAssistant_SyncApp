import unittest

from syncapp.policy import is_allowed_relative


class PolicyTests(unittest.TestCase):
    def test_allows_configuration_files(self):
        self.assertTrue(is_allowed_relative("configuration.yaml"))
        self.assertTrue(is_allowed_relative("automations.yaml"))
        self.assertTrue(is_allowed_relative("packages/lights.yaml"))
        self.assertTrue(is_allowed_relative("custom_components/example/manifest.json"))

    def test_blocks_secrets_runtime_state_and_git_attributes(self):
        for path in (
            "secrets.yaml",
            ".storage/core.config_entries",
            "home-assistant_v2.db",
            "home-assistant_v2.db-wal",
            "home-assistant.log",
            "certs/private.key",
            "deps/cache.bin",
            ".gitattributes",
            "packages/.gitattributes",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_allowed_relative(path))

    def test_blocks_parent_traversal(self):
        self.assertFalse(is_allowed_relative("../secrets.yaml"))


if __name__ == "__main__":
    unittest.main()
