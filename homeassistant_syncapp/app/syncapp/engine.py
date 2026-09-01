from __future__ import annotations

import logging

from .config import Settings
from .git_repo import GitRepository
from .mirror import load_manifest, mirror_local_configuration, save_manifest
from .policy import is_allowed_relative
from .staging import StagingValidationError, stage_remote_configuration


LOGGER = logging.getLogger(__name__)


class SyncEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = GitRepository(
            path=settings.repository_dir,
            remote_url=settings.repository_url,
            branch=settings.branch,
            token=settings.github_token,
            user_name=settings.git_user_name,
            user_email=settings.git_user_email,
        )

    def run_once(self) -> None:
        self.repository.ensure()
        self.repository.fetch()
        relationship = self.repository.relationship()

        if relationship == "diverged":
            LOGGER.error(
                "Git state is diverged on branch %s; refusing both push and remote apply",
                self.settings.branch,
            )
            return

        if relationship in {"remote_only", "remote_ahead"}:
            try:
                staged = stage_remote_configuration(
                    self.repository,
                    self.settings.staging_dir,
                )
            except StagingValidationError as exc:
                LOGGER.error(
                    "Rejected remote commit during staging validation: %s",
                    exc,
                )
                return

            LOGGER.warning(
                "Remote commit %s passed staging validation (%d files, %d bytes). "
                "Live apply remains disabled until backup/apply/verify/rollback is implemented.",
                staged.commit,
                staged.file_count,
                staged.total_bytes,
            )
            return

        if relationship == "local_ahead":
            if self.settings.dry_run:
                LOGGER.warning(
                    "Local branch is ahead of GitHub, but dry-run is enabled; push skipped"
                )
                return
            LOGGER.warning("Local branch is ahead of GitHub; retrying previous push")
            self.repository.push()
            LOGGER.info("Previously committed local changes were pushed successfully")
            return

        previous_managed = load_manifest(self.settings.manifest_path)
        current_managed = mirror_local_configuration(
            self.settings.source_dir,
            self.settings.repository_dir,
            previous_managed,
        )
        self.repository.add_all()
        changed = self.repository.staged_paths()

        unsafe = [path for path in changed if not is_allowed_relative(path)]
        if unsafe:
            raise RuntimeError(
                "Refusing commit because blocked paths became staged: " + ", ".join(unsafe)
            )

        if not changed:
            save_manifest(self.settings.manifest_path, current_managed)
            LOGGER.info("No relevant local configuration changes detected")
            return

        LOGGER.info("Detected %d relevant local change(s): %s", len(changed), ", ".join(changed))
        if self.settings.dry_run:
            LOGGER.warning("Dry-run enabled; no commit or push performed")
            return

        commit = self.repository.commit("chore(homeassistant): sync local configuration")
        self.repository.push()
        save_manifest(self.settings.manifest_path, current_managed)
        LOGGER.info("Pushed local Home Assistant configuration commit %s", commit)
