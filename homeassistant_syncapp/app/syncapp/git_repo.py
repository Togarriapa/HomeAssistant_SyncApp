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
_GIT_ENVIRONMENT_OVERRIDES = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_EXEC_PATH",
    "GIT_TEMPLATE_DIR",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_PROXY_COMMAND",
    "GIT_ASKPASS",
    "SSH_ASKPASS",
}


class GitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitTreeEntry:
    mode: str
    object_type: str
    object_id: str
    path: str


def _remote_identity(value: str) -> tuple[str, str]:
    """Return a comparison identity without changing the remote used by Git."""
    parsed = urlparse(value)
    if parsed.scheme == "https" and (parsed.hostname or "").lower() in _GITHUB_HOSTS:
        path = parsed.path.strip("/")
        if path.lower().endswith(".git"):
            path = path[:-4]
        return "github.com", path.lower()
    return "literal", value


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
        for key in list(env):
            if key in _GIT_ENVIRONMENT_OVERRIDES or key.startswith("GIT_CONFIG_"):
                env.pop(key, None)

        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull

        config: list[tuple[str, str]] = [
            ("core.hooksPath", os.devnull),
            ("credential.helper", ""),
        ]
        if self.token:
            parsed = urlparse(self.remote_url)
            if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
                raise GitError("refusing to send GitHub token to a non-GitHub HTTPS remote")
            credential = base64.b64encode(
                f"x-access-token:{self.token}".encode("utf-8")
            ).decode("ascii")
            config.append(
                (
                    "http.https://github.com/.extraHeader",
                    f"Authorization: Basic {credential}",
                )
            )

        env["GIT_CONFIG_COUNT"] = str(len(config))
        for index, (key, value) in enumerate(config):
            env[f"GIT_CONFIG_KEY_{index}"] = key
            env[f"GIT_CONFIG_VALUE_{index}"] = value
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

    def _origin_urls(self, *, push: bool) -> list[str]:
        args = ["remote", "get-url"]
        if push:
            args.append("--push")
        args.extend(["--all", "origin"])
        result = self._run(*args, check=False)
        if result.returncode != 0:
            direction = "push" if push else "fetch"
            raise GitError(
                f"existing managed repository has no readable origin {direction} URL; "
                "refusing implicit reconfiguration"
            )
        urls = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not urls:
            direction = "push" if push else "fetch"
            raise GitError(
                f"existing managed repository has no readable origin {direction} URL; "
                "refusing implicit reconfiguration"
            )
        return urls

    def _assert_remote_provenance(self) -> None:
        expected = _remote_identity(self.remote_url)
        fetch_urls = self._origin_urls(push=False)
        if len(fetch_urls) != 1 or any(
            _remote_identity(value) != expected for value in fetch_urls
        ):
            raise GitError(
                "configured managed repository differs from the origin fetch URL stored under /data; "
                "refusing implicit retargeting because Git history and managed-path state belong to the existing target"
            )

        push_urls = self._origin_urls(push=True)
        if any(_remote_identity(value) != expected for value in push_urls):
            raise GitError(
                "origin push URL differs from the configured managed repository; "
                "refusing to send Home Assistant configuration to an unapproved Git target"
            )

    def ensure(self) -> None:
        existing_repository = (self.path / ".git").exists()
        if not existing_repository:
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
        else:
            self._assert_remote_provenance()
            current = self._run("branch", "--show-current").stdout.strip()
            if current != self.branch:
                shown = current or "<detached>"
                raise GitError(
                    f"configured managed branch {self.branch!r} differs from persistent branch {shown!r}; "
                    "refusing implicit branch retargeting because managed-path and transaction provenance belong to the existing branch"
                )

        self._assert_remote_provenance()
        self._run("config", "user.name", self.user_name)
        self._run("config", "user.email", self.user_email)
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
        self._assert_remote_provenance()
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

    def unpushed_commit_count(self) -> int:
        """Count commits that would be sent by a retry push from the managed branch."""
        local = self.head()
        if local is None:
            return 0
        remote = self.remote_head()
        if remote is not None:
            if not self._is_ancestor(remote, local):
                raise GitError("cannot count unpushed commits from non-ancestor remote")
            revision = f"{remote}..{local}"
        else:
            revision = local
        raw = self._run("rev-list", "--count", revision).stdout.strip()
        try:
            return int(raw)
        except ValueError as exc:
            raise GitError(f"invalid unpushed commit count: {raw!r}") from exc

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

    def index_tree_entries(self) -> list[GitTreeEntry]:
        """Return the exact tree represented by the staged Git index."""
        tree = self._run("write-tree").stdout.strip()
        if not tree:
            raise GitError("git write-tree returned no staged tree")
        return self.tree_entries(tree)

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
        self._assert_remote_provenance()
        self._run("push", "-u", "origin", f"HEAD:refs/heads/{self.branch}")

    def adopt_remote(self, expected_commit: str) -> None:
        remote = self.remote_head()
        if remote != expected_commit:
            raise GitError(
                f"remote moved during apply: expected {expected_commit}, found {remote}"
            )
        self._run("reset", "--hard", expected_commit)
        self._run("clean", "-fd")
