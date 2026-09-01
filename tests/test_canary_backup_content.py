import unittest

from canary import run_canary


class BackupEvidenceClient:
    def __init__(self):
        self.name: str | None = None
        self.inventory_content: object = {"homeassistant": True}
        self.details: dict | None = None
        self.restarted = False

    def core_info(self) -> dict:
        return {"version": "2026.9.0"}

    def supervisor_info(self) -> dict:
        return {"version": "2026.09.0"}

    def host_info(self) -> dict:
        return {"operating_system": "Home Assistant OS 17.0"}

    def core_api_health(self) -> dict:
        return {"message": "API running."}

    def check_core_configuration(self) -> dict:
        return {}

    def create_homeassistant_backup(self, name: str) -> str:
        self.name = name
        return "backup-slug"

    def list_backups(self) -> list[dict]:
        return [
            {
                "slug": "backup-slug",
                "name": self.name,
                "type": "partial",
                "content": self.inventory_content,
            }
        ]

    def backup_info(self, slug: str) -> dict:
        if self.details is not None:
            return self.details
        return {
            "slug": slug,
            "name": self.name,
            "type": "partial",
            "homeassistant": "2026.9.0",
            "homeassistant_exclude_database": True,
        }

    def restart_core(self) -> None:
        self.restarted = True

    def wait_for_core_api(self, timeout_seconds: int) -> dict:
        return {"message": "API running."}


class CanaryBackupContentTests(unittest.TestCase):
    def test_inventory_must_confirm_homeassistant_content(self) -> None:
        client = BackupEvidenceClient()
        client.inventory_content = {"homeassistant": False}
        with self.assertRaisesRegex(RuntimeError, "does not prove.*Home Assistant data"):
            run_canary(client, create_backup=True)  # type: ignore[arg-type]

    def test_backup_detail_slug_must_match(self) -> None:
        client = BackupEvidenceClient()
        client.details = {
            "slug": "different",
            "name": None,
            "type": "partial",
            "homeassistant": "2026.9.0",
            "homeassistant_exclude_database": True,
        }
        with self.assertRaisesRegex(RuntimeError, "detail slug did not match"):
            run_canary(client, create_backup=True)  # type: ignore[arg-type]

    def test_backup_detail_requires_homeassistant_version(self) -> None:
        client = BackupEvidenceClient()
        def details() -> dict:
            return {
                "slug": "backup-slug",
                "name": client.name,
                "type": "partial",
                "homeassistant": "",
                "homeassistant_exclude_database": True,
            }
        client.backup_info = lambda slug: details()  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "Home Assistant content is present"):
            run_canary(client, create_backup=True)  # type: ignore[arg-type]

    def test_backup_detail_requires_database_exclusion(self) -> None:
        client = BackupEvidenceClient()
        def details() -> dict:
            return {
                "slug": "backup-slug",
                "name": client.name,
                "type": "partial",
                "homeassistant": "2026.9.0",
                "homeassistant_exclude_database": False,
            }
        client.backup_info = lambda slug: details()  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "database exclusion"):
            run_canary(client, create_backup=True)  # type: ignore[arg-type]

    def test_failed_content_proof_blocks_restart(self) -> None:
        client = BackupEvidenceClient()
        client.inventory_content = None
        with self.assertRaisesRegex(RuntimeError, "does not prove.*Home Assistant data"):
            run_canary(  # type: ignore[arg-type]
                client,
                create_backup=True,
                restart=True,
            )
        self.assertFalse(client.restarted)


if __name__ == "__main__":
    unittest.main()
