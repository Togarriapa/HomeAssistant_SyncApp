from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from syncapp.apply import apply_staged_initial_remote
from syncapp.config import Settings
from syncapp.git_repo import GitTreeEntry
from syncapp.staging import stage_remote_configuration
from syncapp.transaction import TransactionError


class FakeRepositoryForStaging:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def remote_head(self) -> str:
        return "e" * 40

    def remote_tree_entries(self) -> list[GitTreeEntry]:
        return [GitTreeEntry("100644", "blob", "blob-config", "configuration.yaml")]

    def blob_size(self, object_id: str) -> int:
        if object_id != "blob-config":
            raise AssertionError("unexpected object")
        return len(self.content)

    def read_blob(self, object_id: str) -> bytes:
        if object_id != "blob-config":
            raise AssertionError("unexpected object")
        return self.content


class StagingBindingApplyGateTests(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            repository_url="https://github.com/example/config.git",
            branch="main",
            github_token="token",
            poll_interval_seconds=60,
            dry_run=False,
            remote_apply_enabled=True,
            verify_timeout_seconds=120,
            git_user_name="SyncApp",
            git_user_email="syncapp@example.invalid",
            initial_remote_apply_enabled=True,
            source_dir=root / "homeassistant",
            repository_dir=root / "repository",
            staging_dir=root / "staging",
            transaction_dir=root / "transaction",
            manifest_path=root / "managed_paths.json",
        )

    def test_tampered_valid_staging_fails_before_any_apply_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = self._settings(root)
            settings.source_dir.mkdir(parents=True)
            original = b"homeassistant:\n  name: Remote original\n"
            staged = stage_remote_configuration(
                FakeRepositoryForStaging(original), settings.staging_dir  # type: ignore[arg-type]
            )
            (settings.staging_dir / "configuration.yaml").write_text(
                "homeassistant:\n  name: Tampered but valid\n", encoding="utf-8"
            )

            repository = MagicMock()
            repository.head.return_value = staged.commit

            with patch("syncapp.apply.SupervisorClient") as supervisor_client, patch(
                "syncapp.apply.FileTransaction.prepare"
            ) as prepare:
                with self.assertRaisesRegex(
                    TransactionError, "staging integrity check failed"
                ):
                    apply_staged_initial_remote(repository, settings, staged)

            supervisor_client.assert_not_called()
            prepare.assert_not_called()
            repository.fetch.assert_not_called()
            repository.adopt_remote.assert_not_called()
            self.assertFalse(settings.manifest_path.exists())
            self.assertFalse(settings.transaction_dir.exists())
            self.assertEqual(list(settings.source_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
