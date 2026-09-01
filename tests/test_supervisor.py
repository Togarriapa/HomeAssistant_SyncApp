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

    def test_configuration_check_raises_on_supervisor_error_envelope(self) -> None:
        client = RecordingSupervisorClient(
            [{"result": "error", "message": "configuration invalid"}]
        )
        with self.assertRaisesRegex(SupervisorError, "configuration invalid"):
            client.check_core_configuration()

    def test_core_health_uses_supervisor_core_api_proxy(self) -> None:
        client = RecordingSupervisorClient([{"message": "API running."}])
        result = client.core_api_health(timeout=7)
        self.assertEqual(result, {"message": "API running."})
        self.assertEqual(client.calls[0], ("GET", "/core/api/", None, 7))

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
