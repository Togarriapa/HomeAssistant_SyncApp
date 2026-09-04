from pathlib import Path
import tempfile
import unittest

from canary import run_canary


class InvarianceCanaryClient:
    def __init__(self, live: Path, *, mutate_on_restart: bool = False):
        self.live = live
        self.mutate_on_restart = mutate_on_restart
        self.backup_name: str | None = None

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
        self.backup_name = name
        return "backup-slug"

    def list_backups(self) -> list[dict]:
        return [
            {
                "slug": "backup-slug",
                "name": self.backup_name,
                "type": "partial",
                "size": 1.5,
                "content": {"homeassistant": True, "addons": [], "folders": []},
            }
        ]

    def backup_info(self, slug: str) -> dict:
        return {
            "slug": slug,
            "name": self.backup_name,
            "type": "partial",
            "size": "1.5",
            "homeassistant": "2026.9.0",
            "homeassistant_exclude_database": True,
        }

    def restart_core(self) -> None:
        if self.mutate_on_restart:
            (self.live / "configuration.yaml").write_text(
                "homeassistant:\n  name: changed\n",
                encoding="utf-8",
            )

    def wait_for_core_api(self, timeout_seconds: int) -> dict:
        return {"message": "API running."}


class CanaryLiveInvarianceTests(unittest.TestCase):
    def test_filesystem_canary_proves_all_policy_approved_files_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            (live / "automations.yaml").write_text("[]\n", encoding="utf-8")
            (live / "secrets.yaml").write_text("password: private\n", encoding="utf-8")
            client = InvarianceCanaryClient(live)

            result = run_canary(  # type: ignore[arg-type]
                client,
                filesystem=True,
                filesystem_root=live,
            )

            proof = result["live_configuration_invariance"]  # type: ignore[assignment]
            self.assertEqual(proof["policy_approved_files"], 2)  # type: ignore[index]
            self.assertTrue(proof["path_set_unchanged"])  # type: ignore[index]
            self.assertTrue(proof["content_unchanged"])  # type: ignore[index]

    def test_restart_mutation_of_allowed_file_fails_invariance_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            client = InvarianceCanaryClient(live, mutate_on_restart=True)

            with self.assertRaisesRegex(RuntimeError, "changed policy-approved live configuration"):
                run_canary(  # type: ignore[arg-type]
                    client,
                    filesystem=True,
                    filesystem_root=live,
                    create_backup=True,
                    restart=True,
                )

    def test_blocked_runtime_file_changes_do_not_fail_configuration_invariance(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            (live / "home-assistant.log").write_text("before\n", encoding="utf-8")
            client = InvarianceCanaryClient(live)

            original_restart = client.restart_core

            def restart_with_runtime_change() -> None:
                original_restart()
                (live / "home-assistant.log").write_text("after\n", encoding="utf-8")

            client.restart_core = restart_with_runtime_change  # type: ignore[method-assign]
            result = run_canary(  # type: ignore[arg-type]
                client,
                filesystem=True,
                filesystem_root=live,
                create_backup=True,
                restart=True,
            )

            self.assertTrue(
                result["live_configuration_invariance"]["content_unchanged"]  # type: ignore[index]
            )


if __name__ == "__main__":
    unittest.main()
