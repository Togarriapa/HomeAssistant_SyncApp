from pathlib import Path
import tempfile
import unittest

from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError, execute_verified_transaction


class MutatingBackupSupervisor:
    def __init__(self, live_file: Path):
        self.live_file = live_file
        self.checks = 0
        self.restarts = 0
        self.health_checks = 0

    def create_homeassistant_backup(self, name: str) -> str:
        self.live_file.write_text("user_edit: true\n", encoding="utf-8")
        return "backup-after-user-edit"

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
        self.health_checks += 1
        return {"message": "API running."}


class TransactionConcurrencyTests(unittest.TestCase):
    def test_local_edit_during_supervisor_backup_aborts_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            transaction_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            live_file = live / "configuration.yaml"
            live_file.write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("remote: true\n", encoding="utf-8")

            transaction = FileTransaction.prepare(
                transaction_root,
                live,
                staging,
                ApplyPlan("a" * 40, ("configuration.yaml",), ()),
            )
            supervisor = MutatingBackupSupervisor(live_file)

            with self.assertRaisesRegex(TransactionError, "aborted without mutation"):
                execute_verified_transaction(
                    transaction,
                    supervisor,
                    health_timeout_seconds=1,
                )

            self.assertEqual(live_file.read_text(encoding="utf-8"), "user_edit: true\n")
            self.assertFalse(transaction_root.exists())
            self.assertEqual(supervisor.checks, 0)
            self.assertEqual(supervisor.restarts, 0)
            self.assertEqual(supervisor.health_checks, 0)


if __name__ == "__main__":
    unittest.main()
