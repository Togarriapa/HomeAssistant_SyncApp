from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlparse


_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


@dataclass(frozen=True, slots=True)
class Settings:
    repository_url: str
    branch: str
    github_token: str | None
    poll_interval_seconds: int
    dry_run: bool
    git_user_name: str
    git_user_email: str
    source_dir: Path = Path("/homeassistant")
    repository_dir: Path = Path("/data/repository")
    manifest_path: Path = Path("/data/managed_paths.json")

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

        repository_url = str(raw.get("repository_url") or "").strip()
        parsed = urlparse(repository_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("repository_url must be an HTTPS Git repository URL")

        branch = str(raw.get("branch", "main")).strip()
        if not branch or not _BRANCH_RE.fullmatch(branch) or ".." in branch:
            raise ValueError("branch contains unsupported characters")

        interval = int(raw.get("poll_interval_seconds", 60))
        if interval < 30:
            raise ValueError("poll_interval_seconds must be at least 30")

        token = raw.get("github_token")
        token = str(token).strip() if token else None
        dry_run = bool(raw.get("dry_run", True))
        if not dry_run and not token:
            raise ValueError("github_token is required when dry_run is disabled")

        return cls(
            repository_url=repository_url,
            branch=branch,
            github_token=token,
            poll_interval_seconds=interval,
            dry_run=dry_run,
            git_user_name=str(raw.get("git_user_name", "HomeAssistant SyncApp")),
            git_user_email=str(raw.get("git_user_email", "homeassistant-syncapp@localhost")),
        )
