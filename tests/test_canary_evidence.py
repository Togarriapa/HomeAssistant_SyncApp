import json
import unittest
from unittest import mock

import canary_evidence


GOOD_SHA = "a" * 64
OTHER_SHA = "b" * 64


class CanaryEvidenceTests(unittest.TestCase):
    def test_runtime_fingerprint_exact_match_is_returned(self):
        evidence = {
            "schema": "syncapp-runtime-v1",
            "algorithm": "sha256",
            "sha256": GOOD_SHA,
            "files": 42,
        }
        with mock.patch("canary_evidence.runtime_fingerprint", return_value=evidence):
            self.assertEqual(
                canary_evidence._verified_runtime_fingerprint(GOOD_SHA),
                evidence,
            )

    def test_runtime_fingerprint_mismatch_fails_closed(self):
        with mock.patch(
            "canary_evidence.runtime_fingerprint",
            return_value={
                "schema": "syncapp-runtime-v1",
                "algorithm": "sha256",
                "sha256": OTHER_SHA,
                "files": 42,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "does not match the expected green CI image"):
                canary_evidence._verified_runtime_fingerprint(GOOD_SHA)

    def test_invalid_expected_digest_is_rejected(self):
        with mock.patch(
            "canary_evidence.runtime_fingerprint",
            return_value={
                "schema": "syncapp-runtime-v1",
                "algorithm": "sha256",
                "sha256": GOOD_SHA,
                "files": 42,
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "expected runtime SHA-256"):
                canary_evidence._verified_runtime_fingerprint("not-a-digest")

    def test_identity_mismatch_happens_before_supervisor_or_canary_operations(self):
        with mock.patch(
            "canary_evidence._verified_runtime_fingerprint",
            side_effect=RuntimeError("identity mismatch"),
        ), mock.patch("canary_evidence.SupervisorClient") as supervisor, mock.patch(
            "canary_evidence.run_canary"
        ) as run_canary, mock.patch(
            "canary_evidence.argparse.ArgumentParser.parse_args",
            return_value=mock.Mock(
                expected_runtime_sha256=GOOD_SHA,
                timeout=120,
                backup_archive_max_mib=1024,
                restart=False,
                backup=False,
                backup_archive_probe=False,
                filesystem=False,
                filesystem_write_probe=False,
                filesystem_path="configuration.yaml",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
                canary_evidence.main()
        supervisor.assert_not_called()
        run_canary.assert_not_called()

    def test_output_binds_runtime_identity_and_canary_result(self):
        runtime = {
            "schema": "syncapp-runtime-v1",
            "algorithm": "sha256",
            "sha256": GOOD_SHA,
            "files": 42,
        }
        canary_result = {
            "environment": {"core": {"version": "2026.9.0"}},
            "core_api": {"message": "API running."},
            "configuration_check": {},
        }
        args = mock.Mock(
            expected_runtime_sha256=GOOD_SHA,
            timeout=120,
            backup_archive_max_mib=1024,
            restart=False,
            backup=False,
            backup_archive_probe=False,
            filesystem=False,
            filesystem_write_probe=False,
            filesystem_path="configuration.yaml",
        )
        with mock.patch(
            "canary_evidence.argparse.ArgumentParser.parse_args", return_value=args
        ), mock.patch(
            "canary_evidence._verified_runtime_fingerprint", return_value=runtime
        ), mock.patch("canary_evidence.SupervisorClient", return_value=object()), mock.patch(
            "canary_evidence.run_canary", return_value=canary_result
        ), mock.patch("builtins.print") as emit:
            self.assertEqual(canary_evidence.main(), 0)

        rendered = json.loads(emit.call_args.args[0])
        self.assertEqual(rendered["runtime_image"], runtime)
        self.assertEqual(rendered["environment"], canary_result["environment"])
        self.assertEqual(rendered["core_api"], canary_result["core_api"])


if __name__ == "__main__":
    unittest.main()
