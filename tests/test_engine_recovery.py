from types import SimpleNamespace
import unittest
from unittest.mock import patch

from syncapp.engine import SyncEngine


class EngineRecoveryBoundaryTests(unittest.TestCase):
    def test_engine_passes_repository_to_recovery_before_git_activity(self):
        settings = SimpleNamespace(
            repository_dir="/tmp/not-used",
            repository_url="https://github.com/example/config.git",
            branch="main",
            github_token="token",
            git_user_name="SyncApp Test",
            git_user_email="syncapp@example.com",
        )
        engine = SyncEngine(settings)

        with patch("syncapp.engine.recover_interrupted_apply", return_value=True) as recover, patch.object(
            engine.repository, "ensure"
        ) as ensure:
            engine.run_once()

        recover.assert_called_once_with(settings, engine.repository)
        ensure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
