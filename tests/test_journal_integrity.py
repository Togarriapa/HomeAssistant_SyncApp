from pathlib import Path
import tempfile
import unittest

from syncapp.journal_integrity import (
    JournalIntegrityError,
    attach_journal_digest,
    validate_journal_payload,
)


_OLD_DIGEST = "0a00ddc8482e3fe5e4c7072754a8cb5c9a6978cd21b86c494ebdb27449468e85"


class JournalIntegrityTests(unittest.TestCase):
    def _payload(self, *, version: int = 2, state: str = "applied") -> dict:
        payload = {
            "version": version,
            "state": state,
            "commit": "a" * 40,
            "write_paths": ["configuration.yaml"],
            "delete_paths": ["obsolete.yaml"],
            "write_sha256": {"configuration.yaml": "b" * 64},
            "existed": ["configuration.yaml", "obsolete.yaml"],
            "supervisor_backup": "backup-123" if state not in {"preparing", "prepared"} else None,
        }
        if version == 2:
            payload["snapshot_sha256"] = (
                {}
                if state == "preparing"
                else {
                    "configuration.yaml": _OLD_DIGEST,
                    "obsolete.yaml": _OLD_DIGEST,
                }
            )
            return attach_journal_digest(payload)
        return payload

    def _snapshot(self, root: Path) -> Path:
        snapshot = root / "snapshot"
        snapshot.mkdir()
        (snapshot / "configuration.yaml").write_text("old: true\n", encoding="utf-8")
        (snapshot / "obsolete.yaml").write_text("old: true\n", encoding="utf-8")
        return snapshot

    def test_accepts_valid_v2_recovery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            record = validate_journal_payload(self._payload(), snapshot)
            self.assertEqual(record.state, "applied")
            self.assertEqual(record.existed, {"configuration.yaml", "obsolete.yaml"})
            self.assertEqual(dict(record.snapshot_sha256)["configuration.yaml"], _OLD_DIGEST)

    def test_accepts_structurally_valid_legacy_v1_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            record = validate_journal_payload(self._payload(version=1), snapshot)
            self.assertEqual(record.version, 1)
            self.assertEqual(record.snapshot_sha256, ())

    def test_rejects_digest_mismatch_before_recovery_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            payload = self._payload()
            payload["state"] = "verified"
            with self.assertRaisesRegex(JournalIntegrityError, "digest does not match"):
                validate_journal_payload(payload, snapshot)

    def test_rejects_corrupted_existed_set_that_could_turn_restore_into_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            payload = self._payload(version=1)
            payload["existed"] = ["obsolete.yaml"]
            with self.assertRaisesRegex(JournalIntegrityError, "snapshot does not match"):
                validate_journal_payload(payload, snapshot)

    def test_rejects_snapshot_missing_file_claimed_by_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            (snapshot / "obsolete.yaml").unlink()
            with self.assertRaisesRegex(JournalIntegrityError, "snapshot does not match"):
                validate_journal_payload(self._payload(version=1), snapshot)

    def test_rejects_snapshot_bytes_changed_after_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            (snapshot / "configuration.yaml").write_text("corrupt: true\n", encoding="utf-8")
            with self.assertRaisesRegex(JournalIntegrityError, "content digest does not match"):
                validate_journal_payload(self._payload(), snapshot)

    def test_rejects_incomplete_snapshot_hash_map_in_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            payload = self._payload()
            payload["snapshot_sha256"].pop("obsolete.yaml")
            payload = attach_journal_digest(payload)
            with self.assertRaisesRegex(JournalIntegrityError, "snapshot hashes do not match"):
                validate_journal_payload(payload, snapshot)

    def test_rejects_blocked_or_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            for unsafe in ("secrets.yaml", "../outside.yaml", "/tmp/outside.yaml"):
                payload = self._payload(version=1, state="preparing")
                payload["write_paths"] = [unsafe]
                payload["delete_paths"] = []
                payload["write_sha256"] = {unsafe: "b" * 64}
                payload["existed"] = []
                with self.subTest(unsafe=unsafe):
                    with self.assertRaisesRegex(JournalIntegrityError, "blocked or unsafe"):
                        validate_journal_payload(payload, snapshot)

    def test_rejects_write_delete_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            payload = self._payload(version=1)
            payload["delete_paths"].append("configuration.yaml")
            with self.assertRaisesRegex(JournalIntegrityError, "writes and deletes the same path"):
                validate_journal_payload(payload, snapshot)

    def test_rejects_unknown_state_and_invalid_backup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self._snapshot(Path(temporary))
            unknown = self._payload(version=1)
            unknown["state"] = "mystery"
            with self.assertRaisesRegex(JournalIntegrityError, "unsupported state"):
                validate_journal_payload(unknown, snapshot)

            invalid_backup = self._payload(version=1)
            invalid_backup["supervisor_backup"] = "../backup"
            with self.assertRaisesRegex(JournalIntegrityError, "invalid Supervisor backup slug"):
                validate_journal_payload(invalid_backup, snapshot)

    def test_preparing_state_does_not_require_complete_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "snapshot"
            payload = self._payload(version=1, state="preparing")
            record = validate_journal_payload(payload, snapshot)
            self.assertEqual(record.state, "preparing")


if __name__ == "__main__":
    unittest.main()
