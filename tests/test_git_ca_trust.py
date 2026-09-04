import json
import os
from pathlib import Path
import tempfile
import unittest

from syncapp.config import Settings
from syncapp.runtime_environment import RuntimeEnvironmentError, configure_git_ca_trust


class GitCaTrustTests(unittest.TestCase):
    def _load_settings(self, extra: dict[str, object]) -> Settings:
        payload: dict[str, object] = {
            "homeassistant_repository_url": "https://github.com/example/home-assistant-config.git",
            **extra,
        }
        with tempfile.TemporaryDirectory() as tmp:
            options = Path(tmp) / "options.json"
            options.write_text(json.dumps(payload), encoding="utf-8")
            return Settings.load(options)

    def test_optional_ca_bundle_is_confined_to_app_config_root(self) -> None:
        settings = self._load_settings({"git_ca_bundle": "company-ca.pem"})
        self.assertEqual(settings.git_ca_bundle, Path("/config/company-ca.pem"))

    def test_missing_ca_bundle_uses_system_trust_contract(self) -> None:
        settings = self._load_settings({})
        self.assertIsNone(settings.git_ca_bundle)

    def test_ca_bundle_rejects_path_traversal_and_subdirectories(self) -> None:
        for value in ("../company-ca.pem", "/tmp/company-ca.pem", "nested/company-ca.pem", "."):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "single filename"):
                    self._load_settings({"git_ca_bundle": value})

    def test_default_ca_trust_overrides_ambient_ca_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system_dir = root / "system-certs"
            system_dir.mkdir()
            system_bundle = system_dir / "ca-certificates.crt"
            system_bundle.write_text("system-ca", encoding="utf-8")
            environment = {
                "GIT_SSL_CAINFO": "/tmp/attacker-git-ca.pem",
                "GIT_SSL_CAPATH": "/tmp/attacker-git-ca-dir",
                "CURL_CA_BUNDLE": "/tmp/attacker-curl-ca.pem",
                "SSL_CERT_FILE": "/tmp/attacker-ssl-file.pem",
                "SSL_CERT_DIR": "/tmp/attacker-ssl-dir",
            }

            configure_git_ca_trust(
                None,
                environment,
                system_bundle=system_bundle,
                system_ca_path=system_dir,
                snapshot_path=root / "unused.pem",
            )

            self.assertEqual(environment["GIT_SSL_CAINFO"], str(system_bundle))
            self.assertEqual(environment["GIT_SSL_CAPATH"], str(system_dir))
            self.assertNotIn("CURL_CA_BUNDLE", environment)
            self.assertNotIn("SSL_CERT_FILE", environment)
            self.assertNotIn("SSL_CERT_DIR", environment)

    def test_custom_ca_is_snapshotted_before_git_uses_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "company-ca.pem"
            content = b"-----BEGIN CERTIFICATE-----\ntrusted-bytes\n-----END CERTIFICATE-----\n"
            source.write_bytes(content)
            system_dir = root / "system-certs"
            system_dir.mkdir()
            snapshot = root / "data" / "trusted-ca.pem"
            environment: dict[str, str] = {}

            configure_git_ca_trust(
                source,
                environment,
                system_bundle=root / "unused-system-bundle",
                system_ca_path=system_dir,
                snapshot_path=snapshot,
            )

            self.assertEqual(snapshot.read_bytes(), content)
            self.assertEqual(environment["GIT_SSL_CAINFO"], str(snapshot))
            self.assertEqual(environment["GIT_SSL_CAPATH"], str(system_dir))
            self.assertEqual(os.stat(snapshot).st_mode & 0o777, 0o600)

    def test_custom_ca_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.pem"
            real.write_text("trusted", encoding="utf-8")
            link = root / "linked.pem"
            link.symlink_to(real)
            system_dir = root / "system-certs"
            system_dir.mkdir()

            with self.assertRaisesRegex(RuntimeEnvironmentError, "opened safely"):
                configure_git_ca_trust(
                    link,
                    {},
                    system_bundle=root / "unused-system-bundle",
                    system_ca_path=system_dir,
                    snapshot_path=root / "snapshot.pem",
                )


if __name__ == "__main__":
    unittest.main()
