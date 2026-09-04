from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from syncapp.transaction import ApplyPlan, FileTransaction, TransactionError


class TransactionDiscardConfinementTests(unittest.TestCase):
    @staticmethod
    def _prepare(root: Path, *, nested: bool = False) -> FileTransaction:
        live = root / "live"
        staging = root / "staging"
        transaction_root = root / "transaction"
        live.mkdir()
        staging.mkdir()
        relative = "packages/configuration.yaml" if nested else "configuration.yaml"
        live_file = live / relative
        staging_file = staging / relative
        live_file.parent.mkdir(parents=True, exist_ok=True)
        staging_file.parent.mkdir(parents=True, exist_ok=True)
        live_file.write_text("old: true\n", encoding="utf-8")
        staging_file.write_text("new: true\n", encoding="utf-8")
        return FileTransaction.prepare(
            transaction_root,
            live,
            staging,
            ApplyPlan("a" * 40, (relative,), ()),
        )

    def test_normal_nested_transaction_tree_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root, nested=True)

            transaction.discard()

            self.assertFalse(transaction.root.exists())
            self.assertTrue(transaction.source_dir.exists())
            self.assertTrue(transaction.staging_dir.exists())

    def test_transaction_symlink_is_unlinked_without_following_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root)
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("preserve me\n", encoding="utf-8")
            (transaction.root / "outside-link").symlink_to(outside, target_is_directory=True)

            transaction.discard()

            self.assertFalse(transaction.root.exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me\n")

    def test_replaced_transaction_root_is_refused_before_recursive_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root)
            original = root / "transaction.original"
            transaction.root.rename(original)
            transaction.root.mkdir()
            sentinel = transaction.root / "sentinel.txt"
            sentinel.write_text("replacement tree\n", encoding="utf-8")

            with self.assertRaisesRegex(
                TransactionError,
                "no longer identifies the expected cleanup tree",
            ):
                transaction.discard()

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "replacement tree\n")
            self.assertTrue((original / FileTransaction.JOURNAL).exists())

    def test_root_swap_during_cleanup_does_not_traverse_replacement_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transaction = self._prepare(root, nested=True)
            moved = root / "transaction.original"
            replacement_sentinel = transaction.root / "replacement-sentinel.txt"
            real_unlink = os.unlink
            swapped = False

            def swap_root_then_unlink(path, *, dir_fd=None):
                nonlocal swapped
                if not swapped and dir_fd is not None:
                    transaction.root.rename(moved)
                    transaction.root.mkdir()
                    replacement_sentinel.write_text("do not delete\n", encoding="utf-8")
                    replacement_nested = transaction.root / "nested"
                    replacement_nested.mkdir()
                    (replacement_nested / "victim.txt").write_text(
                        "also preserve\n",
                        encoding="utf-8",
                    )
                    swapped = True
                return real_unlink(path, dir_fd=dir_fd)

            with mock.patch(
                "syncapp.transaction_cleanup.os.unlink",
                side_effect=swap_root_then_unlink,
            ):
                with self.assertRaisesRegex(
                    TransactionError,
                    "root was replaced during cleanup",
                ):
                    transaction.discard()

            self.assertTrue(swapped)
            self.assertEqual(
                replacement_sentinel.read_text(encoding="utf-8"),
                "do not delete\n",
            )
            self.assertEqual(
                (transaction.root / "nested" / "victim.txt").read_text(encoding="utf-8"),
                "also preserve\n",
            )
            self.assertTrue(transaction.root.exists())
            self.assertTrue(moved.exists())


if __name__ == "__main__":
    unittest.main()
