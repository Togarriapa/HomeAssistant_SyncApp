from pathlib import Path
import tempfile
import unittest

from runtime_fingerprint import FINGERPRINT_SCHEMA, runtime_fingerprint


class RuntimeFingerprintTests(unittest.TestCase):
    def _tree(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        app = root / "app"
        app.mkdir()
        entrypoint = root / "run.sh"
        entrypoint.write_text("#!/bin/sh\necho start\n", encoding="utf-8")
        (app / "main.py").write_text("print('main')\n", encoding="utf-8")
        package = app / "syncapp"
        package.mkdir()
        (package / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
        return temporary, app, entrypoint

    def test_fingerprint_is_stable_for_unchanged_runtime_bytes(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            first = runtime_fingerprint(app, entrypoint)
            second = runtime_fingerprint(app, entrypoint)

        self.assertEqual(first, second)
        self.assertEqual(first["schema"], FINGERPRINT_SCHEMA)
        self.assertEqual(first["algorithm"], "sha256")
        self.assertEqual(first["files"], 3)
        self.assertEqual(len(first["sha256"]), 64)

    def test_fingerprint_changes_when_runtime_content_changes(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            before = runtime_fingerprint(app, entrypoint)
            (app / "syncapp" / "engine.py").write_text("VALUE = 2\n", encoding="utf-8")
            after = runtime_fingerprint(app, entrypoint)

        self.assertNotEqual(before["sha256"], after["sha256"])

    def test_fingerprint_changes_when_entrypoint_changes(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            before = runtime_fingerprint(app, entrypoint)
            entrypoint.write_text("#!/bin/sh\necho changed\n", encoding="utf-8")
            after = runtime_fingerprint(app, entrypoint)

        self.assertNotEqual(before["sha256"], after["sha256"])

    def test_fingerprint_rejects_symlinked_app_file(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            target = Path(temporary.name) / "outside.py"
            target.write_text("outside = True\n", encoding="utf-8")
            (app / "linked.py").symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "symlink file"):
                runtime_fingerprint(app, entrypoint)

    def test_fingerprint_rejects_symlinked_app_directory(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            outside = Path(temporary.name) / "outside"
            outside.mkdir()
            (outside / "hidden.py").write_text("hidden = True\n", encoding="utf-8")
            (app / "linked-dir").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink directory"):
                runtime_fingerprint(app, entrypoint)

    def test_fingerprint_rejects_symlinked_entrypoint(self):
        temporary, app, entrypoint = self._tree()
        with temporary:
            real_entrypoint = Path(temporary.name) / "real-run.sh"
            entrypoint.rename(real_entrypoint)
            entrypoint.symlink_to(real_entrypoint)
            with self.assertRaisesRegex(RuntimeError, "cannot open runtime fingerprint input safely"):
                runtime_fingerprint(app, entrypoint)


if __name__ == "__main__":
    unittest.main()
