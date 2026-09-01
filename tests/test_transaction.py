from pathlib import Path
import tempfile
import unittest

from syncapp.transaction import (
    ApplyPlan,
    FileTransaction,
    TransactionError,
    execute_verified_transaction,
    recover_active_transaction,
)


class FakeSupervisor:
    def __init__(self, *, fail_check: bool = False):
        self.fail_check = fail_check
        self.backups = 0
        self.checks = 0
        self.restarts = 0
        self.health_checks = 0

    def create_homeassistant_backup(self, name: str) -> str:
        self.backups += 1
        return "backup-123"

    def check_core_configuration(self) -> dict:
        self.checks += 1
        if self.fail_check:
            self.fail_check = False
            raise RuntimeError("invalid configuration")
        return {}

    def restart_core(self) -> None:
        self.restarts += 1

    def wait_for_core_api(self, timeout_seconds: int, poll_seconds: float = 2.0) -> dict:
        self.health_checks += 1
        return {"message": "API running."}


class TransactionTests(unittest.TestCase):
    def _dirs(self, root: Path) -> tuple[Path, Path, Path]:
        live = root / "live"
        staging = root / "staging"
        transaction = root / "transaction"
        live.mkdir()
        staging.mkdir()
        return live, staging, transaction

    def test_verified_transaction_writes_deletes_and_keeps_snapshot_until_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, staging, tx_root = self._dirs(root)
            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (live / "obsolete.yaml").write_text("remove: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")

            plan = ApplyPlan(
                commit="a" * 40,
                write_paths=("configuration.yaml",),
                delete_paths=("obsolete.yaml",),
            )
            tx = FileTransaction.prepare(tx_root, live, staging, plan)
            supervisor = FakeSupervisor()
            result = execute_verified_transaction(tx, supervisor, health_timeout_seconds=1)

            self.assertEqual((live / "configuration.yaml").read_text(), "new: true\n")
            self.assertFalse((live / "obsolete.yaml").exists())
            self.assertEqual(result.backup_slug, "backup-123")
            self.assertEqual(supervisor.backups, 1)
            self.assertEqual(supervisor.checks, 1)
            self.assertEqual(supervisor.restarts, 1)
            self.assertEqual(supervisor.health_checks, 1)
            self.assertTrue(tx_root.exists())

            tx.complete()
            self.assertFalse(tx_root.exists())

    def test_failed_configuration_check_restores_without_restarting_running_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, staging, tx_root = self._dirs(root)
            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("broken: true\n", encoding="utf-8")

            plan = ApplyPlan("b" * 40, ("configuration.yaml",), ())
            tx = FileTransaction.prepare(tx_root, live, staging, plan)
            supervisor = FakeSupervisor(fail_check=True)

            with self.assertRaisesRegex(TransactionError, "restored"):
                execute_verified_transaction(tx, supervisor, health_timeout_seconds=1)

            self.assertEqual((live / "configuration.yaml").read_text(), "old: true\n")
            self.assertFalse(tx_root.exists())
            self.assertEqual(supervisor.backups, 1)
            self.assertEqual(supervisor.checks, 1)
            self.assertEqual(supervisor.restarts, 0)
            self.assertEqual(supervisor.health_checks, 0)

    def test_interrupted_applied_transaction_is_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, staging, tx_root = self._dirs(root)
            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")

            plan = ApplyPlan("c" * 40, ("configuration.yaml",), ())
            tx = FileTransaction.prepare(tx_root, live, staging, plan)
            tx.apply()
            self.assertEqual((live / "configuration.yaml").read_text(), "new: true\n")

            active = FileTransaction.load_active(tx_root, live, staging)
            self.assertIsNotNone(active)
            supervisor = FakeSupervisor()
            recover_active_transaction(active, supervisor, health_timeout_seconds=1)  # type: ignore[arg-type]

            self.assertEqual((live / "configuration.yaml").read_text(), "old: true\n")
            self.assertFalse(tx_root.exists())
            self.assertEqual(supervisor.checks, 1)
            self.assertEqual(supervisor.restarts, 1)
            self.assertEqual(supervisor.health_checks, 1)

    def test_symlinked_live_parent_is_rejected_before_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live, staging, tx_root = self._dirs(root)
            outside = root / "outside"
            outside.mkdir()
            (live / "packages").symlink_to(outside, target_is_directory=True)
            (staging / "packages").mkdir()
            (staging / "packages" / "test.yaml").write_text("ok: true\n", encoding="utf-8")
            plan = ApplyPlan("d" * 40, ("packages/test.yaml",), ())

            with self.assertRaisesRegex(TransactionError, "symlink"):
                FileTransaction.prepare(tx_root, live, staging, plan)
            self.assertFalse(tx_root.exists())


if __name__ == "__main__":
    unittest.main()
