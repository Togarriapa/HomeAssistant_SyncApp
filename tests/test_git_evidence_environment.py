import os
import unittest
from unittest.mock import patch

from syncapp.git_evidence_environment import (
    lock_git_literal_pathspecs,
    lock_git_no_lazy_fetch,
    lock_git_optional_locks,
    lock_git_protocol_from_user,
    scrub_git_allow_protocol,
)


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

    def test_optional_locks_are_disabled_even_when_ambient_value_enables_them(self) -> None:
        environment = {
            "GIT_OPTIONAL_LOCKS": "1",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        lock_git_optional_locks(environment)

        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_optional_lock_policy_targets_process_environment(self) -> None:
        with patch.dict(os.environ, {"GIT_OPTIONAL_LOCKS": "1"}, clear=True):
            lock_git_optional_locks()
            self.assertEqual(os.environ["GIT_OPTIONAL_LOCKS"], "0")

    def test_user_classified_protocols_are_disabled_even_when_ambient_value_enables_them(self) -> None:
        environment = {
            "GIT_PROTOCOL_FROM_USER": "1",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        lock_git_protocol_from_user(environment)

        self.assertEqual(environment["GIT_PROTOCOL_FROM_USER"], "0")
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_user_protocol_policy_targets_process_environment(self) -> None:
        with patch.dict(os.environ, {"GIT_PROTOCOL_FROM_USER": "1"}, clear=True):
            lock_git_protocol_from_user()
            self.assertEqual(os.environ["GIT_PROTOCOL_FROM_USER"], "0")

    def test_pathspec_policy_replaces_ambient_glob_and_case_controls(self) -> None:
        environment = {
            "GIT_LITERAL_PATHSPECS": "0",
            "GIT_GLOB_PATHSPECS": "1",
            "GIT_NOGLOB_PATHSPECS": "1",
            "GIT_ICASE_PATHSPECS": "1",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        lock_git_literal_pathspecs(environment)

        self.assertEqual(environment["GIT_LITERAL_PATHSPECS"], "1")
        self.assertNotIn("GIT_GLOB_PATHSPECS", environment)
        self.assertNotIn("GIT_NOGLOB_PATHSPECS", environment)
        self.assertNotIn("GIT_ICASE_PATHSPECS", environment)
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_literal_pathspec_policy_targets_process_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GIT_LITERAL_PATHSPECS": "0",
                "GIT_GLOB_PATHSPECS": "1",
                "GIT_ICASE_PATHSPECS": "1",
            },
            clear=True,
        ):
            lock_git_literal_pathspecs()
            self.assertEqual(os.environ["GIT_LITERAL_PATHSPECS"], "1")
            self.assertNotIn("GIT_GLOB_PATHSPECS", os.environ)
            self.assertNotIn("GIT_ICASE_PATHSPECS", os.environ)

    def test_ambient_protocol_whitelist_is_removed_without_touching_other_state(self) -> None:
        environment = {
            "GIT_ALLOW_PROTOCOL": "https:file:ext",
            "SYNCAPP_SENTINEL": "preserve-me",
        }

        scrub_git_allow_protocol(environment)

        self.assertNotIn("GIT_ALLOW_PROTOCOL", environment)
        self.assertEqual(environment["SYNCAPP_SENTINEL"], "preserve-me")

    def test_protocol_whitelist_scrub_targets_process_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"GIT_ALLOW_PROTOCOL": "https:file:ext", "SYNCAPP_SENTINEL": "preserve-me"},
            clear=True,
        ):
            scrub_git_allow_protocol()
            self.assertNotIn("GIT_ALLOW_PROTOCOL", os.environ)
            self.assertEqual(os.environ["SYNCAPP_SENTINEL"], "preserve-me")


if __name__ == "__main__":
    unittest.main()
