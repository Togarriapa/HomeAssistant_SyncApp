import hashlib
from pathlib import Path
import tempfile
import unittest

from syncapp.transaction import TransactionError
from syncapp.validated_plan import build_validated_apply_plan


class ValidatedApplyPlanTests(unittest.TestCase):
    def test_desired_paths_come_from_validated_manifest_not_staging_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            config = b"homeassistant:\n"
            automation = b"automation: []\n"
            (live / "configuration.yaml").write_bytes(config)
            (live / "automations.yaml").write_bytes(automation)
            hashes = {
                "configuration.yaml": hashlib.sha256(config).hexdigest(),
                "automations.yaml": hashlib.sha256(automation).hexdigest(),
            }

            plan = build_validated_apply_plan(
                hashes,
                {"configuration.yaml", "automations.yaml"},
                "a" * 40,
                live_dir=live,
            )

            self.assertEqual(plan.write_paths, ())
            self.assertEqual(plan.delete_paths, ())

    def test_live_difference_creates_write_pinned_to_validated_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_bytes(b"homeassistant:\n  name: Old\n")
            desired = b"homeassistant:\n  name: New\n"
            digest = hashlib.sha256(desired).hexdigest()

            plan = build_validated_apply_plan(
                {"configuration.yaml": digest},
                {"configuration.yaml"},
                "b" * 40,
                live_dir=live,
            )

            self.assertEqual(plan.write_paths, ("configuration.yaml",))
            self.assertEqual(plan.delete_paths, ())
            self.assertEqual(plan.write_hashes, {"configuration.yaml": digest})

    def test_only_absence_from_validated_manifest_can_create_delete(self) -> None:
        plan = build_validated_apply_plan(
            {},
            {"configuration.yaml", "automations.yaml"},
            "c" * 40,
        )
        self.assertEqual(
            plan.delete_paths, ("automations.yaml", "configuration.yaml")
        )

    def test_invalid_validated_path_or_digest_fails_closed(self) -> None:
        with self.assertRaisesRegex(TransactionError, "blocked path"):
            build_validated_apply_plan(
                {"../outside.yaml": "0" * 64}, set(), "d" * 40
            )
        with self.assertRaisesRegex(TransactionError, "invalid validated staging digest"):
            build_validated_apply_plan(
                {"configuration.yaml": "not-a-digest"}, set(), "d" * 40
            )


if __name__ == "__main__":
    unittest.main()
