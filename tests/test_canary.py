from pathlib import Path
import tempfile
import unittest
from unittest import mock

from canary import run_canary, run_filesystem_canary


class FakeCanaryClient:
    def __init__(self):
        self.calls: list[str] = []

    def core_info(self) -> dict:
        self.calls.append("core-info")
        return {
            "version": "2026.9.0",
            "arch": "amd64",
            "machine": "generic-x86-64",
            "image": "ghcr.io/home-assistant/qemux86-64-homeassistant",
            "ip_address": "172.30.32.1",
        }

    def supervisor_info(self) -> dict:
        self.calls.append("supervisor-info")
        return {
            "version": "2026.09.0",
            "arch": "amd64",
            "version_latest": "2026.09.1",
        }

    def host_info(self) -> dict:
        self.calls.append("host-info")
        return {
            "operating_system": "Home Assistant OS 17.0",
            "kernel": "6.12.0-haos",
            "agent_version": "1.7.2",
            "deployment": "production",
            "virtualization": "kvm",
            "hostname": "private-hostname",
            "disk_free": 123.4,
        }

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
    def test_default_canary_is_non_mutating_and_records_redacted_environment(self):
        client = FakeCanaryClient()
        result = run_canary(client)  # type: ignore[arg-type]

        self.assertEqual(
            client.calls,
            ["core-info", "supervisor-info", "host-info", "health", "check"],
        )
        self.assertEqual(
            result["environment"],
            {
                "core": {
                    "version": "2026.9.0",
                    "arch": "amd64",
                    "machine": "generic-x86-64",
                    "image": "ghcr.io/home-assistant/qemux86-64-homeassistant",
                },
                "supervisor": {"version": "2026.09.0", "arch": "amd64"},
                "host": {
                    "operating_system": "Home Assistant OS 17.0",
                    "kernel": "6.12.0-haos",
                    "agent_version": "1.7.2",
                    "deployment": "production",
                    "virtualization": "kvm",
                },
            },
        )
        rendered = repr(result["environment"])
        self.assertNotIn("private-hostname", rendered)
        self.assertNotIn("172.30.32.1", rendered)
        self.assertNotIn("disk_free", rendered)
        self.assertNotIn("version_latest", rendered)
        self.assertNotIn("backup_slug", result)
        self.assertNotIn("post_restart_core_api", result)
        self.assertNotIn("filesystem", result)

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
            [
                "core-info",
                "supervisor-info",
                "host-info",
                "health",
                "check",
                "backup",
                "restart",
                "wait:90",
            ],
        )
        self.assertEqual(result["backup_slug"], "backup-slug")
        self.assertEqual(result["post_restart_core_api"], {"message": "API running."})

    def test_readonly_filesystem_probe_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            before = sorted(path.name for path in live.iterdir())

            result = run_filesystem_canary(live)

            self.assertEqual(sorted(path.name for path in live.iterdir()), before)
            self.assertTrue(result["root_opened_no_follow"])
            self.assertTrue(result["descriptor_relative_open"])
            self.assertTrue(result["descriptor_relative_stat"])
            self.assertTrue(result["probe_path_exists_regular"])
            self.assertTrue(result["probe_path_read_verified"])
            self.assertFalse(result["write_probe"])
            self.assertNotIn("stale_probe_files_before", result)

    def test_readonly_filesystem_probe_requires_existing_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()

            with self.assertRaisesRegex(RuntimeError, "not an existing policy-approved regular file"):
                run_filesystem_canary(live)

    def test_explicit_filesystem_write_probe_replaces_unlinks_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            before = sorted(path.name for path in live.iterdir())

            result = run_filesystem_canary(live, write_probe=True)

            self.assertEqual(sorted(path.name for path in live.iterdir()), before)
            self.assertTrue(result["write_probe"])
            self.assertTrue(result["exclusive_source_reservation"])
            self.assertTrue(result["exclusive_destination_reservation"])
            self.assertTrue(result["descriptor_relative_replace"])
            self.assertTrue(result["descriptor_relative_unlink"])
            self.assertTrue(result["file_fsync"])
            self.assertTrue(result["directory_fsync"])
            self.assertTrue(result["write_probe_cleanup"])
            self.assertEqual(result["stale_probe_files_before"], 0)
            self.assertEqual(result["stale_probe_files_after"], 0)

    def test_write_probe_refuses_preexisting_canary_evidence_without_touching_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            stale = live / ".syncapp-canary-previous.tmp"
            stale.write_text("preserve evidence\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "stale .syncapp-canary-.* evidence exists"):
                run_filesystem_canary(live, write_probe=True)

            self.assertEqual(stale.read_text(encoding="utf-8"), "preserve evidence\n")
            self.assertEqual(
                sorted(path.name for path in live.iterdir()),
                [".syncapp-canary-previous.tmp", "configuration.yaml"],
            )

    def test_exclusive_reservation_still_blocks_collision_after_clean_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            collision = live / ".syncapp-canary-fixed.tmp"
            collision.write_text("preserve race winner\n", encoding="utf-8")

            # Model the race where the preflight saw a clean directory but a
            # matching path appeared before the O_EXCL reservation.
            with mock.patch("canary._canary_temp_names", return_value=()), mock.patch(
                "canary.secrets.token_hex", return_value="fixed"
            ):
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    run_filesystem_canary(live, write_probe=True)

            self.assertEqual(
                collision.read_text(encoding="utf-8"),
                "preserve race winner\n",
            )
            self.assertFalse((live / ".syncapp-canary-fixed-replaced.tmp").exists())

    def test_nonmatching_tmp_file_does_not_block_write_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            unrelated = live / ".other-canary.tmp"
            unrelated.write_text("unrelated\n", encoding="utf-8")

            result = run_filesystem_canary(live, write_probe=True)

            self.assertTrue(result["write_probe"])
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "unrelated\n")

    def test_write_probe_replace_failure_cleans_both_owned_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            real_replace = __import__("os").replace

            def fail_canary_replace(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
                if str(src).startswith(".syncapp-canary-"):
                    raise OSError("injected replace failure")
                return real_replace(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

            with mock.patch("canary.secrets.token_hex", return_value="fixed"), mock.patch(
                "canary.os.replace", side_effect=fail_canary_replace
            ):
                with self.assertRaisesRegex(OSError, "injected replace failure"):
                    run_filesystem_canary(live, write_probe=True)

            leftovers = [path.name for path in live.iterdir() if path.name.startswith(".syncapp-canary-")]
            self.assertEqual(leftovers, [])

    def test_filesystem_probe_rejects_symlink_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            link = root / "live"
            link.symlink_to(actual, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, "root must not be a symlink"):
                run_filesystem_canary(link)

    def test_filesystem_probe_keeps_blocked_paths_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "secrets.yaml").write_text("password: no\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "blocked live path"):
                run_filesystem_canary(live, probe_path="secrets.yaml")

    def test_run_canary_filesystem_write_probe_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            live = Path(temporary) / "live"
            live.mkdir()
            (live / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")
            client = FakeCanaryClient()

            result = run_canary(  # type: ignore[arg-type]
                client,
                filesystem=True,
                filesystem_root=live,
            )
            self.assertFalse(result["filesystem"]["write_probe"])  # type: ignore[index]

            result = run_canary(  # type: ignore[arg-type]
                client,
                filesystem_write_probe=True,
                filesystem_root=live,
            )
            self.assertTrue(result["filesystem"]["write_probe"])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
