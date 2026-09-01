import unittest

from syncapp.backup_retention import (
    prune_syncapp_backups,
    select_expired_syncapp_backups,
)


class FakeSupervisor:
    def __init__(self, backups):
        self.backups = backups
        self.deleted: list[str] = []

    def list_backups(self):
        return self.backups

    def delete_backup(self, slug: str) -> None:
        self.deleted.append(slug)


class BackupRetentionTests(unittest.TestCase):
    def test_only_old_unprotected_syncapp_backups_are_selected(self):
        backups = [
            {"slug": "new", "name": "SyncApp pre-apply abc", "date": "2026-09-01T12:00:00+00:00", "protected": False},
            {"slug": "middle", "name": "SyncApp pre-apply def", "date": "2026-08-31T12:00:00+00:00", "protected": False},
            {"slug": "old", "name": "SyncApp pre-apply ghi", "date": "2026-08-30T12:00:00+00:00", "protected": False},
            {"slug": "protected", "name": "SyncApp pre-apply protected", "date": "2026-08-01T12:00:00+00:00", "protected": True},
            {"slug": "manual", "name": "Manual backup", "date": "2026-07-01T12:00:00+00:00", "protected": False},
            {"slug": "ambiguous", "name": "SyncApp pre-apply missing date", "protected": False},
            {"slug": "naive", "name": "SyncApp pre-apply timezone ambiguous", "date": "2026-01-01T00:00:00", "protected": False},
        ]
        expired = select_expired_syncapp_backups(backups, retention_count=2)
        self.assertEqual(expired, ("old",))

    def test_current_backup_is_never_deleted_even_if_timestamp_is_old(self):
        backups = [
            {"slug": "current", "name": "SyncApp pre-apply current", "date": "2026-01-01T00:00:00Z", "protected": False},
            {"slug": "other", "name": "SyncApp pre-apply other", "date": "2026-02-01T00:00:00Z", "protected": False},
        ]
        expired = select_expired_syncapp_backups(
            backups,
            retention_count=1,
            preserve_slugs={"current"},
        )
        self.assertEqual(expired, ())

    def test_zero_retention_disables_deletion(self):
        backups = [
            {"slug": "old", "name": "SyncApp pre-apply old", "date": "2026-01-01T00:00:00Z", "protected": False}
        ]
        self.assertEqual(select_expired_syncapp_backups(backups, retention_count=0), ())

    def test_prune_calls_delete_only_for_selected_slugs(self):
        supervisor = FakeSupervisor(
            [
                {"slug": "new", "name": "SyncApp pre-apply new", "date": "2026-09-01T00:00:00Z", "protected": False},
                {"slug": "old", "name": "SyncApp pre-apply old", "date": "2026-08-01T00:00:00Z", "protected": False},
                {"slug": "manual", "name": "Manual", "date": "2026-07-01T00:00:00Z", "protected": False},
            ]
        )
        deleted = prune_syncapp_backups(supervisor, retention_count=1)  # type: ignore[arg-type]
        self.assertEqual(deleted, ("old",))
        self.assertEqual(supervisor.deleted, ["old"])


if __name__ == "__main__":
    unittest.main()
