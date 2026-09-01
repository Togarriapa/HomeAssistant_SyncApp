import json
from pathlib import Path
import tempfile
import unittest

from syncapp.config import Settings


TARGET = "https://github.com/example/home-assistant-config.git"


class ConfigTests(unittest.TestCase):
    def _load(self, data: dict) -> Settings:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "options.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return Settings.load(path)

    def test_safe_defaults_keep_all_writes_disabled(self) -> None:
        settings = self._load({"homeassistant_repository_url": TARGET})
        self.assertEqual(settings.homeassistant_repository_url, TARGET)
        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.remote_apply_enabled)
        self.assertEqual(settings.verify_timeout_seconds, 120)
        self.assertEqual(settings.backup_retention_count, 10)

    def test_homeassistant_repository_url_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "homeassistant_repository_url is required"):
            self._load({})

    def test_rejects_non_github_repository(self) -> None:
        with self.assertRaisesRegex(ValueError, "github.com"):
            self._load(
                {"homeassistant_repository_url": "https://example.com/config.git"}
            )

    def test_rejects_embedded_repository_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedded credentials"):
            self._load(
                {
                    "homeassistant_repository_url":
                        "https://user:secret@github.com/example/config.git"
                }
            )

    def test_rejects_syncapp_source_repository_as_target(self) -> None:
        for value in (
            "https://github.com/Togarriapa/HomeAssistant_SyncApp",
            "https://github.com/togarriapa/homeassistant_syncapp.git",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "separate Home Assistant"):
                    self._load({"homeassistant_repository_url": value})

    def test_legacy_repository_url_remains_accepted_for_upgrade(self) -> None:
        settings = self._load({"repository_url": TARGET})
        self.assertEqual(settings.homeassistant_repository_url, TARGET)

    def test_matching_new_and_legacy_repository_options_are_accepted(self) -> None:
        settings = self._load(
            {
                "homeassistant_repository_url": TARGET,
                "repository_url": "https://github.com/example/home-assistant-config",
            }
        )
        self.assertEqual(settings.homeassistant_repository_url, TARGET)

    def test_conflicting_new_and_legacy_repository_options_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "disagree"):
            self._load(
                {
                    "homeassistant_repository_url": TARGET,
                    "repository_url": "https://github.com/example/other-config.git",
                }
            )

    def test_remote_apply_requires_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "github_token"):
            self._load(
                {
                    "homeassistant_repository_url": TARGET,
                    "remote_apply_enabled": True,
                }
            )

    def test_write_enabled_configuration_accepts_token(self) -> None:
        settings = self._load(
            {
                "homeassistant_repository_url": TARGET,
                "github_token": "token",
                "dry_run": False,
                "remote_apply_enabled": True,
                "verify_timeout_seconds": 300,
                "backup_retention_count": 25,
            }
        )
        self.assertFalse(settings.dry_run)
        self.assertTrue(settings.remote_apply_enabled)
        self.assertEqual(settings.verify_timeout_seconds, 300)
        self.assertEqual(settings.backup_retention_count, 25)

    def test_verify_timeout_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 30 and 600"):
            self._load(
                {
                    "homeassistant_repository_url": TARGET,
                    "verify_timeout_seconds": 601,
                }
            )

    def test_backup_retention_bounds_are_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self._load(
                {
                    "homeassistant_repository_url": TARGET,
                    "backup_retention_count": 101,
                }
            )
        settings = self._load(
            {
                "homeassistant_repository_url": TARGET,
                "backup_retention_count": 0,
            }
        )
        self.assertEqual(settings.backup_retention_count, 0)


if __name__ == "__main__":
    unittest.main()
