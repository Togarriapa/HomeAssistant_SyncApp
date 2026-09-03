from pathlib import Path
import tempfile
import unittest
from unittest import mock

import syncapp.recovery_loader as recovery_loader
import syncapp.transaction_evidence as transaction_evidence
from syncapp.recovery_loader import load_active_transaction
from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError
from syncapp.transaction_evidence import MAX_TRANSACTION_JOURNAL_BYTES


class RecoveryLoaderSafetyTests(unittest.TestCase):
    def _prepared_transaction(self, base: Path) -> tuple[Path, Path, Path]:
        live = base / "live"
        staging = base / "staging"
        transaction = base / "transaction"
        live.mkdir()
        staging.mkdir()
        (live / "configuration.yaml").write_text(
            "homeassistant:\n  name: Old\n", encoding="utf-8"
        )
        (staging / "configuration.yaml").write_text(
            "homeassistant:\n  name: New\n", encoding="utf-8"
        )
        FileTransaction.prepare(
            transaction,
            live,
            staging,
            ApplyPlan(
                commit="a" * 40,
                write_paths=("configuration.yaml",),
                delete_paths=(),
            ),
        )
        return transaction, live, staging

    def test_missing_transaction_root_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            self.assertIsNone(
                load_active_transaction(
                    base / "missing", base / "live", base / "staging"
                )
            )

    def test_empty_orphan_root_is_removed_descriptor_relatively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "transaction"
            root.mkdir()

            self.assertIsNone(
                load_active_transaction(root, base / "live", base / "staging")
            )
            self.assertFalse(root.exists())

    def test_symlinked_transaction_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            root = base / "transaction"
            root.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(TransactionError, "root must not be a symlink"):
                load_active_transaction(root, base / "live", base / "staging")

    def test_symlinked_journal_leaf_is_rejected_without_reading_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "transaction"
            root.mkdir()
            outside = base / "outside-journal.json"
            outside.write_text('{"do_not_read": true}\n', encoding="utf-8")
            (root / FileTransaction.JOURNAL).symlink_to(outside)

            with self.assertRaisesRegex(
                TransactionError, "journal safely.*symlinks are refused"
            ):
                load_active_transaction(root, base / "live", base / "staging")

            self.assertEqual(outside.read_text(encoding="utf-8"), '{"do_not_read": true}\n')

    def test_oversized_journal_is_rejected_before_json_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "transaction"
            root.mkdir()
            (root / FileTransaction.JOURNAL).write_bytes(
                b"x" * (MAX_TRANSACTION_JOURNAL_BYTES + 1)
            )

            with self.assertRaisesRegex(TransactionError, "exceeds.*size limit"):
                load_active_transaction(root, base / "live", base / "staging")

    def test_journal_directory_entry_replacement_during_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, live, staging = self._prepared_transaction(base)
            journal = root / FileTransaction.JOURNAL
            original = journal.read_bytes()
            replaced = False
            real_read = transaction_evidence.os.read

            def read_then_replace(fd: int, size: int) -> bytes:
                nonlocal replaced
                chunk = real_read(fd, size)
                if chunk and not replaced:
                    journal.rename(root / "journal.opened.json")
                    journal.write_bytes(original)
                    replaced = True
                return chunk

            with mock.patch.object(
                transaction_evidence.os,
                "read",
                side_effect=read_then_replace,
            ):
                with self.assertRaisesRegex(
                    TransactionError, "journal.json was replaced or changed"
                ):
                    load_active_transaction(root, live, staging)

            self.assertTrue(replaced)
            self.assertEqual((root / "journal.opened.json").read_bytes(), original)
            self.assertEqual(journal.read_bytes(), original)

    def test_valid_prepared_transaction_loads_through_safe_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, live, staging = self._prepared_transaction(base)

            loaded = load_active_transaction(root, live, staging)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.state, "prepared")  # type: ignore[union-attr]
            self.assertEqual(loaded.plan.commit, "a" * 40)  # type: ignore[union-attr]

    def test_root_replacement_after_snapshot_validation_fails_before_record_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, live, staging = self._prepared_transaction(base)
            moved = base / "transaction-opened"
            real_validate = recovery_loader.validate_journal_payload
            swapped = False

            def validate_then_swap(data, snapshot_dir):
                nonlocal swapped
                record = real_validate(data, snapshot_dir)
                root.rename(moved)
                root.mkdir()
                (root / "replacement-marker").write_text("replacement", encoding="utf-8")
                swapped = True
                return record

            with mock.patch.object(
                recovery_loader,
                "validate_journal_payload",
                side_effect=validate_then_swap,
            ):
                with self.assertRaisesRegex(
                    TransactionError, "root pathname was replaced"
                ):
                    load_active_transaction(root, live, staging)

            self.assertTrue(swapped)
            self.assertTrue((moved / FileTransaction.JOURNAL).exists())
            self.assertEqual(
                (root / "replacement-marker").read_text(encoding="utf-8"),
                "replacement",
            )


if __name__ == "__main__":
    unittest.main()
