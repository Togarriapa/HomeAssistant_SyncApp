import os
import unittest
from unittest.mock import patch

from syncapp.git_evidence_environment import lock_git_no_lazy_fetch


class GitEvidenceEnvironmentTests(unittest.TestCase):
    def test_lazy_fetch_is_disabled_even_when_ambient_value_allows_it(self) -> None:
        environment = {
            "GIT_NO_LAZY_FETCH": "0",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        lock_git_no_lazy_fetch(environment)

        self.assertEqual(environment["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_lazy_fetch_lock_targets_process_environment(self) -> None:
        with patch.dict(os.environ, {"GIT_NO_LAZY_FETCH": "0"}, clear=True):
            lock_git_no_lazy_fetch()
            self.assertEqual(os.environ["GIT_NO_LAZY_FETCH"], "1")


if __name__ == "__main__":
    unittest.main()
