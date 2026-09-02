from pathlib import Path
import tempfile
import unittest

from syncapp.process_lock import ProcessLock, ProcessLockError


class ProcessLockTests(unittest.TestCase):
    def test_first_owner_succeeds_and_second_owner_fails_nonblocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with ProcessLock(root) as first:
                first.assert_path_identity()
                with self.assertRaisesRegex(
                    ProcessLockError, "another SyncApp process already owns"
                ):
                    with ProcessLock(root):
                        self.fail("second owner must not acquire the same data root")

    def test_release_allows_a_later_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with ProcessLock(root):
                pass
            with ProcessLock(root) as later:
                later.assert_path_identity()

    def test_context_manager_releases_lock_after_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "injected"):
                with ProcessLock(root):
                    raise RuntimeError("injected")
            with ProcessLock(root):
                pass

    def test_symlinked_data_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / "actual"
            actual.mkdir()
            link = base / "data"
            link.symlink_to(actual, target_is_directory=True)

            with self.assertRaisesRegex(ProcessLockError, "must not be a symlink"):
                with ProcessLock(link):
                    self.fail("symlink root must be refused")

    def test_replacing_locked_root_path_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "data"
            root.mkdir()
            opened = base / "data-opened"

            with ProcessLock(root) as lock:
                root.rename(opened)
                root.mkdir()
                with self.assertRaisesRegex(
                    ProcessLockError, "pathname was replaced"
                ):
                    lock.assert_path_identity()

            # The flock was held on the opened inode, not the replacement pathname.
            with ProcessLock(root):
                pass
            with ProcessLock(opened):
                pass


if __name__ == "__main__":
    unittest.main()
