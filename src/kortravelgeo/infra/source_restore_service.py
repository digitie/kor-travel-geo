"""Backup-manifest source block + ``restored_from_backup`` DB/RustFS glue (T-208).

DB + RustFS glue around the pure logic in ``core.source_restore``. Covers:

* :func:`read_active_match_set_block` — read the active snapshot's
  ``source_match_set_id`` → match set + items + groups + files and assemble the
  manifest ``source_match_set`` block ``infra/backup.py`` embeds (doc ~1848-1886).
* :func:`create_restored_from_backup` — given a backup manifest's
  ``source_match_set`` block, in ONE transaction create stub
  ``ops.source_file_groups`` / ``ops.source_files`` (``state='missing'``,
  ``validation_state='unknown'``, manifest hash preserved as untrusted metadata),
  the ``source_match_set_items`` referencing them, and a ``source_match_sets`` row
  at ``state='restored_from_backup'`` (doc steps 1-6, ~1906-1911).
* :func:`relink_restored_group` — reattach a stub group's objects: each child
  ``missing → validating``/``missing``/``quarantined`` (manifest hash is the trust
  boundary), then ``recompute_group_aggregates`` recomputes ``group_sha256`` and
  drives the match-set up-propagation (``restored_from_backup → revalidatable``
  with the canonical hash precomputed first — M-A option 2, doc steps 7-9).
* :func:`verify_restore_source` — the restore-entrypoint verification matrix:
  after a ``pg_restore`` manifest restore OR an ADR-036 rename hot-swap, run ONE
  source quick reconcile against the active snapshot's ``source_match_set_id`` and
  surface a "재구성 불가" warning if source objects are missing (doc ~1896-1902).

The pure assembly / stub plan / relink transition / verification matrix live in
``core.source_restore`` so they are unit-tested without a DB or RustFS; this
module reads rows, calls those functions, and writes results back.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_events import (
    SOURCE_RESTORE_SOURCE_VERIFY,
    SOURCE_RESTORED_FROM_BACKUP_CREATE,
    SOURCE_RESTORED_FROM_BACKUP_RELINK,
)
from kortravelgeo.core.source_restore import (
    ManifestSourceDbFileFact,
    ManifestSourceFile,
    ManifestSourceFileReconcileDecision,
    ManifestSourceHeadFact,
    ManifestSourceItem,
    ManifestSourceMatchSet,
    RelinkObjectCheck,
    RestoreEntrypoint,
    RestoreSourceVerificationPlan,
    decide_manifest_source_file_reconcile,
    decide_relink_child,
    plan_restore_source_verification,
    plan_restored_from_backup,
)
from kortravelgeo.dto.source import (
    RestoredFromBackupCreateResponse,
    RestoreSourceVerificationResult,
    SourceGroupRelinkFile,
    SourceGroupRelinkResponse,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.infra.rustfs import RustfsClient
from kortravelgeo.infra.source_audit import insert_source_audit_event
from kortravelgeo.infra.source_group_service import recompute_group_aggregates


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


# --- read active match set → manifest block (doc ~1848-1886) ---------------


async def read_active_match_set_block(
    engine: AsyncEngine,
) -> ManifestSourceMatchSet | None:
    """Assemble the backup-manifest ``source_match_set`` block, or ``None``.

    Reads the ACTIVE ``ops.source_match_sets`` row + its items + each item's group
    + the group's non-deleted files, and builds the manifest block recording "what
    source archives reconstruct this DB" (no archive copy, doc line ~1849).
    Returns ``None`` when there is no active match set (a legacy / fresh DB — the
    manifest then keeps only the legacy ``source_set`` estimate).
    """
    async with engine.connect() as conn:
        ms = (
            await conn.execute(
                text(
                    """
SELECT source_match_set_id, name, profile, source_set_hash,
       yyyymm_by_category, omitted_optional
  FROM ops.source_match_sets
 WHERE state = 'active'
 LIMIT 1
"""
                )
            )
        ).mappings().first()
        if ms is None:
            return None
        match_set_id = str(ms["source_match_set_id"])
        item_rows = (
            await conn.execute(
                text(
                    """
SELECT it.category, it.role, it.source_file_group_id, it.omitted,
       it.effective_yyyymm, g.group_kind, g.group_sha256, g.user_yyyymm
  FROM ops.source_match_set_items it
  LEFT JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id
 ORDER BY it.load_order NULLS LAST, it.category
"""
                ),
                {"id": match_set_id},
            )
        ).mappings().all()

        items: list[ManifestSourceItem] = []
        omitted_optional: dict[str, str] = dict(ms["omitted_optional"] or {})
        for r in item_rows:
            if bool(r["omitted"]):
                omitted_optional.setdefault(
                    str(r["category"]), "match set에서 생략됨"
                )
                continue
            gid = r["source_file_group_id"]
            if gid is None:
                continue
            files = await _group_manifest_files(conn, str(gid))
            items.append(
                ManifestSourceItem(
                    category=str(r["category"]),
                    source_file_group_id=str(gid),
                    group_kind=str(r["group_kind"] or "single_file"),
                    group_sha256=r["group_sha256"],
                    role=str(r["role"]),
                    user_yyyymm=r["user_yyyymm"],
                    effective_yyyymm=r["effective_yyyymm"],
                    files=files,
                )
            )

    return ManifestSourceMatchSet(
        source_match_set_id=match_set_id,
        name=str(ms["name"]),
        profile=str(ms["profile"]),
        source_set_hash=ms["source_set_hash"],
        yyyymm_by_category=dict(ms["yyyymm_by_category"] or {}),
        items=tuple(items),
        omitted_optional=omitted_optional,
    )


async def _group_manifest_files(
    conn: AsyncConnection, group_id: str
) -> tuple[ManifestSourceFile, ...]:
    rows = (
        await conn.execute(
            text(
                """
SELECT source_file_id, original_filename, part_kind, part_key, sha256,
       size_bytes, storage_uri, object_key, bucket, object_etag
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted', 'soft_deleted')
 ORDER BY part_key
"""
            ),
            {"gid": group_id},
        )
    ).mappings().all()
    return tuple(
        ManifestSourceFile(
            source_file_id=str(r["source_file_id"]),
            filename=str(r["original_filename"]),
            sha256=str(r["sha256"]),
            size_bytes=int(r["size_bytes"]),
            storage_uri=str(r["storage_uri"]),
            part_kind=str(r["part_kind"]),
            part_key=str(r["part_key"]),
            object_key=r["object_key"],
            bucket=r["bucket"],
            object_etag=r["object_etag"],
        )
        for r in rows
    )


def parse_manifest_source_match_set(
    block: Mapping[str, Any],
) -> ManifestSourceMatchSet:
    """Parse a manifest ``source_match_set`` JSON block back into the dataclass.

    Tolerant of legacy / partial blocks: missing per-file fields default; a
    missing ``source_set_hash`` stays ``None`` (legacy manifest, doc line ~1910).
    """
    items: list[ManifestSourceItem] = []
    for it in block.get("items", []) or []:
        files = tuple(
            ManifestSourceFile(
                source_file_id=str(f.get("source_file_id") or uuid4()),
                filename=str(f.get("filename") or "archive"),
                sha256=str(f.get("sha256") or ""),
                size_bytes=int(f.get("size_bytes") or 0),
                storage_uri=str(f.get("storage_uri") or ""),
                part_kind=str(f.get("part_kind") or "single"),
                part_key=str(f.get("part_key") or "archive"),
                object_key=f.get("object_key"),
                bucket=f.get("bucket"),
                object_etag=f.get("object_etag"),
            )
            for f in (it.get("files") or [])
        )
        items.append(
            ManifestSourceItem(
                category=str(it["category"]),
                source_file_group_id=str(it.get("source_file_group_id") or uuid4()),
                group_kind=str(it.get("group_kind") or "single_file"),
                group_sha256=it.get("group_sha256"),
                role=str(it.get("role") or "build_required"),
                user_yyyymm=it.get("user_yyyymm"),
                effective_yyyymm=it.get("effective_yyyymm"),
                files=files,
            )
        )
    return ManifestSourceMatchSet(
        source_match_set_id=str(block.get("source_match_set_id") or uuid4()),
        name=str(block.get("name") or "restored match set"),
        profile=str(block.get("profile") or "custom"),
        source_set_hash=block.get("source_set_hash"),
        yyyymm_by_category=dict(block.get("yyyymm_by_category") or {}),
        items=tuple(items),
        omitted_optional=dict(block.get("omitted_optional") or {}),
    )


# --- manifest ↔ DB ↔ RustFS reconcile (T-238) -----------------------------


@dataclass(frozen=True)
class ManifestSourceReconcileRow:
    """One T-238 manifest per-file reconcile row."""

    category: str
    source_file_id: str
    filename: str
    part_key: str
    object_key: str | None
    decision: ManifestSourceFileReconcileDecision


@dataclass(frozen=True)
class ManifestSourceReconcileReport:
    """Opt-in backup manifest/source inventory reconcile report."""

    artifact_schema_version: int | None
    source_match_set_id: str | None
    skipped: bool
    reason: str | None
    total: int
    counts: dict[str, int]
    ok: bool
    rows: tuple[ManifestSourceReconcileRow, ...]


def manifest_source_reconcile_report_to_dict(
    report: ManifestSourceReconcileReport,
) -> dict[str, Any]:
    return {
        "artifact_schema_version": report.artifact_schema_version,
        "source_match_set_id": report.source_match_set_id,
        "skipped": report.skipped,
        "reason": report.reason,
        "total": report.total,
        "counts": dict(report.counts),
        "ok": report.ok,
        "rows": [
            {
                "category": row.category,
                "source_file_id": row.source_file_id,
                "filename": row.filename,
                "part_key": row.part_key,
                "object_key": row.object_key,
                "status": row.decision.status,
                "db_status": row.decision.db_status,
                "expected_object_key": row.decision.expected_object_key,
                "observed_object_key": row.decision.observed_object_key,
                "expected_size_bytes": row.decision.expected_size_bytes,
                "observed_size_bytes": row.decision.observed_size_bytes,
                "expected_etag": row.decision.expected_etag,
                "observed_etag": row.decision.observed_etag,
                "reasons": list(row.decision.reasons),
            }
            for row in report.rows
        ],
    }


async def reconcile_manifest_source_inventory(
    engine: AsyncEngine,
    manifest: Mapping[str, Any],
    *,
    rustfs: RustfsClient | None,
    actor: str | None = None,
) -> ManifestSourceReconcileReport:
    """Compare backup manifest ``source_match_set`` files with DB and RustFS HEAD.

    This is the T-238 opt-in check. Legacy manifests and RustFS-disabled
    environments degrade to a skipped report instead of failing restore/backup
    flows.
    """
    artifact_schema_version = _int_or_none(manifest.get("artifact_schema_version"))
    block_json = manifest.get("source_match_set")
    if not isinstance(block_json, Mapping):
        return ManifestSourceReconcileReport(
            artifact_schema_version=artifact_schema_version,
            source_match_set_id=None,
            skipped=True,
            reason="legacy_manifest_no_source_match_set",
            total=0,
            counts={},
            ok=True,
            rows=(),
        )
    block = parse_manifest_source_match_set(block_json)
    files = tuple((item.category, file) for item in block.items for file in item.files)
    if rustfs is None:
        return ManifestSourceReconcileReport(
            artifact_schema_version=artifact_schema_version,
            source_match_set_id=block.source_match_set_id,
            skipped=True,
            reason="rustfs_unavailable",
            total=len(files),
            counts={},
            ok=True,
            rows=(),
        )

    db_facts = await _manifest_source_db_facts(engine, tuple(file for _, file in files))
    rows: list[ManifestSourceReconcileRow] = []
    for category, file in files:
        head = await _head_manifest_file(rustfs, file)
        db = db_facts.get(file.source_file_id)
        if db is None and file.object_key:
            db = db_facts.get(f"object_key:{file.object_key}")
        decision = decide_manifest_source_file_reconcile(
            file,
            db=db,
            head=head,
        )
        rows.append(
            ManifestSourceReconcileRow(
                category=category,
                source_file_id=file.source_file_id,
                filename=file.filename,
                part_key=file.part_key,
                object_key=file.object_key,
                decision=decision,
            )
        )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row.decision.status] = counts.get(row.decision.status, 0) + 1
    ok = not any(status != "present" for status in counts)
    report = ManifestSourceReconcileReport(
        artifact_schema_version=artifact_schema_version,
        source_match_set_id=block.source_match_set_id,
        skipped=False,
        reason=None,
        total=len(rows),
        counts=counts,
        ok=ok,
        rows=tuple(rows),
    )
    if actor is not None:
        async with engine.begin() as conn:
            await _audit(
                conn,
                action=SOURCE_RESTORE_SOURCE_VERIFY,
                actor=actor,
                resource_id=block.source_match_set_id,
                outcome="verified" if ok else "mismatch",
                payload={
                    "mode": "manifest_source_reconcile",
                    "total": report.total,
                    "counts": report.counts,
                    "ok": report.ok,
                },
            )
    return report


async def _manifest_source_db_facts(
    engine: AsyncEngine,
    files: tuple[ManifestSourceFile, ...],
) -> dict[str, ManifestSourceDbFileFact]:
    ids = tuple({f.source_file_id for f in files if f.source_file_id})
    keys = tuple({f.object_key for f in files if f.object_key})
    if not ids and not keys:
        return {}
    clauses: list[str] = []
    params: dict[str, object] = {}
    bindparams: list[Any] = []
    if ids:
        clauses.append("source_file_id::text IN :ids")
        params["ids"] = ids
        bindparams.append(bindparam("ids", expanding=True))
    if keys:
        clauses.append("object_key IN :keys")
        params["keys"] = keys
        bindparams.append(bindparam("keys", expanding=True))
    sql = f"""
SELECT source_file_id::text AS source_file_id, object_key, sha256,
       size_bytes, object_etag
  FROM ops.source_files
 WHERE {" OR ".join(clauses)}
"""
    stmt = text(sql).bindparams(*bindparams)
    facts: dict[str, ManifestSourceDbFileFact] = {}
    async with engine.connect() as conn:
        rows = (await conn.execute(stmt, params)).mappings().all()
    for row in rows:
        fact = ManifestSourceDbFileFact(
            source_file_id=str(row["source_file_id"]),
            object_key=row["object_key"],
            sha256=row["sha256"],
            size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
            object_etag=row["object_etag"],
        )
        facts[fact.source_file_id] = fact
        if fact.object_key:
            facts.setdefault(f"object_key:{fact.object_key}", fact)
    return facts


async def _head_manifest_file(
    rustfs: RustfsClient,
    file: ManifestSourceFile,
) -> ManifestSourceHeadFact | None:
    if not file.object_key:
        return None
    try:
        head = await rustfs.head_object(file.object_key)
    except Exception:
        return ManifestSourceHeadFact(present=False)
    return ManifestSourceHeadFact(
        present=True,
        size=head.size,
        etag=head.etag,
    )


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


# --- create restored_from_backup (doc steps 1-6, ~1906-1911) ---------------


async def create_restored_from_backup(
    engine: AsyncEngine,
    block: ManifestSourceMatchSet,
    *,
    actor: str | None,
) -> RestoredFromBackupCreateResponse:
    """Create a ``restored_from_backup`` stub match set in ONE transaction.

    Per doc steps 2-5: stub groups (``state='missing'``,
    ``validation_state='unknown'``, manifest ``group_sha256`` preserved in
    ``metadata`` and the group's own hash column NULL), stub files
    (``missing``/``unknown``, manifest sha256/size/storage_uri), items referencing
    the stubs (``omitted_optional`` restored as ``omitted=true``), and the match
    set at ``state='restored_from_backup'`` (``source_set_hash`` may be NULL for a
    legacy manifest). Rebuild stays disabled until relink (step 6).
    """
    group_id_for = {it.source_file_group_id: str(uuid4()) for it in block.items}
    file_id_for = {
        f.source_file_id: str(uuid4()) for it in block.items for f in it.files
    }
    plan = plan_restored_from_backup(
        block,
        new_match_set_id=str(uuid4()),
        group_id_for=group_id_for,
        file_id_for=file_id_for,
    )

    created_file_count = 0
    async with engine.begin() as conn:
        # Match set first (items FK it).
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.source_match_sets
  (source_match_set_id, name, description, profile, state, source_set_hash,
   yyyymm_by_category, omitted_optional, created_by, metadata)
VALUES
  (:id, :name, :description, :profile, 'restored_from_backup', :hash,
   :by_cat, :omitted, :created_by, :metadata)
""",
                "by_cat",
                "omitted",
                "metadata",
            ),
            {
                "id": plan.source_match_set_id,
                "name": plan.name,
                "description": "백업 manifest에서 재구성된 read-only match set",
                "profile": plan.profile,
                "hash": plan.source_set_hash,
                "by_cat": plan.yyyymm_by_category,
                "omitted": plan.omitted_optional,
                "created_by": actor,
                "metadata": {
                    "restored_from_backup": True,
                    "manifest_source_match_set_id": block.source_match_set_id,
                    "rebuild_enabled": False,
                },
            },
        )

        for grp in plan.groups:
            await conn.execute(
                _json_text(
                    """
INSERT INTO ops.source_file_groups
  (source_file_group_id, category, group_kind, display_name, state,
   validation_state, user_yyyymm, expected_file_count, actual_file_count,
   group_sha256, uploaded_by, metadata)
VALUES
  (:gid, :category, :group_kind, :display_name, :state, :vstate, :user_yyyymm,
   :expected, 0, NULL, :uploaded_by, :metadata)
""",
                    "metadata",
                ),
                {
                    "gid": grp.source_file_group_id,
                    "category": grp.category,
                    "group_kind": grp.group_kind,
                    "display_name": grp.display_name,
                    "state": grp.state,
                    "vstate": grp.validation_state,
                    "user_yyyymm": grp.user_yyyymm,
                    "expected": max(1, len(grp.expected_part_keys)),
                    "uploaded_by": actor,
                    "metadata": grp.metadata(),
                },
            )
            for f in grp.files:
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.source_files
  (source_file_id, source_file_group_id, original_filename, part_kind, part_key,
   compression_format, state, validation_state, size_bytes, sha256,
   storage_kind, storage_uri, bucket, object_key, uploaded_by, metadata)
VALUES
  (:fid, :gid, :filename, :part_kind, :part_key, :compression, :state, :vstate,
   :size, :sha256, :storage_kind, :storage_uri, :bucket, :object_key,
   :uploaded_by, :metadata)
""",
                        "metadata",
                    ),
                    {
                        "fid": f.source_file_id,
                        "gid": grp.source_file_group_id,
                        "filename": f.original_filename,
                        "part_kind": f.part_kind,
                        "part_key": f.part_key,
                        "compression": "zip",
                        "state": f.state,
                        "vstate": f.validation_state,
                        "size": f.size_bytes,
                        "sha256": f.sha256 or ("0" * 64),
                        "storage_kind": "rustfs",
                        "storage_uri": f.storage_uri or f"rustfs://restored/{f.part_key}",
                        "bucket": f.bucket,
                        "object_key": f.object_key,
                        "uploaded_by": actor,
                        "metadata": {"restored_from_backup": True},
                    },
                )
                created_file_count += 1

        for item in plan.items:
            await conn.execute(
                _json_text(
                    """
INSERT INTO ops.source_match_set_items
  (source_match_set_item_id, source_match_set_id, category, role,
   source_file_group_id, required, omitted, omitted_reason, effective_yyyymm,
   validation_enabled, metadata)
VALUES
  (:id, :msid, :category, :role, :gid, :required, :omitted, :omitted_reason,
   :effective_yyyymm, :validation_enabled, '{}'::jsonb)
""",
                ),
                {
                    "id": str(uuid4()),
                    "msid": plan.source_match_set_id,
                    "category": item.category,
                    "role": item.role,
                    "gid": item.source_file_group_id,
                    "required": item.required,
                    "omitted": item.omitted,
                    "omitted_reason": item.omitted_reason,
                    "effective_yyyymm": item.effective_yyyymm,
                    "validation_enabled": not item.omitted,
                },
            )

        await _audit(
            conn,
            action=SOURCE_RESTORED_FROM_BACKUP_CREATE,
            actor=actor,
            resource_id=plan.source_match_set_id,
            outcome="restored_from_backup",
            payload={
                "manifest_source_match_set_id": block.source_match_set_id,
                "group_count": len(plan.groups),
                "file_count": created_file_count,
                "omitted_categories": list(plan.omitted_optional),
            },
        )

    return RestoredFromBackupCreateResponse(
        source_match_set_id=plan.source_match_set_id,
        state="restored_from_backup",
        profile=plan.profile,
        source_set_hash=plan.source_set_hash,
        created_group_ids=tuple(g.source_file_group_id for g in plan.groups),
        created_file_count=created_file_count,
        omitted_categories=tuple(plan.omitted_optional),
        rebuild_enabled=False,
        message=(
            "복원된 match set은 모든 group을 relink해 available로 만들기 전까지 "
            "rebuild할 수 없습니다"
        ),
    )


# --- relink stub group → available (doc steps 7-9) -------------------------


@dataclass(frozen=True)
class RelinkChildVerification:
    """A head/rehash-verified stub child the caller passes to :func:`relink_restored_group`."""

    source_file_id: str
    part_key: str
    object_present: bool
    observed_sha256: str | None = None
    observed_size: int | None = None


async def relink_restored_group(
    engine: AsyncEngine,
    source_file_group_id: str,
    *,
    verifications: tuple[RelinkChildVerification, ...],
    actor: str | None,
) -> SourceGroupRelinkResponse:
    """Relink a ``restored_from_backup`` stub group's objects (doc steps 7-9).

    The caller (client layer) has run RustFS ``head_object`` + a streaming rehash
    per child and passes the observations. Each child transitions
    ``missing → validating`` (object present + manifest-hash/size consistent → the
    recomputed sha256/size become the child's NEW current values),
    ``missing`` (absent), or ``quarantined`` (manifest-hash/size mismatch — the
    manifest value is the trust boundary). ``recompute_group_aggregates`` then
    recomputes ``group_sha256`` and drives the match-set up-propagation: when every
    referenced group is ``available`` it precomputes the canonical
    ``source_set_hash`` FIRST then ``restored_from_backup → revalidatable`` (M-A
    option 2). Direct active promotion is forbidden (a separate ``activate``).
    """
    by_file = {v.source_file_id: v for v in verifications}
    async with engine.begin() as conn:
        group_row = (
            await conn.execute(
                text(
                    """
SELECT category, group_kind, state, metadata
  FROM ops.source_file_groups
 WHERE source_file_group_id = :gid FOR UPDATE
"""
                ),
                {"gid": source_file_group_id},
            )
        ).mappings().first()
        if group_row is None:
            raise NotFoundError(f"source file group not found: {source_file_group_id}")
        meta = dict(group_row.get("metadata") or {})
        if not meta.get("restored_from_backup"):
            raise InvalidInputError(
                "relink은 restored_from_backup stub group만 대상으로 합니다"
            )

        child_rows = (
            await conn.execute(
                text(
                    """
SELECT source_file_id, part_key, sha256, size_bytes
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted', 'soft_deleted')
"""
                ),
                {"gid": source_file_group_id},
            )
        ).mappings().all()

        results: list[SourceGroupRelinkFile] = []
        all_consistent = bool(child_rows)
        for row in child_rows:
            fid = str(row["source_file_id"])
            v = by_file.get(fid)
            check = (
                RelinkObjectCheck(
                    object_present=v.object_present,
                    observed_sha256=v.observed_sha256,
                    observed_size=v.observed_size,
                )
                if v is not None
                else RelinkObjectCheck(object_present=False)
            )
            # The manifest sha256/size are the stub's stored sha256/size_bytes
            # (preserved from the manifest at create time, step 3 — untrusted).
            decision = decide_relink_child(
                manifest_sha256=str(row["sha256"]),
                manifest_size=int(row["size_bytes"]),
                check=check,
            )
            if decision.new_state != "validating":
                all_consistent = False
            # On a consistent present object the recomputed sha256/size become the
            # child's NEW current values (step 7); else keep the manifest values.
            new_sha = decision.observed_sha256 or str(row["sha256"])
            new_size = (
                decision.observed_size
                if decision.observed_size is not None
                else int(row["size_bytes"])
            )
            await conn.execute(
                text(
                    """
UPDATE ops.source_files
   SET state = :state, validation_state = :vstate, sha256 = :sha,
       size_bytes = :size, last_deep_verified_at = now()
 WHERE source_file_id = :fid
"""
                ),
                {
                    "fid": fid,
                    "state": decision.new_state,
                    "vstate": decision.validation_state,
                    "sha": new_sha,
                    "size": new_size,
                },
            )
            results.append(
                SourceGroupRelinkFile(
                    source_file_id=fid,
                    part_key=str(row["part_key"]),
                    state=decision.new_state,
                    reasons=decision.reasons,
                )
            )

        # Step 8: only when every child is consistent (present + manifest-hash ok)
        # does the structure validator record passed and the group reach available.
        # A real structure validator runs out-of-band; the relink uses the manifest
        # hash consistency as the gate (objects matching the backup are structurally
        # the same archives that were validated pre-backup).
        if all_consistent:
            structure_state = "passed"
            await conn.execute(
                text(
                    """
UPDATE ops.source_files
   SET state = 'available', validation_state = 'passed', validated_at = now()
 WHERE source_file_group_id = :gid AND state = 'validating'
"""
                ),
                {"gid": source_file_group_id},
            )
        else:
            structure_state = "unknown"

        recompute = await recompute_group_aggregates(
            conn,
            source_file_group_id,
            trigger="restored_from_backup_relink",
            structure_validation_state=structure_state,
        )
        await _audit(
            conn,
            action=SOURCE_RESTORED_FROM_BACKUP_RELINK,
            actor=actor,
            resource_id=source_file_group_id,
            outcome=recompute.state,
            payload={
                "files": [
                    {"source_file_id": r.source_file_id, "state": r.state}
                    for r in results
                ],
                "affected_match_set_ids": list(recompute.affected_match_set_ids),
            },
        )

    return SourceGroupRelinkResponse(
        source_file_group_id=source_file_group_id,
        category=str(group_row["category"]),
        state=recompute.state,
        validation_state=recompute.validation_state,
        group_sha256=recompute.group_sha256,
        files=tuple(results),
        affected_match_set_ids=recompute.affected_match_set_ids,
    )


# --- restore entrypoint source verification matrix (doc ~1896-1902) --------


async def active_source_match_set_id(engine: AsyncEngine) -> str | None:
    """The active snapshot's ``source_match_set_id`` (the reconcile target)."""
    async with engine.connect() as conn:
        return await _active_source_match_set_id_conn(conn)


async def _active_source_match_set_id_conn(conn: AsyncConnection) -> str | None:
    value = await conn.scalar(
        text(
            """
SELECT s.source_match_set_id::text
  FROM ops.serving_releases r
  JOIN ops.dataset_snapshots s ON s.dataset_snapshot_id = r.dataset_snapshot_id
 WHERE r.state = 'active' AND s.source_match_set_id IS NOT NULL
 ORDER BY r.activated_at DESC NULLS LAST, r.created_at DESC
 LIMIT 1
"""
        )
    )
    if value is not None:
        return str(value)
    # Fall back to the live active match set (a rebuild may set it before the
    # release row flips to active).
    value = await conn.scalar(
        text(
            "SELECT source_match_set_id::text FROM ops.source_match_sets "
            "WHERE state = 'active' LIMIT 1"
        )
    )
    return str(value) if value is not None else None


async def verify_restore_source(
    engine: AsyncEngine,
    *,
    entrypoint: RestoreEntrypoint,
    rustfs: RustfsClient | None,
    actor: str | None,
    rolling_deep_days: int = 30,
    object_limit: int = 50_000,
) -> RestoreSourceVerificationResult:
    """Run the post-restore source verification matrix (doc ~1896-1902).

    After a ``pg_restore`` manifest restore OR an ADR-036 rename hot-swap, resolve
    the active snapshot's ``source_match_set_id`` and — when present and RustFS is
    available — run ONE source ``quick`` reconcile to surface
    ``source_file_unavailable`` / object availability. A legacy snapshot (no FK)
    skips the reconcile and only flags the legacy estimate. When source objects are
    missing, serving stays up but ``reconstruct_unavailable`` is set and a
    "재구성 불가" warning is surfaced (the active match set's ``integrity_alert`` is
    set inside ``run_source_reconcile`` via ``recompute_group_aggregates``).
    """
    match_set_id = await active_source_match_set_id(engine)
    plan: RestoreSourceVerificationPlan = plan_restore_source_verification(
        entrypoint=entrypoint,
        active_source_match_set_id=match_set_id,
    )

    run_id: str | None = None
    mismatch_count = 0
    reconstruct_unavailable = False

    if plan.run_quick_reconcile and rustfs is not None:
        # Import here to avoid a hard infra→infra cycle at module load.
        from kortravelgeo.infra.source_reconcile import run_source_reconcile

        prefix = await _match_set_object_prefix(engine, match_set_id)
        result = await run_source_reconcile(
            engine,
            rustfs=rustfs,
            prefix=prefix,
            mode=plan.reconcile_mode,
            actor=actor,
            rolling_deep_days=rolling_deep_days,
            object_limit=object_limit,
        )
        run_id = result.source_storage_reconcile_run_id
        mismatch_count = result.mismatch_count
        unavailable = result.issue_counts.get("source_file_unavailable", 0)
        unavailable += result.issue_counts.get("db_missing_object", 0)
        reconstruct_unavailable = unavailable > 0 or result.mass_loss

    async with engine.begin() as conn:
        await _audit(
            conn,
            action=SOURCE_RESTORE_SOURCE_VERIFY,
            actor=actor,
            resource_id=match_set_id or entrypoint,
            outcome="reconstruct_unavailable" if reconstruct_unavailable else "verified",
            resource_type="source_match_set" if match_set_id else "database",
            payload={
                "entrypoint": entrypoint,
                "run_quick_reconcile": plan.run_quick_reconcile,
                "legacy_estimate_only": plan.legacy_estimate_only,
                "active_source_match_set_id": match_set_id,
                "reconcile_run_id": run_id,
                "mismatch_count": mismatch_count,
                "reconstruct_unavailable": reconstruct_unavailable,
            },
        )

    message: str | None = None
    if plan.legacy_estimate_only:
        message = "legacy snapshot: source_set 추정만 표시 (재구성 검증 대상 없음)"
    elif reconstruct_unavailable:
        message = "원천 archive 결손 — serving은 유지되지만 같은 DB를 재구성할 수 없습니다"

    return RestoreSourceVerificationResult(
        entrypoint=entrypoint,
        run_quick_reconcile=plan.run_quick_reconcile,
        legacy_estimate_only=plan.legacy_estimate_only,
        active_source_match_set_id=match_set_id,
        reconcile_run_id=run_id,
        mismatch_count=mismatch_count,
        reconstruct_unavailable=reconstruct_unavailable,
        message=message,
    )


async def _match_set_object_prefix(
    engine: AsyncEngine, match_set_id: str | None
) -> str:
    """Longest common RustFS object-key prefix for a match set's files.

    Used to scope the quick reconcile to the match set's archives. Falls back to
    ``""`` (scan everything) when no shared prefix is derivable.
    """
    if match_set_id is None:
        return ""
    async with engine.connect() as conn:
        keys = (
            await conn.execute(
                text(
                    """
SELECT DISTINCT f.object_key
  FROM ops.source_match_set_items it
  JOIN ops.source_files f
    ON f.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id
   AND it.omitted = false
   AND f.object_key IS NOT NULL
   AND f.state NOT IN ('hard_deleted', 'soft_deleted')
"""
                ),
                {"id": match_set_id},
            )
        ).scalars().all()
    return _common_prefix(tuple(str(k) for k in keys))


def _common_prefix(keys: tuple[str, ...]) -> str:
    if not keys:
        return ""
    prefix = keys[0]
    for key in keys[1:]:
        while not key.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    # Trim to the last path separator so the prefix is a directory boundary.
    sep = prefix.rfind("/")
    return prefix[: sep + 1] if sep >= 0 else prefix


# --- audit -----------------------------------------------------------------


async def _audit(
    conn: AsyncConnection,
    *,
    action: str,
    actor: str | None,
    resource_id: str,
    outcome: str,
    payload: dict[str, Any],
    resource_type: str = "source_match_set",
) -> None:
    now = datetime.now(UTC).isoformat()
    await insert_source_audit_event(
        conn,
        action=action,
        outcome=outcome,
        actor_id=actor,
        resource_type=resource_type,
        resource_id=resource_id,
        payload={**payload, "at": now},
    )
