import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from syncapp.git_repo import GitRepository


def git_bytes(cwd: Path, *args: str, input_data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=input_data,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


class GitReplaceObjectSafetyTests(unittest.TestCase):
    def repository(self, root: Path) -> GitRepository:
        return GitRepository(
            path=root,
            remote_url="/tmp/syncapp-test-remote.git",
            branch="main",
            token=None,
            user_name="SyncApp Test",
            user_email="syncapp-test@example.invalid",
        )

    def test_ambient_replace_object_enable_is_overridden(self) -> None:
        repository = self.repository(Path("/unused"))
        with patch.dict(os.environ, {"GIT_NO_REPLACE_OBJECTS": "0"}, clear=False):
            environment = repository._environment()

        self.assertEqual(environment["GIT_NO_REPLACE_OBJECTS"], "1")

    def test_repository_replace_ref_cannot_substitute_blob_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repository"
            root.mkdir()
            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            original = git_bytes(
                root, "hash-object", "-w", "--stdin", input_data=b"trusted\n"
            ).decode("ascii").strip()
            replacement = git_bytes(
                root, "hash-object", "-w", "--stdin", input_data=b"attacker\n"
            ).decode("ascii").strip()
            subprocess.run(
                ["git", "replace", original, replacement],
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            ordinary = git_bytes(root, "cat-file", "blob", original)
            self.assertEqual(ordinary, b"attacker\n")

            repository = self.repository(root)
            self.assertEqual(repository.read_blob(original), b"trusted\n")


if __name__ == "__main__":
    unittest.main()
