from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git_repo import GitRepository
from .policy import collect_allowed_files, is_allowed_relative


@dataclass(frozen=True, slots=True)
class DriftResult:
    changed: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.changed


def detect_live_drift(repository: GitRepository, source_dir: Path) -> DriftResult:
    """Compare live allowed files with the local Git HEAD baseline."""
    head = repository.head()
    if head is None:
        live = sorted(collect_allowed_files(source_dir))
        return DriftResult(tuple(live))

    baseline_entries = {
        entry.path: entry
        for entry in repository.tree_entries(head)
        if entry.object_type == "blob" and is_allowed_relative(entry.path)
    }
    live_paths = collect_allowed_files(source_dir)
    changed: list[str] = []

    for relative in sorted(set(baseline_entries) | live_paths):
        entry = baseline_entries.get(relative)
        live_path = source_dir / relative
        if entry is None or relative not in live_paths:
            changed.append(relative)
            continue
        if live_path.read_bytes() != repository.read_blob(entry.object_id):
            changed.append(relative)

    return DriftResult(tuple(changed))
