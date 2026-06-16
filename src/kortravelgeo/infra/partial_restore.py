"""T-243 best-effort recovery of a partially corrupted backup archive.

``verify_internal_checksums`` aborts the whole restore if a single file's sha256 is wrong.
When a backup is the *only* copy and one table's data file rotted, that is a needless total
loss. With ``allow_partial=true`` the restore instead collects every corrupted file and, if
only per-table data files (``dump/<id>.dat``) are affected, restores the intact tables via
``pg_restore --use-list`` while skipping the corrupted ones — recording exactly what was
recovered and skipped in a ``partial_restore`` manifest block.

Corruption of ``manifest.json`` or ``dump/toc.dat`` is a **hard failure**: without a valid
table of contents there is nothing trustworthy to selectively restore.

This is an emergency last resort (disabled by default, zero regression). The functions here
are pure so the policy is unit-tested without a database; the live ``pg_restore --use-list``
flow is integration-tested in T-245.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

#: Files whose corruption makes any partial restore untrustworthy (hard-fail).
CRITICAL_PARTIAL_RESTORE_FILES = ("manifest.json", "dump/toc.dat")

#: ``dump/<dumpId>.dat`` or ``dump/<dumpId>.dat.gz`` — a single table's data file. The stem
#: number is the pg_dump TOC dumpId, which is also the leading token of a ``pg_restore -l`` line.
_DATA_FILE_RE = re.compile(r"^dump/(\d+)\.dat(?:\.gz)?$")


def partial_restore_data_id(relative_path: str) -> str | None:
    """Return the TOC dumpId for a ``dump/<id>.dat`` data file, else ``None``."""
    match = _DATA_FILE_RE.match(relative_path)
    return match.group(1) if match else None


@dataclass(frozen=True, slots=True)
class PartialRestorePartition:
    """Split of corrupted files into hard-fail vs. skippable per-table data files."""

    critical: tuple[str, ...] = ()
    skippable_files: tuple[str, ...] = ()
    skippable_data_ids: tuple[str, ...] = ()

    @property
    def can_partial_restore(self) -> bool:
        # Partial restore is possible only when nothing critical is corrupted AND there is at
        # least one corrupted data file to skip (otherwise there is nothing to recover from).
        return not self.critical and bool(self.skippable_data_ids)


def partition_checksum_failures(failures: Collection[str]) -> PartialRestorePartition:
    """Classify corrupted relative paths into critical vs. skippable data files (pure).

    Anything that is not a ``dump/<id>.dat`` data file (including ``manifest.json`` and
    ``dump/toc.dat``) is treated as critical — partial restore must not silently proceed past
    an unrecognized corrupted file.
    """
    critical: list[str] = []
    skippable_files: list[str] = []
    skippable_ids: list[str] = []
    for relative in sorted(failures):
        data_id = partial_restore_data_id(relative)
        if data_id is None:
            critical.append(relative)
        else:
            skippable_files.append(relative)
            skippable_ids.append(data_id)
    return PartialRestorePartition(
        critical=tuple(critical),
        skippable_files=tuple(skippable_files),
        skippable_data_ids=tuple(skippable_ids),
    )


@dataclass(frozen=True, slots=True)
class PartialRestoreUseList:
    """A filtered ``pg_restore --use-list`` plan: lines to write + the entries skipped."""

    lines: tuple[str, ...] = ()
    skipped_entries: tuple[str, ...] = ()
    skipped_ids: tuple[str, ...] = field(default=())


def build_partial_restore_uselist(
    toc_lines: Sequence[str], corrupted_ids: Collection[str]
) -> PartialRestoreUseList:
    """Comment out corrupted entries in a ``pg_restore -l`` listing (pure).

    Each non-comment TOC line begins ``<dumpId>; ...``. Lines whose dumpId is corrupted are
    prefixed with ``;`` so ``pg_restore --use-list`` skips them; every other line is kept
    verbatim. Returns the lines to write plus the human-readable entries that were skipped.
    """
    corrupted = {str(i) for i in corrupted_ids}
    out: list[str] = []
    skipped_entries: list[str] = []
    skipped_ids: list[str] = []
    for line in toc_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith(";"):
            out.append(line)
            continue
        head, _, _rest = line.partition(";")
        dump_id = head.strip()
        if dump_id in corrupted:
            out.append(f";{line}")
            skipped_entries.append(line.strip())
            skipped_ids.append(dump_id)
        else:
            out.append(line)
    return PartialRestoreUseList(
        lines=tuple(out),
        skipped_entries=tuple(skipped_entries),
        skipped_ids=tuple(skipped_ids),
    )


def partial_restore_block(
    partition: PartialRestorePartition, use_list: PartialRestoreUseList
) -> dict[str, object]:
    """Build the ``partial_restore`` manifest block recording what was skipped/recovered."""
    return {
        "enabled": True,
        "skipped_data_ids": list(partition.skippable_data_ids),
        "skipped_files": list(partition.skippable_files),
        "skipped_entries": list(use_list.skipped_entries),
        "skipped_count": len(use_list.skipped_ids),
    }
