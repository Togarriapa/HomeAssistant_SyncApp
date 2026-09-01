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
