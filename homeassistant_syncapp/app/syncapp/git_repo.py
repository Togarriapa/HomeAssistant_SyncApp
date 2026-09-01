from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
import shutil
import subprocess


LOGGER = logging.getLogger(__name__)


class GitError(RuntimeError):
    pass


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

    def add_all(self) -> None:
        self._run("add", "-A")

    def staged_paths(self) -> list[str]:
        result = self._run("diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB")
        return [line for line in result.stdout.splitlines() if line]

    def commit(self, message: str) -> str:
        self._run("commit", "-m", message)
        head = self.head()
        if not head:
            raise GitError("commit completed without a HEAD")
        return head

    def push(self) -> None:
        self._run("push", "-u", "origin", f"HEAD:refs/heads/{self.branch}")
