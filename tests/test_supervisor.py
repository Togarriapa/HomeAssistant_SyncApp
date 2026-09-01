import unittest

from syncapp.supervisor import SupervisorClient, SupervisorError


class RecordingSupervisorClient(SupervisorClient):
    def __init__(self, responses: list[dict]):
        super().__init__(token="test-token", base_url="http://supervisor")
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict | None, int]] = []

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        timeout: int = 120,
    ) -> dict:
        self.calls.append((method, path, payload, timeout))
        if not self.responses:
            raise AssertionError("unexpected Supervisor request")
        return self.responses.pop(0)


class SupervisorClientTests(unittest.TestCase):
    def test_backup_uses_synchronous_partial_homeassistant_backup(self) -> None:
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": {"slug": "backup-slug"}}]
        )

        slug = client.create_homeassistant_backup("before apply")

        self.assertEqual(slug, "backup-slug")
        method, path, payload, timeout = client.calls[0]
        self.assertEqual((method, path), ("POST", "/backups/new/partial"))
        self.assertEqual(timeout, 900)
        self.assertEqual(
            payload,
            {
                "name": "before apply",
                "homeassistant": True,
                "homeassistant_exclude_database": True,
                "background": False,
            },
        )

    def test_backup_inventory_uses_backups_endpoint(self) -> None:
        backups = [{"slug": "one", "name": "SyncApp pre-apply one"}]
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": {"backups": backups}}]
        )
        self.assertEqual(client.list_backups(), backups)
        self.assertEqual(client.calls[0][:2], ("GET", "/backups"))

    def test_backup_info_uses_specific_slug_endpoint(self) -> None:
        details = {
            "slug": "safe_slug-123",
            "type": "partial",
            "homeassistant": "2026.9.0",
            "homeassistant_exclude_database": True,
        }
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": details}]
        )
        self.assertEqual(client.backup_info("safe_slug-123"), details)
        self.assertEqual(
            client.calls[0][:2],
            ("GET", "/backups/safe_slug-123/info"),
        )

    def test_backup_info_rejects_untrusted_slug_characters(self) -> None:
        client = RecordingSupervisorClient([])
        with self.assertRaisesRegex(SupervisorError, "invalid backup slug"):
            client.backup_info("../other")
        self.assertEqual(client.calls, [])

    def _verified_backup_client(
        self,
        *,
        inventory_size: object = 12.5,
        detail_size: object = "12.50",
    ) -> tuple[RecordingSupervisorClient, str]:
        name = "SyncApp pre-apply abcdef123456"
        return (
            RecordingSupervisorClient(
                [
                    {
                        "result": "ok",
                        "data": {
                            "backups": [
                                {
                                    "slug": "backup-123",
                                    "name": name,
                                    "type": "partial",
                                    "date": "2026-09-01T22:00:00+00:00",
                                    "protected": False,
                                    "size": inventory_size,
                                    "content": {"homeassistant": True},
                                }
                            ]
                        },
                    },
                    {
                        "result": "ok",
                        "data": {
                            "slug": "backup-123",
                            "name": name,
                            "type": "partial",
                            "size": detail_size,
                            "homeassistant": "2026.9.0",
                            "homeassistant_exclude_database": True,
                        },
                    },
                ]
            ),
            name,
        )

    def test_verify_homeassistant_backup_cross_checks_inventory_and_details(self) -> None:
        client, name = self._verified_backup_client()

        evidence = client.verify_homeassistant_backup("backup-123", name)

        self.assertEqual(client.calls[0][:2], ("GET", "/backups"))
        self.assertEqual(client.calls[1][:2], ("GET", "/backups/backup-123/info"))
        self.assertTrue(evidence["inventory_verified"])
        self.assertTrue(evidence["detail_verified"])
        self.assertTrue(evidence["homeassistant_content_verified"])
        self.assertTrue(evidence["homeassistant_database_excluded"])
        self.assertTrue(evidence["backup_size_verified"])
        self.assertEqual(evidence["backup_size_mb"], "12.50")
        self.assertEqual(evidence["homeassistant_version"], "2026.9.0")

    def test_verify_homeassistant_backup_rejects_zero_inventory_size(self) -> None:
        client, name = self._verified_backup_client(inventory_size=0)
        with self.assertRaisesRegex(SupervisorError, "inventory.*non-zero size"):
            client.verify_homeassistant_backup("backup-123", name)
        self.assertEqual(len(client.calls), 1)

    def test_verify_homeassistant_backup_rejects_zero_detail_size(self) -> None:
        client, name = self._verified_backup_client(detail_size="0")
        with self.assertRaisesRegex(SupervisorError, "details.*non-zero size"):
            client.verify_homeassistant_backup("backup-123", name)

    def test_verify_homeassistant_backup_rejects_invalid_or_boolean_size(self) -> None:
        for invalid in (True, "not-a-number", "NaN", "Infinity"):
            with self.subTest(invalid=invalid):
                client, name = self._verified_backup_client(inventory_size=invalid)
                with self.assertRaisesRegex(SupervisorError, "valid backup size|non-zero size"):
                    client.verify_homeassistant_backup("backup-123", name)

    def test_verify_homeassistant_backup_rejects_inventory_detail_size_mismatch(self) -> None:
        client, name = self._verified_backup_client(inventory_size=12.5, detail_size="12.51")
        with self.assertRaisesRegex(SupervisorError, "inventory/detail size did not match"):
            client.verify_homeassistant_backup("backup-123", name)

    def test_verify_homeassistant_backup_rejects_missing_homeassistant_content(self) -> None:
        name = "SyncApp pre-apply abcdef123456"
        client = RecordingSupervisorClient(
            [
                {
                    "result": "ok",
                    "data": {
                        "backups": [
                            {
                                "slug": "backup-123",
                                "name": name,
                                "type": "partial",
                                "size": 12.5,
                                "content": {"homeassistant": False},
                            }
                        ]
                    },
                }
            ]
        )

        with self.assertRaisesRegex(SupervisorError, "contains Home Assistant data"):
            client.verify_homeassistant_backup("backup-123", name)

        self.assertEqual(len(client.calls), 1)

    def test_verify_homeassistant_backup_rejects_database_inclusion(self) -> None:
        name = "SyncApp pre-apply abcdef123456"
        client = RecordingSupervisorClient(
            [
                {
                    "result": "ok",
                    "data": {
                        "backups": [
                            {
                                "slug": "backup-123",
                                "name": name,
                                "type": "partial",
                                "size": 12.5,
                                "content": {"homeassistant": True},
                            }
                        ]
                    },
                },
                {
                    "result": "ok",
                    "data": {
                        "slug": "backup-123",
                        "name": name,
                        "type": "partial",
                        "size": "12.5",
                        "homeassistant": "2026.9.0",
                        "homeassistant_exclude_database": False,
                    },
                },
            ]
        )

        with self.assertRaisesRegex(SupervisorError, "database exclusion"):
            client.verify_homeassistant_backup("backup-123", name)

    def test_backup_delete_uses_specific_slug_endpoint(self) -> None:
        client = RecordingSupervisorClient([{"result": "ok", "data": {}}])
        client.delete_backup("safe_slug-123")
        self.assertEqual(client.calls[0][:2], ("DELETE", "/backups/safe_slug-123"))

    def test_backup_delete_rejects_untrusted_slug_characters(self) -> None:
        client = RecordingSupervisorClient([])
        with self.assertRaisesRegex(SupervisorError, "invalid backup slug"):
            client.delete_backup("../other")
        self.assertEqual(client.calls, [])

    def test_backup_inventory_rejects_unexpected_shape(self) -> None:
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": {"backups": {"not": "a list"}}}]
        )
        with self.assertRaisesRegex(SupervisorError, "unexpected data"):
            client.list_backups()

    def test_configuration_check_raises_on_supervisor_error_envelope(self) -> None:
        client = RecordingSupervisorClient(
            [{"result": "error", "message": "configuration invalid"}]
        )
        with self.assertRaisesRegex(SupervisorError, "configuration invalid"):
            client.check_core_configuration()

    def test_core_info_uses_core_info_endpoint(self) -> None:
        payload = {"version": "2026.9.0", "arch": "amd64"}
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": payload}]
        )
        self.assertEqual(client.core_info(), payload)
        self.assertEqual(client.calls[0][:2], ("GET", "/core/info"))

    def test_supervisor_info_uses_supervisor_info_endpoint(self) -> None:
        payload = {"version": "2026.09.0", "arch": "amd64"}
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": payload}]
        )
        self.assertEqual(client.supervisor_info(), payload)
        self.assertEqual(client.calls[0][:2], ("GET", "/supervisor/info"))

    def test_host_info_uses_host_info_endpoint(self) -> None:
        payload = {
            "operating_system": "Home Assistant OS 17.0",
            "kernel": "6.12.0-haos",
            "agent_version": "1.7.2",
        }
        client = RecordingSupervisorClient(
            [{"result": "ok", "data": payload}]
        )
        self.assertEqual(client.host_info(), payload)
        self.assertEqual(client.calls[0][:2], ("GET", "/host/info"))

    def test_core_health_uses_supervisor_core_api_proxy(self) -> None:
        client = RecordingSupervisorClient([{"message": "API running."}])
        result = client.core_api_health(timeout=7)
        self.assertEqual(result, {"message": "API running."})
        self.assertEqual(client.calls[0], ("GET", "/core/api/", None, 7))

    def test_core_health_rejects_unexpected_success_payload(self) -> None:
        client = RecordingSupervisorClient([{"message": "starting"}])
        with self.assertRaisesRegex(SupervisorError, "unexpected health response"):
            client.core_api_health()

    def test_restart_uses_core_restart_endpoint(self) -> None:
        client = RecordingSupervisorClient([{"result": "ok", "data": {}}])
        client.restart_core()
        self.assertEqual(client.calls[0][:2], ("POST", "/core/restart"))

    def test_backup_without_slug_is_rejected(self) -> None:
        client = RecordingSupervisorClient([{"result": "ok", "data": {}}])
        with self.assertRaisesRegex(SupervisorError, "did not include a slug"):
            client.create_homeassistant_backup("before apply")


if __name__ == "__main__":
    unittest.main()
