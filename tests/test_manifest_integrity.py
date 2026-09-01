from pathlib import Path
import tempfile
import unittest

from syncapp.mirror import ManifestError, load_manifest, mirror_local_configuration, save_manifest


class ManifestIntegrityTests(unittest.TestCase):
    def test_valid_manifest_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            expected = {"configuration.yaml", "automations/lights.yaml"}

            save_manifest(path, expected)

            self.assertEqual(load_manifest(path), expected)

    def test_malformed_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            path.write_text("[", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "valid JSON"):
                load_manifest(path)

    def test_non_array_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            path.write_text('{"configuration.yaml": true}', encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "JSON array"):
                load_manifest(path)

    def test_non_string_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            path.write_text('["configuration.yaml", 42]', encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "all be strings"):
                load_manifest(path)

    def test_traversal_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            path.write_text('["../outside.yaml"]', encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "unsafe or invalid path"):
                load_manifest(path)

    def test_blocked_secret_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"
            path.write_text('["secrets.yaml"]', encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "unsafe or invalid path"):
                load_manifest(path)

    def test_save_refuses_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "managed.json"

            with self.assertRaisesRegex(ManifestError, "refusing to persist unsafe"):
                save_manifest(path, {"configuration.yaml", "../outside.yaml"})

            self.assertFalse(path.exists())

    def test_mirror_refuses_unsafe_previous_paths_before_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "homeassistant"
            repository = root / "repository"
            outside = root / "outside.yaml"
            source.mkdir()
            repository.mkdir()
            outside.write_text("must survive\n", encoding="utf-8")
            (source / "configuration.yaml").write_text("homeassistant:\n", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "unsafe managed paths"):
                mirror_local_configuration(source, repository, {"../outside.yaml"})

            self.assertEqual(outside.read_text(encoding="utf-8"), "must survive\n")
            self.assertFalse((repository / "configuration.yaml").exists())


if __name__ == "__main__":
    unittest.main()
