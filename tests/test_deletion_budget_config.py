import json
from pathlib import Path
import tempfile
import unittest

from syncapp.config import Settings


TARGET = "https://github.com/example/home-assistant-config.git"


class DeletionBudgetConfigTests(unittest.TestCase):
    def _load(self, **overrides: object) -> Settings:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "options.json"
            payload: dict[str, object] = {"homeassistant_repository_url": TARGET}
            payload.update(overrides)
            path.write_text(json.dumps(payload), encoding="utf-8")
            return Settings.load(path)

    def test_safe_defaults_limit_large_remote_deletions(self) -> None:
        settings = self._load()
        self.assertEqual(settings.remote_max_deletions, 25)
        self.assertEqual(settings.remote_max_deletion_percent, 50)

    def test_explicit_zero_can_disable_remote_deletions(self) -> None:
        settings = self._load(
            remote_max_deletions=0,
            remote_max_deletion_percent=0,
        )
        self.assertEqual(settings.remote_max_deletions, 0)
        self.assertEqual(settings.remote_max_deletion_percent, 0)

    def test_absolute_deletion_budget_bounds_are_enforced(self) -> None:
        for value in (-1, 10001):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "remote_max_deletions"):
                    self._load(remote_max_deletions=value)

    def test_percentage_deletion_budget_bounds_are_enforced(self) -> None:
        for value in (-1, 101):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "remote_max_deletion_percent"):
                    self._load(remote_max_deletion_percent=value)


if __name__ == "__main__":
    unittest.main()
