"""Pure logic for backup-manifest source blocks + ``restored_from_backup`` (T-208).

All DB-free / RustFS-free so the manifest assembly, the ``restored_from_backup``
stub plan, the two-state-machine relink transition, and the restore-entrypoint
verification matrix can be unit-tested with synthetic facts. The DB / storage
glue lives in ``infra/source_restore_service.py`` and ``infra/backup.py``; this
module only decides *what* should happen.

Follows ``docs/t109-backup-source-upload-management.md``:

* "백업/복원 manifest 확장" (lines ~1848-1886): the ``source_match_set`` manifest
  block — ``source_match_set_id``/name/profile/``source_set_hash``/
  ``yyyymm_by_category`` + per-category group with per-file metadata +
  ``omitted_optional``.
* "``restored_from_backup`` 생성 절차" (lines ~1904-1914), steps 1-9: stub
  group/file creation (``state='missing'``, ``validation_state='unknown'``,
  manifest ``group_sha256`` preserved as UNTRUSTED in ``metadata``), the
  two-state-machine relink (group/file ``missing → validating → available``;
  match set ``restored_from_backup → revalidatable → validate → validated``), and
  the M-A option 2 canonical-hash precompute before ``revalidatable``.
* "restore entrypoint별 source 검증" matrix (lines ~1896-1902): a single source
  quick reconcile after BOTH a ``pg_restore`` manifest restore and an ADR-036
  rename hot-swap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Key under ``source_file_groups.metadata`` where the manifest's group_sha256 is
# preserved as an UNTRUSTED record (step 2): it is the backup-time value, NOT the
# value re-verified against the current RustFS object.
MANIFEST_GROUP_SHA256_META_KEY = "manifest_group_sha256"

# Marks a registry row as a stub reconstructed from a backup manifest (step 2/3).
RESTORED_FROM_BACKUP_META_KEY = "restored_from_backup"


# --- manifest source_match_set block assembly (doc ~1848-1886) -------------


@dataclass(frozen=True)
class ManifestSourceFile:
    """One file entry in a manifest item (doc ~1869-1876)."""

    source_file_id: str
    filename: str
    sha256: str
    size_bytes: int
    storage_uri: str
    part_kind: str = "single"
    part_key: str = "archive"
    object_key: str | None = None
    bucket: str | None = None

    def as_manifest(self) -> dict[str, Any]:
        return {
            "source_file_id": self.source_file_id,
            "filename": self.filename,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "storage_uri": self.storage_uri,
            "part_kind": self.part_kind,
            "part_key": self.part_key,
            "object_key": self.object_key,
            "bucket": self.bucket,
        }


@dataclass(frozen=True)
class ManifestSourceItem:
    """One category group in a manifest item list (doc ~1863-1879)."""

    category: str
    source_file_group_id: str
    group_kind: str
    group_sha256: str | None
    role: str
    user_yyyymm: str | None
    effective_yyyymm: str | None
    files: tuple[ManifestSourceFile, ...]

    def as_manifest(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "source_file_group_id": self.source_file_group_id,
            "group_kind": self.group_kind,
            "group_sha256": self.group_sha256,
            "role": self.role,
            "user_yyyymm": self.user_yyyymm,
            "effective_yyyymm": self.effective_yyyymm,
            "files": [f.as_manifest() for f in self.files],
        }


@dataclass(frozen=True)
class ManifestSourceMatchSet:
    """The full ``source_match_set`` manifest block (doc ~1853-1885)."""

    source_match_set_id: str
    name: str
    profile: str
    source_set_hash: str | None
    yyyymm_by_category: dict[str, str]
    items: tuple[ManifestSourceItem, ...]
    omitted_optional: dict[str, str] = field(default_factory=dict)

    def as_manifest(self) -> dict[str, Any]:
        return {
            "source_match_set_id": self.source_match_set_id,
            "name": self.name,
            "profile": self.profile,
            "source_set_hash": self.source_set_hash,
            "yyyymm_by_category": dict(self.yyyymm_by_category),
            "items": [it.as_manifest() for it in self.items],
            "omitted_optional": dict(self.omitted_optional),
        }


def build_manifest_source_match_set_block(block: ManifestSourceMatchSet) -> dict[str, Any]:
    """Build the manifest ``source_match_set`` JSON block (records "what source
    archives reconstruct this DB" without copying the archives, doc ~1849)."""
    return block.as_manifest()


# --- restored_from_backup stub plan (doc steps 1-5, ~1906-1911) ------------


@dataclass(frozen=True)
class StubFilePlan:
    """A stub ``ops.source_files`` row the restore service will INSERT (step 3)."""

    source_file_id: str
    original_filename: str
    part_kind: str
    part_key: str
    sha256: str
    size_bytes: int
    storage_uri: str
    object_key: str | None
    bucket: str | None
    # Always ``missing`` / ``unknown`` for a fresh stub (object not yet verified).
    state: str = "missing"
    validation_state: str = "unknown"


@dataclass(frozen=True)
class StubGroupPlan:
    """A stub ``ops.source_file_groups`` row + its children (step 2/3)."""

    source_file_group_id: str
    category: str
    group_kind: str
    display_name: str
    user_yyyymm: str
    # The manifest group_sha256, preserved but NOT trusted as the current group
    # hash. Stored only in ``metadata[MANIFEST_GROUP_SHA256_META_KEY]`` (step 2);
    # the group's own ``group_sha256`` column stays NULL until recompute.
    manifest_group_sha256: str | None
    expected_part_keys: tuple[str, ...]
    files: tuple[StubFilePlan, ...]
    state: str = "missing"
    validation_state: str = "unknown"

    def metadata(self) -> dict[str, Any]:
        return {
            RESTORED_FROM_BACKUP_META_KEY: True,
            MANIFEST_GROUP_SHA256_META_KEY: self.manifest_group_sha256,
            "expected_part_keys": list(self.expected_part_keys),
        }


@dataclass(frozen=True)
class StubItemPlan:
    """A stub ``ops.source_match_set_items`` row referencing a stub group (step 4)."""

    category: str
    role: str
    source_file_group_id: str | None
    omitted: bool
    omitted_reason: str | None
    effective_yyyymm: str | None
    required: bool


@dataclass(frozen=True)
class RestoredMatchSetPlan:
    """The full ``restored_from_backup`` reconstruction plan (steps 2-5).

    The service applies this in ONE transaction: stub groups + files, the items
    referencing them, then the ``source_match_sets`` row at
    ``state='restored_from_backup'``. ``source_set_hash`` may be NULL when the
    legacy manifest carried none (CHECK allows NULL here, doc line ~758/1910).
    Rebuild stays disabled until relink completes (step 6).
    """

    source_match_set_id: str
    name: str
    profile: str
    source_set_hash: str | None
    yyyymm_by_category: dict[str, str]
    omitted_optional: dict[str, str]
    groups: tuple[StubGroupPlan, ...]
    items: tuple[StubItemPlan, ...]
    state: str = "restored_from_backup"


def plan_restored_from_backup(
    block: ManifestSourceMatchSet,
    *,
    new_match_set_id: str,
    group_id_for: dict[str, str],
    file_id_for: dict[str, str],
    name_suffix: str = " (복원됨)",
) -> RestoredMatchSetPlan:
    """Turn a manifest ``source_match_set`` block into a stub creation plan.

    ``group_id_for`` / ``file_id_for`` map the manifest's original ids to FRESH
    uuids (the restore creates new rows; it never re-uses the old ids, which may
    collide with surviving registry rows). For a non-omitted item missing from
    ``group_id_for`` the manifest's own id is reused as a fallback.

    Stub groups/files are ``state='missing'``, ``validation_state='unknown'``
    (step 2/3). The manifest ``group_sha256`` is preserved in the group plan's
    ``metadata`` (untrusted); the group's own hash column stays NULL until a
    relink recomputes it. ``omitted_optional`` restores ``omitted=true`` items.
    """
    groups: list[StubGroupPlan] = []
    items: list[StubItemPlan] = []

    for it in block.items:
        new_gid = group_id_for.get(it.source_file_group_id, it.source_file_group_id)
        files: list[StubFilePlan] = []
        for f in it.files:
            new_fid = file_id_for.get(f.source_file_id, f.source_file_id)
            files.append(
                StubFilePlan(
                    source_file_id=new_fid,
                    original_filename=f.filename,
                    part_kind=f.part_kind,
                    part_key=f.part_key,
                    sha256=f.sha256,
                    size_bytes=f.size_bytes,
                    storage_uri=f.storage_uri,
                    object_key=f.object_key,
                    bucket=f.bucket,
                )
            )
        expected_part_keys = tuple(f.part_key for f in files) or ("archive",)
        groups.append(
            StubGroupPlan(
                source_file_group_id=new_gid,
                category=it.category,
                group_kind=it.group_kind,
                display_name=f"{block.name}:{it.category}{name_suffix}",
                user_yyyymm=(
                    it.user_yyyymm
                    or block.yyyymm_by_category.get(it.category)
                    or "000000"
                ),
                manifest_group_sha256=it.group_sha256,
                expected_part_keys=expected_part_keys,
                files=tuple(files),
            )
        )
        items.append(
            StubItemPlan(
                category=it.category,
                role=it.role,
                source_file_group_id=new_gid,
                omitted=False,
                omitted_reason=None,
                effective_yyyymm=it.effective_yyyymm,
                required=it.role in {"build_required", "build_recommended"},
            )
        )

    # omitted_optional categories restore as omitted=true items (step 4).
    for category, reason in block.omitted_optional.items():
        items.append(
            StubItemPlan(
                category=category,
                role="validation_optional",
                source_file_group_id=None,
                omitted=True,
                omitted_reason=reason,
                effective_yyyymm=None,
                required=False,
            )
        )

    return RestoredMatchSetPlan(
        source_match_set_id=new_match_set_id,
        name=f"{block.name}{name_suffix}",
        profile=block.profile,
        source_set_hash=block.source_set_hash,
        yyyymm_by_category=dict(block.yyyymm_by_category),
        omitted_optional=dict(block.omitted_optional),
        groups=tuple(groups),
        items=tuple(items),
    )


# --- relink transition (two state machines, doc steps 7-9) -----------------

RelinkChildState = Literal["available", "validating", "missing", "quarantined"]


@dataclass(frozen=True)
class RelinkObjectCheck:
    """Result of a RustFS ``head_object`` (+ rehash) for one stub child (step 7)."""

    object_present: bool
    # Streaming-rehash result (None when not re-read). The relink compares this
    # to the MANIFEST sha256 the stub stored — the manifest value is the trust
    # boundary, never the head ETag.
    observed_sha256: str | None = None
    observed_size: int | None = None


@dataclass(frozen=True)
class RelinkChildDecision:
    """Where a ``missing`` stub child lands after object verification (step 7/8).

    A consistent present object goes to ``validating`` (NOT straight to
    ``available``: the ``unknown`` stub can only reach ``available`` after the
    structure validator records ``passed``/``warning`` — step 8). Absent →
    ``missing``; manifest-hash/size mismatch → ``quarantined`` (step 7).
    """

    new_state: RelinkChildState
    validation_state: str
    observed_sha256: str | None
    observed_size: int | None
    reasons: tuple[str, ...] = field(default_factory=tuple)


def decide_relink_child(
    *,
    manifest_sha256: str,
    manifest_size: int | None,
    check: RelinkObjectCheck,
) -> RelinkChildDecision:
    """Decide a stub child's relink landing state (doc step 7-8).

    * object absent → ``missing`` (cannot reattach);
    * present + rehash != manifest hash → ``quarantined`` (manifest hash is the
      trust boundary, doc step 7);
    * present + size != manifest size → ``quarantined``;
    * present + consistent (or not rehashed) → ``validating`` (the structure
      validator then promotes it to ``available`` — step 8). The rehash result is
      surfaced so the service can persist it as the child's NEW current sha256.
    """
    if not check.object_present:
        return RelinkChildDecision(
            new_state="missing",
            validation_state="unknown",
            observed_sha256=None,
            observed_size=None,
            reasons=("RustFS object를 찾을 수 없습니다",),
        )
    if check.observed_sha256 is not None and check.observed_sha256 != manifest_sha256:
        return RelinkChildDecision(
            new_state="quarantined",
            validation_state="failed",
            observed_sha256=check.observed_sha256,
            observed_size=check.observed_size,
            reasons=("재계산 SHA-256이 manifest 값과 다릅니다",),
        )
    if (
        check.observed_size is not None
        and manifest_size is not None
        and check.observed_size != manifest_size
    ):
        return RelinkChildDecision(
            new_state="quarantined",
            validation_state="failed",
            observed_sha256=check.observed_sha256,
            observed_size=check.observed_size,
            reasons=("재계산 size가 manifest 값과 다릅니다",),
        )
    return RelinkChildDecision(
        new_state="validating",
        validation_state="running",
        observed_sha256=check.observed_sha256,
        observed_size=check.observed_size,
        reasons=(),
    )


# --- restore entrypoint source verification matrix (doc ~1896-1902) --------

RestoreEntrypoint = Literal["pg_restore", "rename_hot_swap"]


@dataclass(frozen=True)
class RestoreSourceVerificationPlan:
    """What source verification a restore entrypoint must run (doc ~1896-1902).

    BOTH entrypoints run exactly ONE source quick reconcile after the restore
    finalizes (pg_restore manifest restore) or the rename/smoke completes
    (ADR-036 hot-swap). ``has_active_match_set`` is False for a legacy snapshot
    with no ``source_match_set_id`` FK — then only a legacy ``source_set``
    estimate is shown (no reconcile target), doc line ~1901.
    """

    entrypoint: RestoreEntrypoint
    run_quick_reconcile: bool
    reconcile_mode: str
    has_active_match_set: bool
    legacy_estimate_only: bool
    reason: str = ""


def plan_restore_source_verification(
    *,
    entrypoint: RestoreEntrypoint,
    active_source_match_set_id: str | None,
) -> RestoreSourceVerificationPlan:
    """Decide the source verification for a restore entrypoint (doc matrix).

    Both ``pg_restore`` and ``rename_hot_swap`` run ONE ``quick`` reconcile when
    the active snapshot carries a ``source_match_set_id``; otherwise (legacy
    snapshot) no reconcile target exists and only a legacy estimate is surfaced.
    """
    has_active = active_source_match_set_id is not None
    return RestoreSourceVerificationPlan(
        entrypoint=entrypoint,
        run_quick_reconcile=has_active,
        reconcile_mode="quick",
        has_active_match_set=has_active,
        legacy_estimate_only=not has_active,
        reason=(
            "active snapshot source_match_set_id로 quick reconcile"
            if has_active
            else "legacy snapshot: source_set 추정만 표시"
        ),
    )
