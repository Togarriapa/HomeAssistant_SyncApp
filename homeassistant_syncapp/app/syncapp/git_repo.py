from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse


LOGGER = logging.getLogger(__name__)
_GITHUB_HOSTS = {"github.com", "www.github.com"}


class GitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitTreeEntry:
    mode: str
    object_type: str
    object_id: str
    path: str


class GitRepository:
    def __init__(
        self,
        path: Path,
        remote_url: str,
        branch: str,
        token: str | None,
        user_name: str,
        user_email: str,
    ) -> None:
        self.path = path
        self.remote_url = remote_url
        self.branch = branch
        self.token = token
        self.user_name = user_name
        self.user_email = user_email

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if self.token:
            parsed = urlparse(self.remote_url)
            if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
                raise GitError("refusing to send GitHub token to a non-GitHub HTTPS remote")
            credential = base64.b64encode(
                f"x-access-token:{self.token}".encode("utf-8")
            ).decode("ascii")
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credential}"
        return env

    def _run(
        self,
        *args: str,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.run(
            ["git", *args],
            cwd=cwd or self.path,
            env=self._environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip()
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return process

    def _run_bytes(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        process = subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=self._environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and process.returncode != 0:
            detail = (process.stderr or process.stdout).decode("utf-8", errors="replace").strip()
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return process

    def ensure(self) -> None:
        if not (self.path / ".git").exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                for child in self.path.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            result = self._run(
                "clone",
                "--no-tags",
                self.remote_url,
                str(self.path),
                cwd=self.path.parent,
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise GitError(f"git clone failed: {detail}")

        self._run("config", "user.name", self.user_name)
        self._run("config", "user.email", self.user_email)
        self._run("remote", "set-url", "origin", self.remote_url)
        self.fetch()

        remote_ref = f"refs/remotes/origin/{self.branch}"
        has_remote_branch = self._run(
            "show-ref", "--verify", "--quiet", remote_ref, check=False
        ).returncode == 0
        current = self._run("branch", "--show-current").stdout.strip()

        if current == self.branch:
            return
        if has_remote_branch:
            self._run("checkout", "-B", self.branch, f"origin/{self.branch}")
        else:
            self._run("checkout", "-B", self.branch)

    def fetch(self) -> None:
        self._run("fetch", "--prune", "origin")

    def head(self) -> str | None:
        result = self._run("rev-parse", "HEAD", check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def remote_head(self) -> str | None:
        result = self._run(
            "rev-parse", f"refs/remotes/origin/{self.branch}", check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def relationship(self) -> str:
        """Describe local HEAD relative to the configured remote branch."""
        local = self.head()
        remote = self.remote_head()

        if local is None and remote is None:
            return "empty"
        if remote is None:
            return "local_only"
        if local is None:
            return "remote_only"
        if local == remote:
            return "equal"
        if self._is_ancestor(local, remote):
            return "remote_ahead"
        if self._is_ancestor(remote, local):
            return "local_ahead"
        return "diverged"

    def _is_ancestor(self, older: str, newer: str) -> bool:
        return self._run(
            "merge-base", "--is-ancestor", older, newer, check=False
        ).returncode == 0

    def tree_entries(self, ref: str) -> list[GitTreeEntry]:
        raw = self._run_bytes("ls-tree", "-r", "-z", ref).stdout
        entries: list[GitTreeEntry] = []
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, separator, raw_path = record.partition(b"\t")
            if not separator:
                raise GitError("unexpected git ls-tree output")
            parts = metadata.decode("ascii").split()
            if len(parts) != 3:
                raise GitError("unexpected git ls-tree metadata")
            mode, object_type, object_id = parts
            path = raw_path.decode("utf-8")
            entries.append(GitTreeEntry(mode, object_type, object_id, path))
        return entries

    def remote_tree_entries(self) -> list[GitTreeEntry]:
        remote = self.remote_head()
        if remote is None:
            return []
        return self.tree_entries(remote)

    def blob_size(self, object_id: str) -> int:
        output = self._run("cat-file", "-s", object_id).stdout.strip()
        try:
            return int(output)
        except ValueError as exc:
            raise GitError(f"invalid blob size for {object_id}") from exc

    def read_blob(self, object_id: str) -> bytes:
        return self._run_bytes("cat-file", "blob", object_id).stdout

    def add_all(self) -> None:
        self._run("add", "-A")

    def staged_paths(self) -> list[str]:
        result = self._run("diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB")
        return [line for line in result.stdout.splitlines() if line]

    def tracked_paths(self) -> list[str]:
        raw = self._run_bytes("ls-files", "-z").stdout
        paths: list[str] = []
        for item in raw.split(b"\0"):
            if not item:
                continue
            try:
                paths.append(item.decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise GitError("tracked file path is not valid UTF-8") from exc
        return paths

    def discard_worktree_changes(self) -> None:
        """Drop rejected/dry-run candidates only from the isolated /data repository."""
        if self.head() is not None:
            self._run("reset", "--hard", "HEAD")
        else:
            self._run("rm", "-r", "--cached", "--ignore-unmatch", ".", check=False)
        self._run("clean", "-fdx")

    def commit(self, message: str) -> str:
        self._run("commit", "-m", message)
        head = self.head()
        if not head:
            raise GitError("commit completed without a HEAD")
        return head

    def push(self) -> None:
        self._run("push", "-u", "origin", f"HEAD:refs/heads/{self.branch}")

    def adopt_remote(self, expected_commit: str) -> None:
        remote = self.remote_head()
        if remote != expected_commit:
            raise GitError(
                f"remote moved during apply: expected {expected_commit}, found {remote}"
            )
        self._run("reset", "--hard", expected_commit)
        self._run("clean", "-fd")
