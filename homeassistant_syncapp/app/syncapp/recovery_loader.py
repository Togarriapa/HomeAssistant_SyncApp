from __future__ import annotations

import json
from pathlib import Path

from .journal_integrity import JournalIntegrityError, validate_journal_payload
from .transaction import ApplyPlan, FileTransaction, TransactionError
from .transaction_evidence import (
    TransactionEvidenceError,
    TransactionEvidenceMissing,
    TransactionEvidenceRoot,
)


def load_active_transaction(
    root: Path,
    source_dir: Path,
    staging_dir: Path,
) -> FileTransaction | None:
    """Load recovery evidence through a pinned no-follow transaction root."""
    try:
        with TransactionEvidenceRoot(root) as evidence:
            text = evidence.read_journal_text(FileTransaction.JOURNAL)
            if text is None:
                if evidence.remove_if_empty():
                    return None
                raise TransactionError(
                    "transaction directory exists without a journal; refusing new work because transaction state is ambiguous"
                )

            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise TransactionError(f"invalid recovery journal JSON: {exc}") from exc

            try:
                record = validate_journal_payload(
                    data,
                    root / FileTransaction.SNAPSHOT,
                    snapshot_hash_provider=lambda: evidence.snapshot_hashes(
                        FileTransaction.SNAPSHOT
                    ),
                )
            except JournalIntegrityError as exc:
                raise TransactionError(f"invalid recovery journal: {exc}") from exc

            # Journal and rollback snapshot validation are bound to the opened
            # transaction-root descriptor. Refuse to interpret the resulting record
            # if the pathname itself was replaced while that evidence was inspected.
            evidence.assert_path_identity()
            snapshot_root_identity = evidence.validated_snapshot_identity()

            plan = ApplyPlan(
                commit=record.commit,
                write_paths=record.write_paths,
                delete_paths=record.delete_paths,
                write_sha256=record.write_sha256,
            )
            transaction = FileTransaction(
                root,
                source_dir,
                staging_dir,
                plan,
                snapshot_root_identity=snapshot_root_identity,
            )
            transaction.existed = set(record.existed)
            transaction.snapshot_sha256 = dict(record.snapshot_sha256)
            transaction.supervisor_backup = record.supervisor_backup
            transaction.state = record.state
            return transaction
    except TransactionEvidenceMissing:
        return None
    except TransactionEvidenceError as exc:
        raise TransactionError(
            f"unsafe or unstable transaction recovery evidence: {exc}"
        ) from exc
