"""DB + RustFS glue for ``rebuild-db`` and rollback match-set swap (T-205b).

Companion to ``infra/source_match_set_service.py`` (T-205a). This module:

* assembles the ``full_load_batch`` payload the EXISTING loader DAG consumes
  from a ``validated``/``active`` match set's groups — the rebuild "bridge"
  (replacing the removed ``build_full_load_source_set_plan`` entry point);
* runs the **pre-load source-archive integrity gate** (re-verify each group's
  RustFS objects' ``sha256``/``size``/presence + ``group_sha256`` against the
  registry) BEFORE any child loader is enqueued; on mismatch it transitions the
  failing groups to ``quarantined`` and propagates via
  ``recompute_group_aggregates`` (active → ``integrity_alert``, non-active
  ``validated`` → ``invalid``);
* force-closes stale prior rebuild jobs (heartbeat timeout); the next attempt
  materializes into a fresh staging directory;
* records ``ops.dataset_snapshots.source_match_set_id`` (정본 FK) on success;
* performs the rollback atomic match-set swap.

The pure decisions (integrity gate, forced-promotion gate, rollback target
resolution, stale-job detection) live in ``core.source_rebuild`` and are reused
here — none is reimplemented. This module never imports the ``api`` JobQueue
(layered-architecture contract): the endpoint owns the lock + enqueue and calls
these methods.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_categories import category_by_code
from kortravelgeo.core.source_events import (
    SOURCE_FORCED_PROMOTION,
    SOURCE_REBUILD_DB,
)
from kortravelgeo.core.source_rebuild import (
    GroupArchiveCheck,
    IntegrityGateDecision,
    RebuildStartFacts,
    RollbackIntegrityFacts,
    RollbackTargetDecision,
    RollbackTargetFacts,
    RunningJobFacts,
    StaleJobDecision,
    decide_integrity_gate,
    decide_rebuild_start,
    decide_rollback_target,
    decide_stale_jobs,
    recompute_rollback_integrity_alert,
)
from kortravelgeo.exceptions import ConflictError, InvalidInputError, NotFoundError
from kortravelgeo.infra.concurrency import AdvisoryLockKey, AdvisoryLockNamespace
from kortravelgeo.infra.serving_quality import SOURCE_MANIFEST_SQL
from kortravelgeo.infra.source_audit import insert_source_audit_event
from kortravelgeo.infra.source_group_service import recompute_group_aggregates

#: How a match set category maps onto the existing loader job kind + the
#: filesystem subdirectory the loader expects the materialized archive under.
#: Only the build categories that the legacy ``full_load_batch`` DAG handles are
#: bridged; optional validation/enrichment categories are loaded by
#: ``run-validation`` (T-205b run-validation is out of this slice's scope).
_CATEGORY_TO_LOAD_KINDS: dict[str, tuple[str, ...]] = {
    "roadname_hangul_full": ("juso_text_load", "juso_parcel_link_load"),
    "locsum_full": ("locsum_load",),
    "navi_full": ("navi_load",),
    "electronic_map_full": ("shp_polygons_load",),
    "roadaddr_entrance_full": ("roadaddr_entrance_load",),
    "zone_shape_full": ("sppn_makarea_load",),
}

_HEAVY_MATERIALIZE_CATEGORIES = frozenset({"navi_full", "electronic_map_full"})

#: Default heartbeat timeout for stale rebuild-job detection (seconds).
DEFAULT_REBUILD_HEARTBEAT_TIMEOUT_S = 900.0


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


@dataclass(frozen=True)
class RebuildFileRef:
    """One registry file object that can be downloaded for rebuild staging."""

    source_file_id: str
    part_key: str | None
    part_label: str | None
    original_filename: str | None
    object_key: str
    storage_uri: str | None
    sha256: str | None
    size_bytes: int | None
    compression_format: str | None


@dataclass(frozen=True)
class RebuildGroupRef:
    """One build-category group the rebuild will materialize + load."""

    category: str
    source_file_group_id: str
    group_sha256: str | None
    user_yyyymm: str | None
    effective_yyyymm: str | None
    load_kinds: tuple[str, ...]
    object_keys: tuple[str, ...]
    file_ids: tuple[str, ...]
    storage_uris: tuple[str, ...]
    files: tuple[RebuildFileRef, ...]


@dataclass(frozen=True)
class RebuildPlan:
    """Assembled rebuild inputs: the group refs + the full_load_batch payload."""

    source_match_set_id: str
    groups: tuple[RebuildGroupRef, ...]
    batch_payload: dict[str, Any]


class SourceRebuildService:
    """Raw-SQL + RustFS glue for ``rebuild-db`` and rollback (T-205b)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # --- lock key ----------------------------------------------------------

    @staticmethod
    def rebuild_lock_key() -> AdvisoryLockKey:
        """The global ``source_rebuild_db`` advisory lock (doc line ~1417/1555).

        Shared serialization domain with legacy ``full_load_batch`` /
        ``mv_refresh`` / restore hot-swap: the rebuild handler holds this for the
        download/integrity/enqueue phase; the existing serial JobQueue +
        per-stage locks serialize the actual COPY/MV steps.
        """
        return AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_REBUILD_DB)

    # --- start precondition + stale-job sweep ------------------------------

    async def prepare_rebuild(
        self,
        source_match_set_id: str,
        *,
        heartbeat_timeout_s: float = DEFAULT_REBUILD_HEARTBEAT_TIMEOUT_S,
    ) -> tuple[RebuildPlan, StaleJobDecision]:
        """Validate the match set, sweep stale jobs, and assemble the batch plan.

        Raises ``NotFoundError`` for an unknown set, ``ConflictError`` when the
        start precondition fails or a LIVE rebuild job is still running, and
        ``InvalidInputError`` when no bridgeable build category is present.
        """
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT state, integrity_alert, source_set_hash "
                        "FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id FOR UPDATE"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(
                    f"source match set not found: {source_match_set_id}"
                )

            groups = await self._build_group_refs(conn, source_match_set_id)
            all_available = await self._all_groups_available(conn, source_match_set_id)
            start = decide_rebuild_start(
                RebuildStartFacts(
                    state=str(row["state"]),
                    integrity_alert=bool(row["integrity_alert"]),
                    source_set_hash=row["source_set_hash"],
                    all_groups_available=all_available,
                )
            )
            if not start.ok:
                raise ConflictError("; ".join(start.reasons))
            if not groups:
                raise InvalidInputError(
                    "match set has no bridgeable build category for rebuild-db"
                )

            stale = await self._sweep_stale_jobs(
                conn,
                source_match_set_id,
                heartbeat_timeout_s=heartbeat_timeout_s,
            )
            if stale.live_blocking_job_id is not None:
                raise ConflictError(
                    "a rebuild job is already running for this match set "
                    f"(job_id={stale.live_blocking_job_id})"
                )

        plan = self._assemble_plan(source_match_set_id, groups)
        return plan, stale

    async def _sweep_stale_jobs(
        self,
        conn: AsyncConnection,
        source_match_set_id: str,
        *,
        heartbeat_timeout_s: float,
    ) -> StaleJobDecision:
        rows = (
            await conn.execute(
                text(
                    """
SELECT job_id, state,
       EXTRACT(EPOCH FROM (now() - heartbeat_at))::float8 AS secs_since_heartbeat
  FROM load_jobs
 WHERE kind = 'full_load_batch'
   AND state = 'running'
   AND payload ->> 'source_match_set_id' = :msid
"""
                ),
                {"msid": source_match_set_id},
            )
        ).mappings().all()
        decision = decide_stale_jobs(
            tuple(
                RunningJobFacts(
                    job_id=str(r["job_id"]),
                    state=str(r["state"]),
                    seconds_since_heartbeat=(
                        float(r["secs_since_heartbeat"])
                        if r["secs_since_heartbeat"] is not None
                        else None
                    ),
                )
                for r in rows
            ),
            heartbeat_timeout_s=heartbeat_timeout_s,
        )
        for job_id in decision.stale_job_ids:
            # Force-close the stale batch root + its children idempotently; the
            # next materialization attempt uses a fresh staging directory.
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = COALESCE(error_message || E'\n', '')
                       || 'rebuild stale: heartbeat timeout, force-closed',
       finished_at = now(),
       heartbeat_at = now()
 WHERE (job_id = :job_id OR load_batch_id = :job_id)
   AND state IN ('queued','running')
"""
                ),
                {"job_id": job_id},
            )
        return decision

    # --- group refs + batch payload assembly (the bridge) ------------------

    async def prepare_consistency_resume(
        self,
        source_match_set_id: str,
        previous_batch_id: str,
        *,
        current_batch_id: str | None = None,
        expected_manifest: object = None,
    ) -> dict[str, Any]:
        """완료한 원천을 검증해 새 정합성·MV 실행의 입력을 만든다. 과거 행은 바꾸지 않는다."""
        async with self.engine.connect() as conn:
            match_set = (
                (
                    await conn.execute(
                        text(
                            "SELECT state, integrity_alert, source_set_hash "
                            "FROM ops.source_match_sets "
                            "WHERE source_match_set_id = :id"
                        ),
                        {"id": source_match_set_id},
                    )
                )
                .mappings()
                .first()
            )
            if match_set is None:
                raise NotFoundError("재개할 매칭 세트가 없습니다.")
            groups = await self._build_group_refs(conn, source_match_set_id)
            start = decide_rebuild_start(
                RebuildStartFacts(
                    state=str(match_set["state"]),
                    integrity_alert=bool(match_set["integrity_alert"]),
                    source_set_hash=match_set["source_set_hash"],
                    all_groups_available=await self._all_groups_available(
                        conn, source_match_set_id
                    ),
                )
            )
            if not start.ok or not groups:
                raise ConflictError("매칭 세트의 원천 검증·가용 상태를 확인하세요.")
            plan = self._assemble_plan(source_match_set_id, groups)
            previous = (
                (
                    await conn.execute(
                        text("SELECT kind, state, payload FROM load_jobs WHERE job_id = :id"),
                        {"id": previous_batch_id},
                    )
                )
                .mappings()
                .first()
            )
            if previous is None:
                raise NotFoundError("재개할 이전 배치가 없습니다.")
            if previous["kind"] != "full_load_batch" or previous["state"] not in (
                "failed",
                "cancelled",
            ):
                raise ConflictError("실패하거나 취소된 전체 배치만 정합성부터 재개할 수 있습니다.")
            previous_payload = dict(previous["payload"] or {})
            if previous_payload.get(
                "source_match_set_id"
            ) != source_match_set_id or previous_payload.get("forced_promotion"):
                raise ConflictError("동일 매칭 세트의 정상 승격 배치만 재개할 수 있습니다.")
            source_batch_id = previous_payload.get("source_batch_id", previous_batch_id)
            original = (
                await conn.execute(
                    text(
                        "SELECT payload FROM load_jobs "
                        "WHERE job_id = :id AND kind = 'full_load_batch'"
                    ),
                    {"id": source_batch_id},
                )
            ).scalar_one_or_none()
            if not isinstance(original, dict):
                raise ConflictError("원천 적재 배치의 이력을 확인할 수 없습니다.")
            expected_sources = plan.batch_payload["source_set"]
            for candidate in (original, previous_payload):
                actual_sources = candidate.get("source_set", {})
                if candidate.get("source_match_set_id") != source_match_set_id or any(
                    actual_sources.get(key) != value for key, value in expected_sources.items()
                ):
                    raise ConflictError("이전 배치와 현재 매칭 세트의 원천·기준월·해시가 다릅니다.")
            source_jobs: list[RowMapping] = list(
                (
                    await conn.execute(
                        text(
                            "SELECT job_id, kind, state, payload, started_at, finished_at "
                            "FROM load_jobs WHERE parent_job_id = :id "
                            "AND kind NOT IN ('consistency_check', 'mv_refresh') "
                            "ORDER BY created_at"
                        ),
                        {"id": source_batch_id},
                    )
                )
                .mappings()
                .all()
            )
            expected_children = {
                child["kind"]: child["payload"] for child in plan.batch_payload["children"]
            }
            if (
                len(source_jobs) != len(expected_children)
                or {row["kind"] for row in source_jobs} != expected_children.keys()
                or any(
                    row["state"] != "done"
                    or row["started_at"] is None
                    or row["finished_at"] is None
                    for row in source_jobs
                )
            ):
                raise ConflictError("모든 원천 적재가 완료된 배치만 재개할 수 있습니다.")
            identity_fields = (
                "source_file_group_id",
                "source_file_ids",
                "group_sha256",
                "source_yyyymm",
            )
            for row in source_jobs:
                wanted = expected_children[row["kind"]]
                if any(row["payload"].get(key) != wanted.get(key) for key in identity_fields):
                    raise ConflictError(
                        "완료한 원천 작업의 파일·해시·기준월이 현재 구성과 다릅니다."
                    )
            first_started = min(row["started_at"] for row in source_jobs)
            history_ids = [row["job_id"] for row in source_jobs]
            cohort_id = previous_payload.get("source_cohort_batch_id")
            if cohort_id is None and previous_payload.get("repair_from_batch_id"):
                cohort_id = previous_batch_id
            if cohort_id is not None:
                if not isinstance(cohort_id, str):
                    raise ConflictError("복구 원천 배치의 식별자를 확인하세요.")
                source_jobs, cancelled_ids = await self._repair_resume_sources(
                    conn,
                    cohort_id=cohort_id,
                    source_batch_id=source_batch_id,
                    source_match_set_id=source_match_set_id,
                    original_jobs=source_jobs,
                    expected_sources=expected_sources,
                    expected_children=expected_children,
                )
                history_ids.extend(cancelled_ids)
                history_ids.extend(row["job_id"] for row in source_jobs)
            other = await conn.scalar(
                text("""
SELECT job_id FROM load_jobs
 WHERE job_id <> ALL(CAST(:source_ids AS text[]))
   AND (right(kind, 5) = '_load' OR right(kind, 6) = '_delta')
   AND (state IN ('queued', 'running') OR started_at >= :first_started
        OR finished_at >= :first_started)
 LIMIT 1
"""),
                {
                    "source_ids": history_ids,
                    "first_started": first_started,
                },
            )
            active_batch = await conn.scalar(
                text("""
SELECT job_id FROM load_jobs WHERE kind = 'full_load_batch' AND state IN ('queued', 'running')
 AND (CAST(:current AS text) IS NULL OR job_id <> :current) LIMIT 1
"""),
                {"current": current_batch_id},
            )
            if other or active_batch:
                raise ConflictError(
                    "다른 원천 적재가 시작됐습니다. 현재 원천의 전체 적재 완료를 확인하세요."
                )
            manifest = await conn.scalar(text(SOURCE_MANIFEST_SQL))
            if not isinstance(manifest, list) or not manifest:
                raise ConflictError("원천 manifest가 없어 완료 상태를 증명할 수 없습니다.")
            by_table = {row["table_name"]: row for row in manifest}
            tables = {
                "shp_polygons_load": "tl_spbd_buld_polygon",
                "locsum_load": "tl_locsum_entrc",
                "navi_load": "tl_navi_buld_centroid",
                "roadaddr_entrance_load": "tl_roadaddr_entrc",
                "juso_text_load": "tl_juso_text",
                "juso_parcel_link_load": "tl_juso_parcel_link",
                "sppn_makarea_load": "tl_sppn_makarea",
            }
            for row in source_jobs:
                entry = by_table.get(tables[row["kind"]])
                if (
                    entry is None
                    or not entry.get("row_count")
                    or entry.get("source_yyyymm") != row["payload"].get("source_yyyymm")
                    or not row["started_at"].timestamp()
                    <= float(entry["updated_at"])
                    <= row["finished_at"].timestamp()
                ):
                    raise ConflictError(
                        "현재 원천이 이전 완료 작업과 일치하지 않거나 일부만 적재됐습니다."
                    )
            recorded = (
                expected_manifest
                if expected_manifest is not None
                else previous_payload.get("source_checkpoint")
            )
            if recorded is not None and recorded != manifest:
                raise ConflictError("완료 이후 원천 manifest가 변경돼 정합성 재개를 차단했습니다.")
            payload = dict(plan.batch_payload)
            payload.pop("children", None)
            payload.pop("staging_dir", None)
            payload.update(
                resume_from_batch_id=previous_batch_id,
                source_batch_id=source_batch_id,
                source_checkpoint=manifest,
                reused_source_jobs=[
                    {"job_id": row["job_id"], "kind": row["kind"]} for row in source_jobs
                ],
            )
            payload["source_set"] = dict(
                expected_sources,
                resume_from_batch_id=previous_batch_id,
                source_batch_id=source_batch_id,
            )
            if cohort_id is not None:
                payload["source_cohort_batch_id"] = cohort_id
                payload["source_set"]["source_cohort_batch_id"] = cohort_id
            return payload

    async def _repair_resume_sources(
        self,
        conn: AsyncConnection,
        *,
        cohort_id: str,
        source_batch_id: str,
        source_match_set_id: str,
        original_jobs: list[RowMapping],
        expected_sources: Mapping[str, Any],
        expected_children: Mapping[str, Any],
    ) -> tuple[list[RowMapping], list[str]]:
        """취소된 SHP만 복구한 배치의 새 완료 작업과 기존 완료 작업을 대조한다."""
        message = "복구 배치의 전자지도·재사용 원천·취소 이력을 확인할 수 없습니다."

        async def root_payload(job_id: str, state: tuple[str, ...]) -> dict[str, Any]:
            row = (
                (
                    await conn.execute(
                        text("SELECT kind,state,payload FROM load_jobs WHERE job_id=:id"),
                        {"id": job_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None or row["kind"] != "full_load_batch" or row["state"] not in state:
                raise ConflictError(message)
            data = row["payload"]
            if (
                not isinstance(data, dict)
                or data.get("source_match_set_id") != source_match_set_id
                or data.get("forced_promotion")
                or not isinstance(data.get("source_set"), dict)
                or any(data["source_set"].get(k) != v for k, v in expected_sources.items())
            ):
                raise ConflictError(message)
            return data

        async def children(job_id: str) -> list[RowMapping]:
            return list(
                (
                    await conn.execute(
                        text(
                            "SELECT job_id,kind,state,payload,load_batch_id,started_at,finished_at "
                            "FROM load_jobs WHERE parent_job_id=:id "
                            "AND kind NOT IN ('consistency_check','mv_refresh') ORDER BY created_at"
                        ),
                        {"id": job_id},
                    )
                )
                .mappings()
                .all()
            )

        cohort = await root_payload(cohort_id, ("failed", "cancelled"))
        abandoned_id = cohort.get("repair_from_batch_id")
        if (
            cohort_id == source_batch_id
            or cohort.get("source_batch_id") != source_batch_id
            or not isinstance(abandoned_id, str)
            or abandoned_id in (source_batch_id, cohort_id)
            or "shp_polygons_load" not in expected_children
        ):
            raise ConflictError(message)
        await root_payload(abandoned_id, ("cancelled",))
        repaired = await children(cohort_id)
        if len(repaired) != 1:
            raise ConflictError(message)
        replacement = repaired[0]
        if (
            replacement["kind"] != "shp_polygons_load"
            or replacement["state"] != "done"
            or replacement["load_batch_id"] != cohort_id
            or replacement["started_at"] is None
            or replacement["finished_at"] is None
            or replacement["started_at"] > replacement["finished_at"]
            or not isinstance(replacement["payload"], dict)
            or replacement["payload"].get("mode") != "append"
        ):
            raise ConflictError(message)
        identity = ("source_file_group_id", "source_file_ids", "group_sha256", "source_yyyymm")
        if any(
            replacement["payload"].get(k) != expected_children["shp_polygons_load"].get(k)
            for k in identity
        ):
            raise ConflictError(message)
        partitions = []
        for key in ("repair_preserved_sidos", "repair_remaining_sidos"):
            names = cohort.get(key)
            if (
                not isinstance(names, list)
                or not names
                or any(not isinstance(name, str) or not name for name in names)
                or replacement["payload"].get(key) != names
            ):
                raise ConflictError(message)
            partitions.extend(names)
        if len(partitions) != len(set(partitions)) or len(partitions) != len(
            expected_children["shp_polygons_load"]["source_file_ids"]
        ):
            raise ConflictError(message)
        originals = [row for row in original_jobs if row["kind"] != "shp_polygons_load"]
        reused = cohort.get("reused_source_jobs")
        if (
            not isinstance(reused, list)
            or len(reused) != len(originals)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("job_id"), str)
                or not isinstance(row.get("kind"), str)
                for row in reused
            )
            or {(r["job_id"], r["kind"]) for r in reused}
            != {(r["job_id"], r["kind"]) for r in originals}
        ):
            raise ConflictError(message)
        abandoned = await children(abandoned_id)
        if (
            len(abandoned) != len(expected_children)
            or {row["kind"] for row in abandoned} != expected_children.keys()
        ):
            raise ConflictError(message)
        for row in abandoned:
            if (
                row["state"] != "cancelled"
                or row["load_batch_id"] != abandoned_id
                or row["finished_at"] is None
                or not isinstance(row["payload"], dict)
                or any(
                    row["payload"].get(k) != expected_children[row["kind"]].get(k) for k in identity
                )
            ):
                raise ConflictError(message)
            if row["kind"] == "shp_polygons_load":
                if (
                    row["started_at"] is None
                    or row["started_at"] < max(r["finished_at"] for r in original_jobs)
                    or row["started_at"] > row["finished_at"]
                    or row["finished_at"] > replacement["started_at"]
                ):
                    raise ConflictError(message)
            elif row["started_at"] is not None:
                raise ConflictError(message)
        selected = [
            replacement if row["kind"] == "shp_polygons_load" else row for row in original_jobs
        ]
        return selected, [row["job_id"] for row in abandoned]

    async def _build_group_refs(
        self, conn: AsyncConnection, source_match_set_id: str
    ) -> tuple[RebuildGroupRef, ...]:
        rows = (
            await conn.execute(
                text(
                    """
SELECT it.category, it.source_file_group_id, it.effective_yyyymm, it.omitted,
       it.load_order, g.group_sha256, g.user_yyyymm
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id
   AND it.omitted = false
 ORDER BY it.load_order NULLS LAST, it.category
"""
                ),
                {"id": source_match_set_id},
            )
        ).mappings().all()
        refs: list[RebuildGroupRef] = []
        for r in rows:
            category = str(r["category"])
            load_kinds = _CATEGORY_TO_LOAD_KINDS.get(category)
            if load_kinds is None:
                # Optional validation/enrichment category — not part of the
                # full_load_batch DAG (handled by run-validation, out of scope).
                continue
            gid = str(r["source_file_group_id"])
            files = (
                await conn.execute(
                    text(
                        """
SELECT source_file_id, part_key, part_label, original_filename, object_key,
       storage_uri, sha256, size_bytes, compression_format
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
 ORDER BY part_key
"""
                    ),
                    {"gid": gid},
                )
            ).mappings().all()
            refs.append(
                RebuildGroupRef(
                    category=category,
                    source_file_group_id=gid,
                    group_sha256=r["group_sha256"],
                    user_yyyymm=r["user_yyyymm"],
                    effective_yyyymm=r["effective_yyyymm"],
                    load_kinds=load_kinds,
                    object_keys=tuple(
                        str(f["object_key"]) for f in files if f["object_key"]
                    ),
                    file_ids=tuple(str(f["source_file_id"]) for f in files),
                    storage_uris=tuple(
                        str(f["storage_uri"]) for f in files if f["storage_uri"]
                    ),
                    files=tuple(
                        RebuildFileRef(
                            source_file_id=str(f["source_file_id"]),
                            part_key=str(f["part_key"]) if f["part_key"] else None,
                            part_label=str(f["part_label"]) if f["part_label"] else None,
                            original_filename=(
                                str(f["original_filename"])
                                if f["original_filename"]
                                else None
                            ),
                            object_key=str(f["object_key"]),
                            storage_uri=(
                                str(f["storage_uri"]) if f["storage_uri"] else None
                            ),
                            sha256=str(f["sha256"]) if f["sha256"] else None,
                            size_bytes=(
                                int(f["size_bytes"]) if f["size_bytes"] is not None else None
                            ),
                            compression_format=(
                                str(f["compression_format"])
                                if f["compression_format"]
                                else None
                            ),
                        )
                        for f in files
                        if f["object_key"]
                    ),
                )
            )
        return tuple(refs)

    def _assemble_plan(
        self, source_match_set_id: str, groups: tuple[RebuildGroupRef, ...]
    ) -> RebuildPlan:
        """Build the ``full_load_batch`` payload the existing DAG consumes.

        Each build group becomes a child ``{"kind": <load_kind>, "payload":
        {...}}`` — the same structure ``batch_children`` already accepts. The
        ``path`` is the materialized staging directory the loader reads; the root
        payload carries ``source_match_set_id`` + per-category provenance (doc
        step 7, ~1548).
        """
        staging_root = self.staging_dir(source_match_set_id)
        children: list[dict[str, Any]] = []
        source_set: dict[str, Any] = {}
        for ref in groups:
            yyyymm = ref.effective_yyyymm or ref.user_yyyymm
            child_payload: dict[str, Any] = {
                "replace": True,
                "path": str(self.category_staging_dir(staging_root, ref.category)),
                "source_yyyymm": yyyymm,
                "source_file_group_id": ref.source_file_group_id,
                "source_file_ids": list(ref.file_ids),
                "group_sha256": ref.group_sha256,
                "storage_uris": list(ref.storage_uris),
            }
            for load_kind in ref.load_kinds:
                children.append({"kind": load_kind, "payload": dict(child_payload)})
            source_set[ref.category] = {
                "source_file_group_id": ref.source_file_group_id,
                "group_sha256": ref.group_sha256,
                "user_yyyymm": ref.user_yyyymm,
                "effective_yyyymm": ref.effective_yyyymm,
            }
        batch_payload: dict[str, Any] = {
            "children": children,
            "source_match_set_id": source_match_set_id,
            "source_set": source_set,
            "staging_dir": str(staging_root),
        }
        return RebuildPlan(
            source_match_set_id=source_match_set_id,
            groups=groups,
            batch_payload=batch_payload,
        )

    @staticmethod
    def staging_dir(source_match_set_id: str) -> Path:
        return Path("rebuild_staging") / source_match_set_id

    @staticmethod
    def category_staging_dir(staging_root: Path, category: str) -> Path:
        return staging_root / category

    async def materialize_rebuild_plan(
        self,
        rustfs: Any,
        plan: RebuildPlan,
        staging_root: Path,
        *,
        download_concurrency: int = 3,
        materialize_concurrency: int = 2,
    ) -> dict[str, Any]:
        """Download/extract registry objects into loader-readable staging paths.

        The existing load DAG consumes filesystem paths. Source registry rebuilds
        therefore have to turn RustFS objects back into the exact shape each
        loader already understands before the batch is enqueued.
        """

        staging_root = await asyncio.to_thread(
            lambda: staging_root.expanduser().resolve(strict=False)
        )
        if staging_root.exists():
            await asyncio.to_thread(shutil.rmtree, staging_root)
        await asyncio.to_thread(staging_root.mkdir, parents=True, exist_ok=True)

        relocated = relocate_rebuild_batch_payload(plan.batch_payload, staging_root)
        path_by_category = _child_paths_by_category(relocated)
        download_sem = asyncio.Semaphore(max(1, download_concurrency))
        materialize_sem = asyncio.Semaphore(
            _effective_materialize_concurrency(plan.groups, materialize_concurrency)
        )

        async def materialize_group(ref: RebuildGroupRef) -> None:
            target = path_by_category[ref.category]
            try:
                await _materialize_group(
                    rustfs,
                    ref,
                    target,
                    download_sem=download_sem,
                    materialize_sem=materialize_sem,
                )
            except InvalidInputError as exc:
                raise InvalidInputError(
                    "failed to materialize rebuild source "
                    f"{ref.category}/{ref.source_file_group_id}: {exc}"
                ) from exc
            except (OSError, RuntimeError) as exc:
                raise RuntimeError(
                    "failed to materialize rebuild source "
                    f"{ref.category}/{ref.source_file_group_id}: {exc}"
                ) from exc

        tasks = [asyncio.create_task(materialize_group(ref)) for ref in plan.groups]

        async def cleanup_failed_materialize() -> None:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.to_thread(shutil.rmtree, staging_root, ignore_errors=True)

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            await cleanup_failed_materialize()
            raise
        except Exception:
            await cleanup_failed_materialize()
            raise
        return relocated

    # --- pre-load source-archive integrity gate ----------------------------

    def integrity_gate(
        self, checks: tuple[GroupArchiveCheck, ...]
    ) -> IntegrityGateDecision:
        """Run the pure pre-load integrity gate (doc line ~1544)."""
        return decide_integrity_gate(checks)

    async def quarantine_failed_groups(
        self,
        source_match_set_id: str,
        failed_group_ids: tuple[str, ...],
        *,
        actor: str | None,
        reason: str,
    ) -> tuple[str, ...]:
        """Quarantine each gated group + propagate to referencing match sets.

        Mirrors the doc: failing groups go ``quarantined``; their non-deleted
        children go ``quarantined``; then ``recompute_group_aggregates`` folds
        that into the group state and propagates (active set → ``integrity_alert``,
        non-active ``validated`` → ``invalid``, pre-hash stays). Returns the
        affected match set ids for the response. No child load jobs are created.
        """
        affected: set[str] = set()
        async with self.engine.begin() as conn:
            for gid in failed_group_ids:
                await conn.execute(
                    text(
                        """
UPDATE ops.source_files
   SET state = 'quarantined', validation_state = 'failed'
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
"""
                    ),
                    {"gid": gid},
                )
                await conn.execute(
                    text(
                        """
UPDATE ops.source_file_groups
   SET state = 'quarantined', validation_state = 'failed', updated_at = now()
 WHERE source_file_group_id = :gid
"""
                    ),
                    {"gid": gid},
                )
                recompute = await recompute_group_aggregates(
                    conn,
                    gid,
                    trigger="rebuild_integrity_gate",
                    structure_validation_state="failed",
                )
                affected.update(recompute.affected_match_set_ids)
            await self._audit(
                conn,
                action=SOURCE_REBUILD_DB,
                actor=actor,
                resource_id=source_match_set_id,
                outcome="integrity_gate_failed",
                payload={
                    "failed_group_ids": list(failed_group_ids),
                    "reason": reason,
                },
            )
        return tuple(sorted(affected))

    # --- snapshot FK + audit on success ------------------------------------

    async def record_rebuild_audit(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        outcome: str,
        job_id: str | None,
        load_batch_id: str | None,
        forced_promotion: bool,
        reason: str | None,
    ) -> None:
        async with self.engine.begin() as conn:
            await self._audit(
                conn,
                action=SOURCE_REBUILD_DB,
                actor=actor,
                resource_id=source_match_set_id,
                outcome=outcome,
                job_id=job_id,
                payload={
                    "load_batch_id": load_batch_id,
                    "forced_promotion": forced_promotion,
                    "reason": reason,
                },
            )
            if forced_promotion:
                await self._audit(
                    conn,
                    action=SOURCE_FORCED_PROMOTION,
                    actor=actor,
                    resource_id=source_match_set_id,
                    outcome=outcome,
                    job_id=job_id,
                    payload={
                        "load_batch_id": load_batch_id,
                        "reason": reason,
                        "bypassed": "consistency_error_only",
                    },
                )

    # --- rollback atomic match-set swap ------------------------------------

    async def rollback_swap(
        self,
        serving_release_id: str,
        *,
        actor: str | None,
        reason: str | None,
    ) -> tuple[RollbackTargetDecision, bool]:
        """Resolve + apply the rollback's match-set side (doc ~818/1530, #18).

        Under the ``SOURCE_MATCH_ACTIVATE`` advisory lock in ONE transaction:
        resolve the target snapshot's ``source_match_set_id``; if present, retire
        the current active match set and restore the target to ``active`` (the
        same one-active invariant as activate), recomputing the target's
        ``integrity_alert`` from a pre-rollback DB quick reconcile of its groups.
        Legacy snapshots (no FK) make NO match-set change. Returns the decision +
        the recomputed ``integrity_alert``.
        """
        lock = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_MATCH_ACTIVATE)
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock.as_int()}
            )
            release = (
                await conn.execute(
                    text(
                        """
SELECT r.serving_release_id, r.dataset_snapshot_id, r.state, s.source_match_set_id
  FROM ops.serving_releases r
  JOIN ops.dataset_snapshots s ON s.dataset_snapshot_id = r.dataset_snapshot_id
 WHERE r.serving_release_id = :rid
"""
                    ),
                    {"rid": serving_release_id},
                )
            ).mappings().first()
            if release is None:
                raise NotFoundError(f"serving release not found: {serving_release_id}")

            current_active = (
                await conn.execute(
                    text(
                        "SELECT source_match_set_id FROM ops.source_match_sets "
                        "WHERE state = 'active' LIMIT 1 FOR UPDATE"
                    )
                )
            ).first()
            decision = decide_rollback_target(
                RollbackTargetFacts(
                    release_id=str(release["serving_release_id"]),
                    snapshot_id=str(release["dataset_snapshot_id"]),
                    release_state=str(release["state"]),
                    target_source_match_set_id=(
                        str(release["source_match_set_id"])
                        if release["source_match_set_id"]
                        else None
                    ),
                    current_active_match_set_id=(
                        str(current_active[0]) if current_active else None
                    ),
                )
            )
            if not decision.ok:
                raise ConflictError("; ".join(decision.reasons))

            integrity_alert = False
            if decision.mode == "match_set_swap":
                integrity_alert = await self._apply_match_set_swap(
                    conn, decision
                )
            await self._audit(
                conn,
                action="serving_release.rollback",
                actor=actor,
                resource_id=serving_release_id,
                outcome=decision.mode,
                resource_type="serving_release",
                payload={
                    "mode": decision.mode,
                    "activated_match_set_id": decision.activate_match_set_id,
                    "retired_match_set_id": decision.retire_match_set_id,
                    "target_integrity_alert": integrity_alert,
                    "reason": reason,
                },
            )
        return decision, integrity_alert

    async def _apply_match_set_swap(
        self, conn: AsyncConnection, decision: RollbackTargetDecision
    ) -> bool:
        target_id = decision.activate_match_set_id
        assert target_id is not None  # mode == match_set_swap guarantees this
        if decision.retire_match_set_id is not None:
            await conn.execute(
                text(
                    "UPDATE ops.source_match_sets SET state = 'retired', "
                    "updated_at = now() WHERE source_match_set_id = :id"
                ),
                {"id": decision.retire_match_set_id},
            )
        # Pre-rollback source quick reconcile: derive integrity_alert from the
        # registry state of the target's referenced groups.
        facts = await self._rollback_integrity_facts(conn, target_id)
        integrity_alert = recompute_rollback_integrity_alert(facts)
        await conn.execute(
            _json_text(
                """
UPDATE ops.source_match_sets
   SET state = 'active',
       integrity_alert = :alert,
       integrity_alert_at = CASE WHEN :alert THEN now() ELSE NULL END,
       integrity_alert_detail = CASE WHEN :alert THEN :detail
                                     ELSE '{}'::jsonb END,
       updated_at = now()
 WHERE source_match_set_id = :id
""",
                "detail",
            ),
            {
                "id": target_id,
                "alert": integrity_alert,
                "detail": {
                    "trigger": "rollback_quick_reconcile",
                    "unavailable_group_ids": list(facts.unavailable_group_ids),
                    "at": datetime.now(UTC).isoformat(),
                },
            },
        )
        return integrity_alert

    async def _rollback_integrity_facts(
        self, conn: AsyncConnection, match_set_id: str
    ) -> RollbackIntegrityFacts:
        rows = (
            await conn.execute(
                text(
                    """
SELECT it.source_file_group_id, g.state AS group_state
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id AND it.omitted = false
"""
                ),
                {"id": match_set_id},
            )
        ).mappings().all()
        unavailable = tuple(
            str(r["source_file_group_id"])
            for r in rows
            if r["group_state"] != "available"
        )
        return RollbackIntegrityFacts(
            all_groups_available=not unavailable and bool(rows),
            unavailable_group_ids=unavailable,
        )

    # --- helpers -----------------------------------------------------------

    async def _all_groups_available(
        self, conn: AsyncConnection, source_match_set_id: str
    ) -> bool:
        row = (
            await conn.execute(
                text(
                    """
SELECT bool_and(g.state = 'available') AS all_available, count(*) AS n
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id AND it.omitted = false
"""
                ),
                {"id": source_match_set_id},
            )
        ).mappings().first()
        return bool(row and row["n"] and row["all_available"])

    async def _audit(
        self,
        conn: AsyncConnection,
        *,
        action: str,
        actor: str | None,
        resource_id: str,
        outcome: str,
        payload: dict[str, Any],
        job_id: str | None = None,
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
            job_id=job_id,
            payload={**payload, "at": now},
        )


def category_load_kind(category: str) -> str | None:
    """Public accessor: the loader job kind for a build category (or ``None``)."""
    if category not in category_by_code:
        return None
    load_kinds = _CATEGORY_TO_LOAD_KINDS.get(category)
    return load_kinds[0] if load_kinds else None


def relocate_rebuild_batch_payload(
    batch_payload: Mapping[str, Any], staging_root: Path
) -> dict[str, Any]:
    """Return a copy whose child paths point at ``staging_root``."""

    relocated = dict(batch_payload)
    relocated["staging_dir"] = str(staging_root)
    children: list[dict[str, Any]] = []
    for child in batch_payload.get("children", ()):
        if not isinstance(child, Mapping):
            continue
        payload = child.get("payload")
        child_payload = dict(payload) if isinstance(payload, Mapping) else {}
        category = Path(str(child_payload.get("path") or "")).name
        if category:
            child_payload["path"] = str(staging_root / category)
        children.append({"kind": child.get("kind"), "payload": child_payload})
    relocated["children"] = children
    return relocated


def _child_paths_by_category(batch_payload: Mapping[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for child in batch_payload.get("children", ()):
        if not isinstance(child, Mapping):
            continue
        payload = child.get("payload")
        if not isinstance(payload, Mapping):
            continue
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        paths[path.name] = path
    return paths


def _effective_materialize_concurrency(
    groups: tuple[RebuildGroupRef, ...], requested: int
) -> int:
    concurrency = max(1, requested)
    if any(group.category in _HEAVY_MATERIALIZE_CATEGORIES for group in groups):
        return 1
    return concurrency


async def _materialize_group(
    rustfs: Any,
    ref: RebuildGroupRef,
    target: Path,
    *,
    download_sem: asyncio.Semaphore,
    materialize_sem: asyncio.Semaphore,
) -> None:
    if not ref.files:
        raise InvalidInputError(
            f"rebuild source group has no RustFS objects: {ref.category}"
        )
    await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)

    if ref.category in {"roadaddr_entrance_full", "zone_shape_full"}:
        await asyncio.gather(
            *(
                _download_rebuild_file(
                    rustfs,
                    ref,
                    file,
                    target / _archive_name(ref, file),
                    download_sem,
                )
                for file in ref.files
            )
        )
        await asyncio.to_thread(_write_materialized_marker, target)
        return

    download_dir = target.parent / f".{target.name}-downloads"
    if download_dir.exists():
        await asyncio.to_thread(shutil.rmtree, download_dir)
    await asyncio.to_thread(download_dir.mkdir, parents=True, exist_ok=True)
    downloads = {
        file: download_dir / _archive_name(ref, file)
        for file in ref.files
    }
    await asyncio.gather(
        *(
            _download_rebuild_file(rustfs, ref, file, destination, download_sem)
            for file, destination in downloads.items()
        )
    )

    async with materialize_sem:
        await asyncio.to_thread(_materialize_downloads, ref, downloads, target)
    await asyncio.to_thread(shutil.rmtree, download_dir)
    await asyncio.to_thread(_write_materialized_marker, target)


async def _download_rebuild_file(
    rustfs: Any,
    ref: RebuildGroupRef,
    file: RebuildFileRef,
    destination: Path,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        await rustfs.download_file(file.object_key, destination)
        await _verify_downloaded_rebuild_file(ref, file, destination)


async def _verify_downloaded_rebuild_file(
    ref: RebuildGroupRef, file: RebuildFileRef, destination: Path
) -> None:
    if file.size_bytes is not None:
        stat = await asyncio.to_thread(destination.stat)
        if stat.st_size != file.size_bytes:
            raise InvalidInputError(
                "rebuild source download size mismatch: "
                f"{ref.category}/{file.part_key or file.source_file_id} "
                f"expected={file.size_bytes} actual={stat.st_size}"
            )
    if file.sha256:
        digest = await asyncio.to_thread(_sha256_file, destination)
        if digest != file.sha256:
            raise InvalidInputError(
                "rebuild source download sha256 mismatch: "
                f"{ref.category}/{file.part_key or file.source_file_id} "
                f"expected={file.sha256} actual={digest}"
            )


def _materialize_downloads(
    ref: RebuildGroupRef,
    downloads: Mapping[RebuildFileRef, Path],
    target: Path,
) -> None:
    if ref.category in {"roadname_hangul_full", "locsum_full"}:
        _expect_one_file(ref, downloads)
        _extract_zip_safe(next(iter(downloads.values())), target)
        return
    if ref.category == "navi_full":
        _expect_one_file(ref, downloads)
        _extract_navi_7z(next(iter(downloads.values())), target)
        return
    if ref.category == "electronic_map_full":
        for file, archive in downloads.items():
            part_label = file.part_label or file.part_key
            if not part_label:
                raise InvalidInputError(
                    "electronic_map_full rebuild file requires part_label or part_key"
                )
            _extract_zip_safe(archive, target / _safe_path_name(part_label))
        return
    raise InvalidInputError(f"unsupported rebuild materialize category: {ref.category}")


def _expect_one_file(
    ref: RebuildGroupRef, downloads: Mapping[RebuildFileRef, Path]
) -> None:
    if len(downloads) != 1:
        raise InvalidInputError(
            f"{ref.category} rebuild staging expects one archive, got {len(downloads)}"
        )


def _archive_name(ref: RebuildGroupRef, file: RebuildFileRef) -> str:
    suffix = _archive_suffix(ref, file)
    candidates = (
        file.original_filename,
        Path(file.object_key).name,
        file.part_key,
        file.source_file_id,
    )
    for candidate in candidates:
        if not candidate:
            continue
        name = _safe_path_name(candidate)
        candidate_suffix = Path(name).suffix.lower()
        if candidate_suffix:
            if name in {"archive.zip", "archive.7z"} and file.part_key not in {
                None,
                "archive",
            }:
                continue
            return name
        if name != "archive" or file.part_key in {None, "archive"}:
            return f"{name}{suffix}"
    return f"{file.source_file_id}{suffix}"


def _archive_suffix(ref: RebuildGroupRef, file: RebuildFileRef) -> str:
    if ref.category == "navi_full":
        return ".7z"
    for value in (file.original_filename, file.object_key, file.storage_uri):
        if not value:
            continue
        suffix = Path(value).suffix.lower()
        if suffix in {".zip", ".7z"}:
            return suffix
    compression = (file.compression_format or "").lower().lstrip(".")
    if compression in {"zip", "7z"}:
        return f".{compression}"
    return ".zip"


def _safe_path_name(value: str) -> str:
    name = Path(value).name
    if name in {"", ".", ".."}:
        raise InvalidInputError(f"invalid rebuild staging file name: {value}")
    return name


def _extract_zip_safe(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            member_target = (target / member.filename).resolve()
            if member_target != root and root not in member_target.parents:
                raise InvalidInputError(
                    f"rebuild source ZIP contains unsafe member: {member.filename}"
                )
        zip_file.extractall(target)


def _extract_navi_7z(archive: Path, target: Path) -> None:
    seven_zip = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
    if seven_zip is None:
        raise InvalidInputError("7z/7zz/7za command not found; navi .7z를 풀 수 없습니다")
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as output:
        completed = subprocess.run(
            [
                seven_zip,
                "x",
                "-y",
                "-mmt=1",
                f"-o{target}",
                str(archive),
                "match_build_*.txt",
                "match_rs_entrc.txt",
                "match_jibun_*.txt",
            ],
            check=False,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        excerpt = _tail_text(output)
    if completed.returncode != 0:
        raise InvalidInputError(f"failed to materialize navi .7z archive: {excerpt}")


def _tail_text(output: Any, *, limit: int = 1000) -> str:
    output.flush()
    output.seek(0, 2)
    size = output.tell()
    output.seek(max(0, size - limit))
    return str(output.read())


def _write_materialized_marker(target: Path) -> None:
    marker = target / ".ktg-materialized-ok"
    marker.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_source_match_set_id(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("source_match_set_id")
    return str(value) if isinstance(value, str) and value else None
