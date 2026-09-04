from pathlib import Path
import json
import tempfile
import unittest

from syncapp.transaction import (
    ApplyPlan,
    FileTransaction,
    TransactionError,
    execute_verified_transaction,
)


class MutatingBackupSupervisor:
    def __init__(self, staged_file: Path):
        self.staged_file = staged_file
        self.checks = 0
        self.restarts = 0

    def create_homeassistant_backup(self, name: str) -> str:
        self.staged_file.write_text("attacker: changed\n", encoding="utf-8")
        return "backup-123"

    def verify_homeassistant_backup(
        self,
        slug: str,
        expected_name: str,
    ) -> dict[str, object]:
        return {"slug": slug, "detail_verified": True}

    def check_core_configuration(self) -> dict:
        self.checks += 1
        return {}

    def restart_core(self) -> None:
        self.restarts += 1

    def wait_for_core_api(self, timeout_seconds: int, poll_seconds: float = 2.0) -> dict:
        raise AssertionError("health check must not run when staging integrity fails")


class StagingIntegrityTests(unittest.TestCase):
    def test_staged_bytes_are_pinned_in_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            staged = staging / "configuration.yaml"
            staged.write_text("safe: true\n", encoding="utf-8")

            tx = FileTransaction.prepare(
                tx_root,
                live,
                staging,
                ApplyPlan("a" * 40, ("configuration.yaml",), ()),
            )
            journal = json.loads((tx_root / "journal.json").read_text(encoding="utf-8"))
            self.assertIn("configuration.yaml", journal["write_sha256"])
            self.assertEqual(len(journal["write_sha256"]["configuration.yaml"]), 64)

    def test_staged_change_during_backup_aborts_before_live_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            staged = staging / "configuration.yaml"
            staged.write_text("new: true\n", encoding="utf-8")

            tx = FileTransaction.prepare(
                tx_root,
                live,
                staging,
                ApplyPlan("b" * 40, ("configuration.yaml",), ()),
            )
            supervisor = MutatingBackupSupervisor(staged)

            with self.assertRaisesRegex(TransactionError, "staged configuration changed"):
                execute_verified_transaction(tx, supervisor, health_timeout_seconds=1)

            self.assertEqual((live / "configuration.yaml").read_text(), "old: true\n")
            self.assertFalse(tx_root.exists())
            self.assertEqual(supervisor.checks, 0)
            self.assertEqual(supervisor.restarts, 0)

    def test_apply_rechecks_staged_hash_before_each_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            staged = staging / "configuration.yaml"
            staged.write_text("new: true\n", encoding="utf-8")

            tx = FileTransaction.prepare(
                tx_root,
                live,
                staging,
                ApplyPlan("c" * 40, ("configuration.yaml",), ()),
            )
            tx.record_supervisor_backup("backup-123")
            staged.write_text("changed: true\n", encoding="utf-8")

            with self.assertRaisesRegex(TransactionError, "staged configuration changed"):
                tx.apply()
            self.assertFalse((live / "configuration.yaml").exists())


if __name__ == "__main__":
    unittest.main()
