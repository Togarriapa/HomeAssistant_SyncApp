import tarfile
import unittest

from syncapp.backup_archive import (
    BackupArchiveError,
    MAX_OUTER_LOGICAL_BYTES,
    MAX_OUTER_MEMBER_BYTES,
    _bounded_regular_size,
)


class BackupArchiveOuterBoundTests(unittest.TestCase):
    def test_outer_regular_member_limit_fails_closed(self):
        member = tarfile.TarInfo("unrelated.bin")
        member.size = MAX_OUTER_MEMBER_BYTES + 1

        with self.assertRaisesRegex(BackupArchiveError, "logical member limit"):
            _bounded_regular_size(
                0,
                member,
                label="downloaded Supervisor backup archive",
                max_member_bytes=MAX_OUTER_MEMBER_BYTES,
                max_total_bytes=MAX_OUTER_LOGICAL_BYTES,
            )

    def test_outer_cumulative_logical_limit_fails_closed(self):
        member = tarfile.TarInfo("unrelated.bin")
        member.size = 2

        with self.assertRaisesRegex(BackupArchiveError, "logical payload limit"):
            _bounded_regular_size(
                MAX_OUTER_LOGICAL_BYTES - 1,
                member,
                label="downloaded Supervisor backup archive",
                max_member_bytes=MAX_OUTER_MEMBER_BYTES,
                max_total_bytes=MAX_OUTER_LOGICAL_BYTES,
            )


if __name__ == "__main__":
    unittest.main()
