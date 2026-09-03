from __future__ import annotations

import ast
from pathlib import Path
import unittest

from syncapp.policy import is_allowed_relative


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPOSITORY_ROOT / "homeassistant_syncapp" / "app" / "syncapp"


class WorkflowSafetyContractTests(unittest.TestCase):
    def test_git_repository_never_invokes_blind_pull(self) -> None:
        source = (APP_ROOT / "git_repo.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        string_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertNotIn(
            "pull",
            string_literals,
            "SyncApp must fetch remote evidence and stage/validate it; never add a blind git pull",
        )

    def test_live_mutation_modules_do_not_shell_out_to_git(self) -> None:
        for filename in ("apply.py", "transaction.py", "live_fs.py"):
            with self.subTest(filename=filename):
                source = (APP_ROOT / filename).read_text(encoding="utf-8")
                tree = ast.parse(source)
                imported_modules = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported_modules.update(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported_modules.add(node.module)
                self.assertNotIn("subprocess", imported_modules)

    def test_secret_and_runtime_exclusions_are_non_negotiable(self) -> None:
        blocked = (
            "secrets.yaml",
            "nested/secrets.yml",
            ".storage/core.config_entries",
            "nested/.storage/auth",
            "home-assistant_v2.db",
            "home-assistant_v2.db-wal",
            "logs/home-assistant.log",
            "logs/home-assistant.log.1",
            "certs/tls.key",
            "certs/tls.pem",
            "certs/tls.p12",
            "certs/tls.pfx",
            "runtime/process.pid",
            "runtime/state.lock",
            "cache/value.tmp",
            ".git/config",
        )
        for relative in blocked:
            with self.subTest(relative=relative):
                self.assertFalse(is_allowed_relative(relative))

    def test_update_workflow_is_documented_in_required_order(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                REPOSITORY_ROOT / "README.md",
                REPOSITORY_ROOT / "homeassistant_syncapp" / "DOCS.md",
            )
        )
        required = "Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback"
        self.assertIn(required, documentation)


if __name__ == "__main__":
    unittest.main()
