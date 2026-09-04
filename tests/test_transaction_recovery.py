from pathlib import Path
import tempfile
import unittest

from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError, recover_active_transaction


class NoCallSupervisor:
    def __init__(self) -> None:
        self.calls = 0

    def create_homeassistant_backup(self, name: str) -> str:
        self.calls += 1
        raise AssertionError("Supervisor should not be called")

    def check_core_configuration(self) -> dict:
        self.calls += 1
        raise AssertionError("Supervisor should not be called")

    def restart_core(self) -> None:
        self.calls += 1
        raise AssertionError("Supervisor should not be called")

    def wait_for_core_api(self, timeout_seconds: int, poll_seconds: float = 2.0) -> dict:
        self.calls += 1
        raise AssertionError("Supervisor should not be called")


class PreparationRecoveryTests(unittest.TestCase):
    def test_prepared_transaction_discards_without_core_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            (live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")

            tx = FileTransaction.prepare(
                tx_root,
                live,
                staging,
                ApplyPlan("a" * 40, ("configuration.yaml",), ()),
            )
            self.assertEqual(tx.state, "prepared")
            supervisor = NoCallSupervisor()
            recover_active_transaction(tx, supervisor, health_timeout_seconds=1)

            self.assertEqual((live / "configuration.yaml").read_text(), "old: true\n")
            self.assertFalse(tx_root.exists())
            self.assertEqual(supervisor.calls, 0)

    def test_empty_orphan_transaction_directory_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            tx_root.mkdir()

            self.assertIsNone(FileTransaction.load_active(tx_root, live, staging))
            self.assertFalse(tx_root.exists())

    def test_nonempty_orphan_transaction_directory_blocks_new_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            live.mkdir()
            staging.mkdir()
            tx_root.mkdir()
            (tx_root / "unknown-state").write_text("ambiguous", encoding="utf-8")

            with self.assertRaisesRegex(TransactionError, "without a journal"):
                FileTransaction.load_active(tx_root, live, staging)
            self.assertTrue(tx_root.exists())

    def test_symlinked_live_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_live = root / "real-live"
            live = root / "live"
            staging = root / "staging"
            tx_root = root / "transaction"
            real_live.mkdir()
            live.symlink_to(real_live, target_is_directory=True)
            staging.mkdir()
            (real_live / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
            (staging / "configuration.yaml").write_text("new: true\n", encoding="utf-8")

            with self.assertRaisesRegex(TransactionError, "root must not be a symlink"):
                FileTransaction.prepare(
                    tx_root,
                    live,
                    staging,
                    ApplyPlan("b" * 40, ("configuration.yaml",), ()),
                )
            self.assertFalse(tx_root.exists())


if __name__ == "__main__":
    unittest.main()
