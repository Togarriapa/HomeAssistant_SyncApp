import json
from pathlib import Path
import tempfile
import unittest

from syncapp.config import Settings


class ConfigTests(unittest.TestCase):
    def _load(self, data: dict) -> Settings:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "options.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return Settings.load(path)

    def test_safe_defaults_keep_all_writes_disabled(self) -> None:
        settings = self._load({"repository_url": "https://github.com/example/config.git"})
        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.remote_apply_enabled)
        self.assertFalse(settings.initial_local_publish_enabled)
        self.assertFalse(settings.initial_remote_apply_enabled)
        self.assertEqual(settings.verify_timeout_seconds, 120)
        self.assertEqual(settings.backup_retention_count, 10)

    def test_rejects_non_github_repository(self) -> None:
        with self.assertRaisesRegex(ValueError, "github.com"):
            self._load({"repository_url": "https://example.com/config.git"})

    def test_rejects_embedded_repository_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedded credentials"):
            self._load({"repository_url": "https://user:secret@github.com/example/config.git"})

    def test_remote_apply_requires_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "github_token"):
            self._load(
                {
                    "repository_url": "https://github.com/example/config.git",
                    "remote_apply_enabled": True,
                }
            )

    def test_initial_authority_options_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            self._load(
                {
                    "repository_url": "https://github.com/example/config.git",
                    "initial_local_publish_enabled": True,
                    "initial_remote_apply_enabled": True,
                }
            )

    def test_write_enabled_configuration_accepts_token(self) -> None:
        settings = self._load(
            {
                "repository_url": "https://github.com/example/config.git",
                "github_token": "token",
                "dry_run": False,
                "remote_apply_enabled": True,
                "initial_remote_apply_enabled": True,
                "verify_timeout_seconds": 300,
                "backup_retention_count": 25,
            }
        )
        self.assertFalse(settings.dry_run)
        self.assertTrue(settings.remote_apply_enabled)
        self.assertFalse(settings.initial_local_publish_enabled)
        self.assertTrue(settings.initial_remote_apply_enabled)
        self.assertEqual(settings.verify_timeout_seconds, 300)
        self.assertEqual(settings.backup_retention_count, 25)

    def test_verify_timeout_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 30 and 600"):
            self._load(
                {
                    "repository_url": "https://github.com/example/config.git",
                    "verify_timeout_seconds": 601,
                }
            )

    def test_backup_retention_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self._load(
                {
                    "repository_url": "https://github.com/example/config.git",
                    "backup_retention_count": 101,
                }
            )
        settings = self._load(
            {
                "repository_url": "https://github.com/example/config.git",
                "backup_retention_count": 0,
            }
        )
        self.assertEqual(settings.backup_retention_count, 0)


if __name__ == "__main__":
    unittest.main()
