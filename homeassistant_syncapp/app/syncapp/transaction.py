from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import time
from typing import Iterable, Protocol

from .policy import collect_allowed_files, is_allowed_relative


class TransactionError(RuntimeError):
    pass


class SupervisorOperations(Protocol):
    def create_homeassistant_backup(self, name: str) -> dict: ...
    def check_core_configuration(self) -> dict: ...
    def restart_core(self) -> dict: ...
    def core_api_root(self) -> dict: ...


@dataclass(frozen=True, slots=True)
class ApplyPlan:
    commit: str
    write_paths: tuple[str, ...]
    delete_paths: tuple[str, ...]

    @property
    def affected_paths(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.write_paths) | set(self.delete_paths)))


@dataclass(frozen=True, slots=True)
class TransactionResult:
    commit: str
    backup_slug: str
    affected_paths: tuple[str, ...]


def build_apply_plan(staging_dir: Path, baseline_paths: Iterable[str], commit: str) -> ApplyPlan:
    desired = collect_allowed_files(staging_dir)
    baseline = {path for path in baseline_paths if is_allowed_relative(path)}
    return ApplyPlan(
        commit=commit,
        write_paths=tuple(sorted(desired)),
        delete_paths=tuple(sorted(baseline - desired)),
    )


def _assert_safe_live_path(root: Path, relative: str) -> Path:
    if not is_allowed_relative(relative):
        raise TransactionError(f"blocked live path in transaction: {relative}")
    root = root.resolve()
    current = root
    parts = Path(relative).parts
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise TransactionError(f"refusing path through symlink: {relative}")
        if current.exists() and not current.is_dir():
            raise TransactionError(f"parent component is not a directory: {relative}")
    target = root.joinpath(*parts)
    if target.is_symlink():
        raise TransactionError(f"refusing to replace symlink: {relative}")
    return target


class FileTransaction:
    JOURNAL = "journal.json"
    SNAPSHOT = "snapshot"

    def __init__(self, root: Path, source_dir: Path, staging_dir: Path, plan: ApplyPlan):
        self.root = root
        self.source_dir = source_dir
        self.staging_dir = staging_dir
        self.plan = plan
        self.snapshot_dir = root / self.SNAPSHOT
        self.journal_path = root / self.JOURNAL
        self.existed: set[str] = set()
        self.supervisor_backup: str | None = None

    @classmethod
    def prepare(
        cls,
        root: Path,
        source_dir: Path,
        staging_dir: Path,
        plan: ApplyPlan,
    ) -> "FileTransaction":
        if root.exists():
            raise TransactionError("an unresolved transaction already exists")
        root.mkdir(parents=True, exist_ok=False)
        tx = cls(root, source_dir, staging_dir, plan)
        tx.snapshot_dir.mkdir()
        try:
            for relative in plan.affected_paths:
                target = _assert_safe_live_path(source_dir, relative)
                if target.exists():
                    if not target.is_file():
                        raise TransactionError(f"live target is not a regular file: {relative}")
                    tx.existed.add(relative)
                    backup = tx.snapshot_dir / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
            tx._write_journal("prepared")
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        return tx

    @classmethod
    def load_active(
        cls, root: Path, source_dir: Path, staging_dir: Path
    ) -> "FileTransaction | None":
        journal = root / cls.JOURNAL
        if not journal.exists():
            return None
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
            plan = ApplyPlan(
                commit=str(data["commit"]),
                write_paths=tuple(str(x) for x in data["write_paths"]),
                delete_paths=tuple(str(x) for x in data["delete_paths"]),
            )
            tx = cls(root, source_dir, staging_dir, plan)
            tx.existed = {str(x) for x in data.get("existed", [])}
            backup = data.get("supervisor_backup")
            tx.supervisor_backup = str(backup) if backup else None
            if data.get("state") == "completed":
                return None
            return tx
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise TransactionError(f"invalid recovery journal: {exc}") from exc

    def _write_journal(self, state: str) -> None:
        payload = {
            "version": 1,
            "state": state,
            "commit": self.plan.commit,
            "write_paths": list(self.plan.write_paths),
            "delete_paths": list(self.plan.delete_paths),
            "existed": sorted(self.existed),
            "supervisor_backup": self.supervisor_backup,
        }
        temporary = self.journal_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.journal_path)

    def record_supervisor_backup(self, identifier: str) -> None:
        self.supervisor_backup = identifier
        self._write_journal("backed_up")

    def mark(self, state: str) -> None:
        self._write_journal(state)

    def apply(self) -> None:
        self._write_journal("applying")
        for relative in self.plan.write_paths:
            target = _assert_safe_live_path(self.source_dir, relative)
            source = self.staging_dir / relative
            if source.is_symlink() or not source.is_file():
                raise TransactionError(f"staged source disappeared or changed type: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".syncapp-new")
            shutil.copy2(source, temporary)
            os.replace(temporary, target)

        for relative in self.plan.delete_paths:
            target = _assert_safe_live_path(self.source_dir, relative)
            if target.exists():
                if not target.is_file():
                    raise TransactionError(f"refusing to delete non-file: {relative}")
                target.unlink()
        self._write_journal("applied")

    def rollback(self) -> None:
        self._write_journal("rolling_back")
        failures: list[str] = []
        for relative in self.plan.affected_paths:
            try:
                target = _assert_safe_live_path(self.source_dir, relative)
                if relative in self.existed:
                    backup = self.snapshot_dir / relative
                    if not backup.is_file():
                        raise TransactionError(f"snapshot missing for {relative}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(target.name + ".syncapp-rollback")
                    shutil.copy2(backup, temporary)
                    os.replace(temporary, target)
                elif target.exists():
                    if not target.is_file():
                        raise TransactionError(f"rollback target is not a file: {relative}")
                    target.unlink()
            except Exception as exc:  # preserve every possible recovery failure
                failures.append(f"{relative}: {exc}")
        if failures:
            self._write_journal("rollback_failed")
            raise TransactionError("rollback failed: " + "; ".join(failures))
        self._write_journal("rolled_back")
        shutil.rmtree(self.root)

    def complete(self) -> None:
        self._write_journal("completed")
        shutil.rmtree(self.root)


def _response_data(response: dict) -> dict:
    data = response.get("data")
    return data if isinstance(data, dict) else response


def _backup_slug(response: dict) -> str:
    slug = _response_data(response).get("slug")
    if not slug:
        raise TransactionError("Supervisor backup completed without returning a slug")
    return str(slug)


def wait_for_core_health(
    supervisor: SupervisorOperations,
    *,
    timeout_seconds: int = 120,
    poll_seconds: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            data = _response_data(supervisor.core_api_root())
            if data.get("message") == "API running.":
                return
        except Exception as exc:  # Supervisor/Core can be transiently unavailable on restart.
            last_error = exc
        time.sleep(poll_seconds)
    suffix = f": {last_error}" if last_error else ""
    raise TransactionError(f"Home Assistant API did not become healthy{suffix}")


def recover_active_transaction(
    transaction: FileTransaction,
    supervisor: SupervisorOperations,
    *,
    health_timeout_seconds: int = 120,
) -> None:
    """Fail closed after an interrupted run: restore the snapshot and verify Core."""
    transaction.rollback()
    supervisor.check_core_configuration()
    supervisor.restart_core()
    wait_for_core_health(supervisor, timeout_seconds=health_timeout_seconds)


def execute_verified_transaction(
    transaction: FileTransaction,
    supervisor: SupervisorOperations,
    *,
    health_timeout_seconds: int = 120,
) -> TransactionResult:
    """Backup → Apply → config check → restart → health verify, with rollback."""
    if not transaction.plan.affected_paths:
        transaction.complete()
        raise TransactionError("refusing empty remote apply transaction")

    try:
        backup = supervisor.create_homeassistant_backup(
            f"SyncApp pre-apply {transaction.plan.commit[:12]}"
        )
        slug = _backup_slug(backup)
        transaction.record_supervisor_backup(slug)
    except Exception:
        transaction.rollback()
        raise

    try:
        transaction.apply()
        supervisor.check_core_configuration()
        transaction.mark("configuration_valid")
        supervisor.restart_core()
        transaction.mark("restarting")
        wait_for_core_health(supervisor, timeout_seconds=health_timeout_seconds)
        transaction.mark("verified")
    except Exception as apply_error:
        transaction.rollback()
        try:
            supervisor.check_core_configuration()
            supervisor.restart_core()
            wait_for_core_health(supervisor, timeout_seconds=health_timeout_seconds)
        except Exception as rollback_error:
            raise TransactionError(
                f"apply failed ({apply_error}); files were restored but rollback health verification failed ({rollback_error})"
            ) from rollback_error
        raise TransactionError(f"remote apply failed and was rolled back: {apply_error}") from apply_error

    result = TransactionResult(
        commit=transaction.plan.commit,
        backup_slug=slug,
        affected_paths=transaction.plan.affected_paths,
    )
    return result
