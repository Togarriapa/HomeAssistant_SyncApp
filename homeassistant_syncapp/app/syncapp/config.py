from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlparse


_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_GITHUB_HOSTS = {"github.com", "www.github.com"}
_SYNCAPP_REPOSITORY_IDENTITY = ("github.com", "togarriapa/homeassistant_syncapp")


def _validate_github_repository_url(value: str, option_name: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{option_name} must be an HTTPS Git repository URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{option_name} must not contain embedded credentials")
    hostname = parsed.hostname.lower()
    if hostname not in _GITHUB_HOSTS:
        raise ValueError(f"{option_name} must point to github.com")

    path = parsed.path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    parts = path.split("/") if path else []
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"{option_name} must identify one GitHub repository")
    return "github.com", "/".join(parts).lower()


@dataclass(frozen=True, slots=True)
class Settings:
    # Internal compatibility name retained so the sync engine and Git abstraction do
    # not need to know about configuration migration. User-facing configuration uses
    # homeassistant_repository_url to distinguish the managed Home Assistant
    # repository from the SyncApp source repository.
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
    initial_remote_apply_enabled: bool = False
    remote_max_deletions: int = 25
    remote_max_deletion_percent: int = 50
    source_dir: Path = Path("/homeassistant")
    repository_dir: Path = Path("/data/repository")
    staging_dir: Path = Path("/data/staging")
    transaction_dir: Path = Path("/data/transaction")
    manifest_path: Path = Path("/data/managed_paths.json")

    @property
    def homeassistant_repository_url(self) -> str:
        return self.repository_url

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

        configured_url = str(raw.get("homeassistant_repository_url") or "").strip()
        legacy_url = str(raw.get("repository_url") or "").strip()
        if not configured_url and not legacy_url:
            raise ValueError("homeassistant_repository_url is required")

        if configured_url and legacy_url:
            configured_identity = _validate_github_repository_url(
                configured_url, "homeassistant_repository_url"
            )
            legacy_identity = _validate_github_repository_url(
                legacy_url, "repository_url"
            )
            if configured_identity != legacy_identity:
                raise ValueError(
                    "homeassistant_repository_url and deprecated repository_url disagree"
                )

        repository_url = configured_url or legacy_url
        option_name = "homeassistant_repository_url" if configured_url else "repository_url"
        repository_identity = _validate_github_repository_url(repository_url, option_name)
        if repository_identity == _SYNCAPP_REPOSITORY_IDENTITY:
            raise ValueError(
                "homeassistant_repository_url must point to a separate Home Assistant "
                "configuration repository, not the SyncApp source repository"
            )

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

        remote_max_deletions = int(raw.get("remote_max_deletions", 25))
        if not 0 <= remote_max_deletions <= 10000:
            raise ValueError("remote_max_deletions must be between 0 and 10000")

        remote_max_deletion_percent = int(raw.get("remote_max_deletion_percent", 50))
        if not 0 <= remote_max_deletion_percent <= 100:
            raise ValueError("remote_max_deletion_percent must be between 0 and 100")

        token = raw.get("github_token")
        token = str(token).strip() if token else None
        dry_run = bool(raw.get("dry_run", True))
        remote_apply_enabled = bool(raw.get("remote_apply_enabled", False))
        initial_local_publish_enabled = bool(raw.get("initial_local_publish_enabled", False))
        initial_remote_apply_enabled = bool(raw.get("initial_remote_apply_enabled", False))
        if initial_local_publish_enabled and initial_remote_apply_enabled:
            raise ValueError(
                "initial_local_publish_enabled and initial_remote_apply_enabled are mutually exclusive"
            )
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
            initial_remote_apply_enabled=initial_remote_apply_enabled,
            remote_max_deletions=remote_max_deletions,
            remote_max_deletion_percent=remote_max_deletion_percent,
        )
