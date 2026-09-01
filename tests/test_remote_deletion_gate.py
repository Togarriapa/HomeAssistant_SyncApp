from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from syncapp.apply import _execute_staged_apply
from syncapp.config import Settings
from syncapp.staging import StagingResult
from syncapp.transaction import TransactionError


class RemoteDeletionGateIntegrationTests(unittest.TestCase):
    def test_over_budget_candidate_is_rejected_before_supervisor_or_live_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            live.mkdir()
            staging.mkdir()

            for name in ("configuration.yaml", "automations.yaml", "scripts.yaml"):
                (live / name).write_text(f"{name}: live\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text(
                "configuration.yaml: live\n", encoding="utf-8"
            )

            settings = Settings(
                repository_url="https://github.com/example/config.git",
                branch="main",
                github_token=None,
                poll_interval_seconds=60,
                dry_run=False,
                remote_apply_enabled=True,
                verify_timeout_seconds=30,
                git_user_name="SyncApp test",
                git_user_email="syncapp-test@example.invalid",
                remote_max_deletions=25,
                remote_max_deletion_percent=50,
                source_dir=live,
                repository_dir=root / "repository",
                staging_dir=staging,
                transaction_dir=root / "transaction",
                manifest_path=root / "managed_paths.json",
            )
            staged = StagingResult(commit="a" * 40, file_count=1, total_bytes=25)
            baseline = {"configuration.yaml", "automations.yaml", "scripts.yaml"}

            with patch(
                "syncapp.apply.SupervisorClient",
                side_effect=AssertionError("Supervisor must not be contacted"),
            ):
                with self.assertRaisesRegex(TransactionError, "66.7%"):
                    _execute_staged_apply(object(), settings, staged, baseline)  # type: ignore[arg-type]

            self.assertEqual(
                (live / "automations.yaml").read_text(encoding="utf-8"),
                "automations.yaml: live\n",
            )
            self.assertEqual(
                (live / "scripts.yaml").read_text(encoding="utf-8"),
                "scripts.yaml: live\n",
            )
            self.assertFalse(settings.transaction_dir.exists())


if __name__ == "__main__":
    unittest.main()
