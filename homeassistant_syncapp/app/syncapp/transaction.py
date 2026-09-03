from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Protocol

from .journal_integrity import (
    JournalIntegrityError,
    attach_journal_digest,
    validate_journal_payload,
)
from .live_fs import LiveFilesystem, LiveFilesystemError
from .policy import is_allowed_relative


@dataclass(frozen=True, slots=True)
class ApplyPlan:
    commit: str
    write_paths: tuple[str, ...]
    delete_paths: tuple[str, ...]
    write_sha256: tuple[tuple[str, str], ...] = ()

    @property
    def affected_paths(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.write_paths) | set(self.delete_paths)))

    @property
    def write_hashes(self) -> dict[str, str]:
        return dict(self.write_sha256)


@dataclass(frozen=True, slots=True)
class TransactionResult:
    commit: str
    backup_slug: str
    affected_paths: tuple[str, ...]


class TransactionError(RuntimeError):
    pass


class SupervisorOperations(Protocol):
    def create_homeassistant_backup(self, name: str) -> str: ...
    def verify_homeassistant_backup(
        self,
        slug: str,
        expected_name: str,
    ) -> dict[str, object]: ...
    def check_core_configuration(self) -> dict: ...
    def restart_core(self) -> None: ...
    def wait_for_core_api(self, timeout_seconds: int) -> dict: ...


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_path_identity(path: Path) -> tuple[int, int]:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise TransactionError(f"cannot inspect rollback snapshot root safely: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise TransactionError("rollback snapshot root is not a directory")
    return info.st_dev, info.st_ino


def _pin_staged_content(staging_dir: Path, plan: ApplyPlan) -> ApplyPlan:
    hashes: list[tuple[str, str]] = []
    for relative in plan.write_paths:
        source = staging_dir / relative
        if source.is_symlink() or not source.is_file():
            raise TransactionError(f"staged source is not a regular file: {relative}")
        hashes.append((relative, _sha256_file(source)))
    return ApplyPlan(
        commit=plan.commit,
        write_paths=plan.write_paths,
        delete_paths=plan.delete_paths,
        write_sha256=tuple(sorted(hashes)),
    )


def build_apply_plan(
    staging_dir: Path,
    baseline_paths: set[str],
    commit: str,
    *,
    live_dir: Path | None = None,
) -> ApplyPlan:
    write_paths: list[str] = []
    staged_paths: set[str] = set()
    live_fs = LiveFilesystem(live_dir) if live_dir is not None else None
    for path in sorted(staging_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(staging_dir).as_posix()
        if not is_allowed_relative(relative):
            raise TransactionError(f"blocked path reached apply planner: {relative}")
        staged_paths.add(relative)
        if live_fs is None:
            write_paths.append(relative)
            continue
        try:
            exists = live_fs.exists_regular(relative)
            if not exists or live_fs.sha256(relative) != _sha256_file(path):
                write_paths.append(relative)
        except LiveFilesystemError as exc:
            raise TransactionError(
                f"cannot compare staged candidate to live configuration safely: {exc}"
            ) from exc
    return ApplyPlan(
        commit=commit,
        write_paths=tuple(write_paths),
        delete_paths=tuple(sorted(baseline_paths - staged_paths)),
    )


def _live_fs(root: Path) -> LiveFilesystem:
    return LiveFilesystem(root)


def _as_transaction_error(exc: LiveFilesystemError) -> TransactionError:
    return TransactionError(str(exc))


class FileTransaction:
    JOURNAL = "journal.json"
    SNAPSHOT = "snapshot"

    def __init__(
        self,
        root: Path,
        source_dir: Path,
        staging_dir: Path,
        plan: ApplyPlan,
        *,
        staging_root_identity: tuple[int, int] | None = None,
        snapshot_root_identity: tuple[int, int] | None = None,
    ):
        self.root = root
        self.source_dir = source_dir
        self.staging_dir = staging_dir
        self.plan = plan
        self.staging_root_identity = staging_root_identity
        self.snapshot_dir = root / self.SNAPSHOT
        self.snapshot_root_identity = snapshot_root_identity
        self.journal_path = root / self.JOURNAL
        self.existed: set[str] = set()
        self.snapshot_sha256: dict[str, str] = {}
        self.supervisor_backup: str | None = None
        self.state = "new"

    @classmethod
    def prepare(
        cls,
        root: Path,
        source_dir: Path,
        staging_dir: Path,
        plan: ApplyPlan,
        *,
        staging_root_identity: tuple[int, int] | None = None,
    ) -> "FileTransaction":
        if not plan.affected_paths:
            raise TransactionError("refusing empty remote apply transaction")
        if root.exists():
            raise TransactionError("an unresolved transaction already exists")

        plan = _pin_staged_content(staging_dir, plan)
        live_fs = _live_fs(source_dir)
        existed: set[str] = set()
        try:
            for relative in plan.affected_paths:
                if live_fs.exists_regular(relative):
                    existed.add(relative)
        except LiveFilesystemError as exc:
            raise _as_transaction_error(exc) from exc

        root.mkdir(parents=True, exist_ok=False)
        _fsync_directory(root.parent)
        tx = cls(
            root,
            source_dir,
            staging_dir,
            plan,
            staging_root_identity=staging_root_identity,
        )
        tx.existed = existed
        try:
            tx._write_journal("preparing")
            tx.snapshot_dir.mkdir()
            tx.snapshot_root_identity = _directory_path_identity(tx.snapshot_dir)
            _fsync_directory(tx.root)
            for relative in sorted(existed):
                backup = tx.snapshot_dir / relative
                try:
                    tx.snapshot_sha256[relative] = live_fs.copy_to(relative, backup)
                except LiveFilesystemError as exc:
                    raise _as_transaction_error(exc) from exc
                _fsync_directory(backup.parent)
            tx._assert_snapshot_root_identity()
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
            if not root.exists():
                return None
            try:
                if not any(root.iterdir()):
                    root.rmdir()
                    _fsync_directory(root.parent)
                    return None
            except OSError as exc:
                raise TransactionError(f"cannot inspect orphan transaction directory: {exc}") from exc
            raise TransactionError(
                "transaction directory exists without a journal; refusing new work because transaction state is ambiguous"
            )
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
            record = validate_journal_payload(data, root / cls.SNAPSHOT)
            plan = ApplyPlan(
                commit=record.commit,
                write_paths=record.write_paths,
                delete_paths=record.delete_paths,
                write_sha256=record.write_sha256,
            )
            tx = cls(root, source_dir, staging_dir, plan)
            tx.existed = set(record.existed)
            tx.snapshot_sha256 = dict(record.snapshot_sha256)
            tx.supervisor_backup = record.supervisor_backup
            tx.state = record.state
            return tx
        except (TransactionError, JournalIntegrityError):
            raise
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise TransactionError(f"invalid recovery journal: {exc}") from exc

    def _write_journal(self, state: str) -> None:
        self.state = state
        payload = attach_journal_digest(
            {
                "version": 2,
                "state": state,
                "commit": self.plan.commit,
                "write_paths": list(self.plan.write_paths),
                "delete_paths": list(self.plan.delete_paths),
                "write_sha256": self.plan.write_hashes,
                "existed": sorted(self.existed),
                "snapshot_sha256": dict(sorted(self.snapshot_sha256.items())),
                "supervisor_backup": self.supervisor_backup,
            }
        )
        temporary = self.journal_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.journal_path)
        _fsync_directory(self.root)

    def record_supervisor_backup(self, identifier: str) -> None:
        self.supervisor_backup = identifier
        self._write_journal("backed_up")

    def mark(self, state: str) -> None:
        self._write_journal(state)

    def _assert_snapshot_root_identity(self) -> None:
        if self.snapshot_root_identity is None:
            return
        if _directory_path_identity(self.snapshot_dir) != self.snapshot_root_identity:
            raise TransactionError("rollback snapshot root was replaced after validation")

    def assert_snapshot_unchanged(self) -> None:
        self._assert_snapshot_root_identity()
        if not self.snapshot_sha256:
            return
        if set(self.snapshot_sha256) != self.existed:
            raise TransactionError("transaction journal is missing rollback snapshot hashes")
        for relative, expected in self.snapshot_sha256.items():
            backup = self.snapshot_dir / relative
            if backup.is_symlink() or not backup.is_file():
                raise TransactionError(f"rollback snapshot disappeared or changed type: {relative}")
            if _sha256_file(backup) != expected:
                raise TransactionError(f"rollback snapshot changed after preparation: {relative}")
        self._assert_snapshot_root_identity()

    def assert_live_unchanged(self) -> None:
        self.assert_snapshot_unchanged()
        live_fs = _live_fs(self.source_dir)
        for relative in self.plan.affected_paths:
            try:
                exists = live_fs.exists_regular(relative)
                if relative in self.existed:
                    expected = self.snapshot_sha256.get(relative)
                    if expected is None:
                        snapshot = self.snapshot_dir / relative
                        if not snapshot.is_file():
                            raise TransactionError(f"snapshot missing for {relative}")
                        expected = _sha256_file(snapshot)
                    if not exists or live_fs.sha256(relative) != expected:
                        raise TransactionError(
                            f"live configuration changed during transaction preparation: {relative}"
                        )
                elif exists:
                    raise TransactionError(
                        f"live configuration created during transaction preparation: {relative}"
                    )
            except LiveFilesystemError as exc:
                raise _as_transaction_error(exc) from exc

    def assert_staging_unchanged(self) -> None:
        expected = self.plan.write_hashes
        if set(expected) != set(self.plan.write_paths):
            raise TransactionError("transaction journal is missing staged-content hashes")
        for relative in self.plan.write_paths:
            source = self.staging_dir / relative
            if source.is_symlink() or not source.is_file():
                raise TransactionError(f"staged source disappeared or changed type: {relative}")
            if _sha256_file(source) != expected[relative]:
                raise TransactionError(
                    f"staged configuration changed during transaction preparation: {relative}"
                )

    def apply(self) -> None:
        if self.state != "backed_up":
            raise TransactionError(
                f"transaction cannot apply from state {self.state}; a recorded Supervisor backup is required"
            )
        self.assert_staging_unchanged()
        self.assert_snapshot_unchanged()
        self._write_journal("applying")
        live_fs = _live_fs(self.source_dir)
        try:
            for relative in self.plan.write_paths:
                source = self.staging_dir / relative
                live_fs.replace_from(
                    relative,
                    source,
                    self.plan.write_hashes[relative],
                    expected_source_root_identity=self.staging_root_identity,
                )
            for relative in self.plan.delete_paths:
                live_fs.delete(relative)
        except LiveFilesystemError as exc:
            raise _as_transaction_error(exc) from exc
        self._write_journal("applied")

    def rollback(self, *, cleanup: bool = True) -> None:
        self.assert_snapshot_unchanged()
        self._write_journal("rolling_back")
        failures: list[str] = []
        live_fs = _live_fs(self.source_dir)
        for relative in self.plan.affected_paths:
            try:
                if relative in self.existed:
                    backup = self.snapshot_dir / relative
                    if not backup.is_file():
                        raise TransactionError(f"snapshot missing for {relative}")
                    expected = self.snapshot_sha256.get(relative)
                    if expected is None:
                        expected = _sha256_file(backup)
                    elif _sha256_file(backup) != expected:
                        raise TransactionError(f"rollback snapshot changed before restore: {relative}")
                    live_fs.replace_from(
                        relative,
                        backup,
                        expected,
                        expected_source_root_identity=self.snapshot_root_identity,
                    )
                else:
                    live_fs.delete(relative)
            except Exception as exc:
                failures.append(f"{relative}: {exc}")
        if failures:
            self._write_journal("rollback_failed")
            raise TransactionError("rollback failed: " + "; ".join(failures))
        self._write_journal("rolled_back")
        if cleanup:
            self.discard()

    def discard(self) -> None:
        parent = self.root.parent
        shutil.rmtree(self.root, ignore_errors=False)
        _fsync_directory(parent)

    def complete(self) -> None:
        self._write_journal("completed")
        self.discard()


def recover_active_transaction(
    transaction: FileTransaction,
    supervisor: SupervisorOperations,
    *,
    health_timeout_seconds: int = 120,
) -> None:
    if transaction.state in {"preparing", "prepared", "backed_up"}:
        transaction.discard()
        return
    transaction.rollback(cleanup=False)
    try:
        supervisor.check_core_configuration()
        supervisor.restart_core()
        supervisor.wait_for_core_api(health_timeout_seconds)
    except Exception as exc:
        transaction.mark("rollback_health_failed")
        raise TransactionError(
            f"files restored after interrupted transaction, but old Core health could not be verified: {exc}"
        ) from exc
    transaction.discard()


def execute_verified_transaction(
    transaction: FileTransaction,
    supervisor: SupervisorOperations,
    *,
    health_timeout_seconds: int = 120,
) -> TransactionResult:
    backup_name = f"SyncApp pre-apply {transaction.plan.commit[:12]}"
    try:
        slug = supervisor.create_homeassistant_backup(backup_name)
        supervisor.verify_homeassistant_backup(slug, backup_name)
        transaction.record_supervisor_backup(slug)
    except Exception as exc:
        transaction.discard()
        raise TransactionError(f"pre-apply Supervisor backup failed: {exc}") from exc

    try:
        transaction.assert_live_unchanged()
        transaction.assert_staging_unchanged()
        supervisor.verify_homeassistant_backup(slug, backup_name)
    except Exception as exc:
        transaction.discard()
        raise TransactionError(
            "live/staged configuration or Supervisor backup changed before live mutation; "
            f"remote apply aborted without mutation: {exc}"
        ) from exc

    restart_requested = False
    try:
        transaction.apply()
        supervisor.verify_homeassistant_backup(slug, backup_name)
        supervisor.check_core_configuration()
        transaction.mark("configuration_valid")
        restart_requested = True
        supervisor.restart_core()
        transaction.mark("restarting")
        supervisor.wait_for_core_api(health_timeout_seconds)
        transaction.mark("verified")
    except Exception as apply_error:
        transaction.rollback(cleanup=not restart_requested)
        if restart_requested:
            try:
                supervisor.check_core_configuration()
                supervisor.restart_core()
                supervisor.wait_for_core_api(health_timeout_seconds)
            except Exception as rollback_error:
                transaction.mark("rollback_health_failed")
                raise TransactionError(
                    f"apply failed ({apply_error}); files were restored but rollback Core health failed ({rollback_error})"
                ) from rollback_error
            transaction.discard()
        raise TransactionError(
            f"remote apply failed and previous configuration was restored: {apply_error}"
        ) from apply_error

    return TransactionResult(
        commit=transaction.plan.commit,
        backup_slug=slug,
        affected_paths=transaction.plan.affected_paths,
    )
