from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Iterable

from .policy import collect_allowed_files, is_allowed_relative


class TransactionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApplyPlan:
    commit: str
    write_paths: tuple[str, ...]
    delete_paths: tuple[str, ...]

    @property
    def affected_paths(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.write_paths) | set(self.delete_paths)))


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
    def load_active(cls, root: Path, source_dir: Path, staging_dir: Path) -> "FileTransaction | None":
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
