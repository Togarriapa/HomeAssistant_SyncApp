import unittest

from canary import run_canary


class FakeCanaryClient:
    def __init__(self):
        self.calls: list[str] = []

    def core_info(self) -> dict:
        self.calls.append("info")
        return {"version": "2026.9.0"}

    def core_api_health(self) -> dict:
        self.calls.append("health")
        return {"message": "API running."}

    def check_core_configuration(self) -> dict:
        self.calls.append("check")
        return {}

    def create_homeassistant_backup(self, name: str) -> str:
        self.calls.append("backup")
        return "backup-slug"

    def restart_core(self) -> None:
        self.calls.append("restart")

    def wait_for_core_api(self, timeout_seconds: int) -> dict:
        self.calls.append(f"wait:{timeout_seconds}")
        return {"message": "API running."}


class CanaryTests(unittest.TestCase):
    def test_default_canary_is_non_mutating(self):
        client = FakeCanaryClient()
        result = run_canary(client)  # type: ignore[arg-type]
        self.assertEqual(client.calls, ["info", "health", "check"])
        self.assertNotIn("backup_slug", result)
        self.assertNotIn("post_restart_core_api", result)

    def test_backup_and_restart_require_explicit_flags(self):
        client = FakeCanaryClient()
        result = run_canary(  # type: ignore[arg-type]
            client,
            create_backup=True,
            restart=True,
            timeout_seconds=90,
        )
        self.assertEqual(
            client.calls,
            ["info", "health", "check", "backup", "restart", "wait:90"],
        )
        self.assertEqual(result["backup_slug"], "backup-slug")
        self.assertEqual(result["post_restart_core_api"], {"message": "API running."})


if __name__ == "__main__":
    unittest.main()
