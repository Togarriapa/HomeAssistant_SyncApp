from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlparse


_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_GITHUB_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True, slots=True)
class Settings:
    repository_url: str
    branch: str
    github_token: str | None
    poll_interval_seconds: int
    dry_run: bool
    remote_apply_enabled: bool
    verify_timeout_seconds: int
    git_user_name: str
    git_user_email: str
    backup_retention_count: int = 10
    initial_local_publish_enabled: bool = False
    source_dir: Path = Path("/homeassistant")
    repository_dir: Path = Path("/data/repository")
    staging_dir: Path = Path("/data/staging")
    transaction_dir: Path = Path("/data/transaction")
    manifest_path: Path = Path("/data/managed_paths.json")

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

        repository_url = str(raw.get("repository_url") or "").strip()
        parsed = urlparse(repository_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("repository_url must be an HTTPS Git repository URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("repository_url must not contain embedded credentials")
        if parsed.hostname.lower() not in _GITHUB_HOSTS:
            raise ValueError("repository_url must point to github.com")

        branch = str(raw.get("branch", "main")).strip()
        if not branch or not _BRANCH_RE.fullmatch(branch) or ".." in branch:
            raise ValueError("branch contains unsupported characters")

        interval = int(raw.get("poll_interval_seconds", 60))
        if interval < 30:
            raise ValueError("poll_interval_seconds must be at least 30")

        verify_timeout = int(raw.get("verify_timeout_seconds", 120))
        if not 30 <= verify_timeout <= 600:
            raise ValueError("verify_timeout_seconds must be between 30 and 600")

        backup_retention_count = int(raw.get("backup_retention_count", 10))
        if not 0 <= backup_retention_count <= 100:
            raise ValueError("backup_retention_count must be between 0 and 100")

        token = raw.get("github_token")
        token = str(token).strip() if token else None
        dry_run = bool(raw.get("dry_run", True))
        remote_apply_enabled = bool(raw.get("remote_apply_enabled", False))
        initial_local_publish_enabled = bool(raw.get("initial_local_publish_enabled", False))
        if (not dry_run or remote_apply_enabled) and not token:
            raise ValueError(
                "github_token is required when pushes or remote apply are enabled"
            )

        return cls(
            repository_url=repository_url,
            branch=branch,
            github_token=token,
            poll_interval_seconds=interval,
            dry_run=dry_run,
            remote_apply_enabled=remote_apply_enabled,
            verify_timeout_seconds=verify_timeout,
            git_user_name=str(raw.get("git_user_name", "HomeAssistant SyncApp")),
            git_user_email=str(raw.get("git_user_email", "homeassistant-syncapp@example.invalid")),
            backup_retention_count=backup_retention_count,
            initial_local_publish_enabled=initial_local_publish_enabled,
        )
