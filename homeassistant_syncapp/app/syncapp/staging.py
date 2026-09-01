from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import yaml

from .git_repo import GitRepository, GitTreeEntry
from .policy import collect_allowed_files, is_allowed_relative


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
_ALLOWED_MODES = {"100644", "100755"}


class StagingValidationError(RuntimeError):
    pass


class _HomeAssistantLoader(yaml.SafeLoader):
    """Parse HA YAML syntax while treating custom tags as opaque values."""


def _unknown_tag(loader: _HomeAssistantLoader, tag_suffix: str, node: yaml.Node) -> object:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    raise StagingValidationError(f"unsupported YAML node for tag !{tag_suffix}")


_HomeAssistantLoader.add_multi_constructor("!", _unknown_tag)


@dataclass(frozen=True, slots=True)
class StagingResult:
    commit: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class DirectoryValidationResult:
    file_count: int
    total_bytes: int


def _validate_entry(entry: GitTreeEntry) -> None:
    if entry.object_type != "blob":
        raise StagingValidationError(
            f"remote path {entry.path!r} is not a regular blob ({entry.object_type})"
        )
    if entry.mode not in _ALLOWED_MODES:
        raise StagingValidationError(
            f"remote path {entry.path!r} has unsupported Git mode {entry.mode}"
        )
    if not is_allowed_relative(entry.path):
        raise StagingValidationError(f"remote path is blocked by policy: {entry.path}")


def _read_utf8(path: Path, relative: str, kind: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise StagingValidationError(f"invalid UTF-8 {kind} in {relative}: {exc}") from exc


def _validate_file(path: Path, relative: str) -> None:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        text = _read_utf8(path, relative, "YAML")
        try:
            list(yaml.load_all(text, Loader=_HomeAssistantLoader))
        except yaml.YAMLError as exc:
            raise StagingValidationError(f"invalid YAML in {relative}: {exc}") from exc
    elif suffix == ".json":
        text = _read_utf8(path, relative, "JSON")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise StagingValidationError(f"invalid JSON in {relative}: {exc}") from exc
    elif suffix == ".py":
        text = _read_utf8(path, relative, "Python")
        try:
            ast.parse(text, filename=relative)
        except SyntaxError as exc:
            raise StagingValidationError(f"invalid Python syntax in {relative}: {exc}") from exc


def validate_configuration_directory(root: Path) -> DirectoryValidationResult:
    """Validate exactly the policy-allowed files in a materialized configuration tree."""
    files = sorted(collect_allowed_files(root))
    total_bytes = 0
    for relative in files:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise StagingValidationError(f"configuration path is not a regular file: {relative}")
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise StagingValidationError(
                f"configuration path {relative!r} exceeds {MAX_FILE_BYTES} byte limit"
            )
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise StagingValidationError(
                f"configuration tree exceeds {MAX_TOTAL_BYTES} byte staging limit"
            )
        _validate_file(path, relative)
    return DirectoryValidationResult(file_count=len(files), total_bytes=total_bytes)


def stage_remote_configuration(repository: GitRepository, staging_dir: Path) -> StagingResult:
    """Materialize a validated remote tree outside the live HA configuration."""
    remote = repository.remote_head()
    if remote is None:
        raise StagingValidationError("remote branch has no commit to stage")

    entries = repository.remote_tree_entries()
    planned: list[tuple[GitTreeEntry, int]] = []
    total_bytes = 0

    for entry in entries:
        _validate_entry(entry)
        size = repository.blob_size(entry.object_id)
        if size > MAX_FILE_BYTES:
            raise StagingValidationError(
                f"remote path {entry.path!r} exceeds {MAX_FILE_BYTES} byte limit"
            )
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise StagingValidationError(
                f"remote tree exceeds {MAX_TOTAL_BYTES} byte staging limit"
            )
        planned.append((entry, size))

    temporary = staging_dir.with_name(staging_dir.name + ".new")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)

    try:
        for entry, expected_size in planned:
            destination = temporary / entry.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = repository.read_blob(entry.object_id)
            if len(content) != expected_size:
                raise StagingValidationError(
                    f"blob size changed while staging {entry.path!r}"
                )
            destination.write_bytes(content)

        validated = validate_configuration_directory(temporary)
        if validated.file_count != len(planned) or validated.total_bytes != total_bytes:
            raise StagingValidationError(
                "materialized staging tree does not match validated Git tree"
            )

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        temporary.rename(staging_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return StagingResult(commit=remote, file_count=len(planned), total_bytes=total_bytes)
