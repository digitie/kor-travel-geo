"""실제 PostgreSQL에서 완료 원천의 재사용 조건과 쓰기·재개 상호 배제를 검증한다."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from kortravelgeo.exceptions import ConflictError
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.source_rebuild_service import RebuildGroupRef, SourceRebuildService
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

BATCH = "batch_" + "1" * 32


@pytest_asyncio.fixture
async def completed_sources(monkeypatch):
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.connect() as conn, conn.begin():
            for name in ("load_jobs", "load_manifest"):
                await conn.execute(
                    text(
                        f"CREATE TEMP TABLE {name} "
                        f"(LIKE public.{name} INCLUDING DEFAULTS) ON COMMIT DROP"
                    )
                )
            match_id = str(uuid4())
            await conn.execute(
                text("""
INSERT INTO ops.source_match_sets (source_match_set_id,name,profile,state,source_set_hash)
VALUES (CAST(:id AS uuid),'재개 검증용','serving_recommended','validated',:hash)
"""),
                {"id": match_id, "hash": "a" * 64},
            )
            group = RebuildGroupRef(
                category="roadname_hangul_full",
                source_file_group_id=str(uuid4()),
                group_sha256="b" * 64,
                user_yyyymm="202609",
                effective_yyyymm="202609",
                load_kinds=("juso_text_load", "juso_parcel_link_load"),
                object_keys=(),
                file_ids=(str(uuid4()),),
                storage_uris=(),
                files=(),
            )
            monkeypatch.setattr(
                SourceRebuildService, "_build_group_refs", AsyncMock(return_value=(group,))
            )
            monkeypatch.setattr(
                SourceRebuildService, "_all_groups_available", AsyncMock(return_value=True)
            )

            @asynccontextmanager
            async def same_connection():
                yield conn

            service = SourceRebuildService(SimpleNamespace(connect=same_connection))
            plan = service._assemble_plan(match_id, (group,))
            await conn.execute(
                text("""
INSERT INTO load_jobs(job_id,kind,state,payload)
VALUES (:id,'full_load_batch','failed',CAST(:payload AS jsonb))
"""),
                {"id": BATCH, "payload": json.dumps(plan.batch_payload)},
            )
            for index, child in enumerate(plan.batch_payload["children"]):
                await conn.execute(
                    text("""
INSERT INTO load_jobs(job_id,kind,state,payload,parent_job_id,load_batch_id,started_at,finished_at)
VALUES (:id,:kind,'done',CAST(:payload AS jsonb),:parent,:parent,
 now()-interval '10min',now()-interval '5min')
"""),
                    {
                        "id": f"source-{index}",
                        "kind": child["kind"],
                        "payload": json.dumps(child["payload"]),
                        "parent": BATCH,
                    },
                )
            await conn.execute(
                text("""
INSERT INTO load_manifest(table_name,row_count,source_yyyymm,updated_at) VALUES
 ('tl_juso_text',10,'202609',now()-interval '7min'),
 ('tl_juso_parcel_link',5,'202609',now()-interval '7min')
""")
            )
            yield SimpleNamespace(conn=conn, engine=engine, service=service, match_id=match_id)
            await conn.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resume_reuses_source_ids_without_changing_failed_history(completed_sources):
    f = completed_sources
    result = await f.service.prepare_consistency_resume(f.match_id, BATCH)
    assert result["source_batch_id"] == result["resume_from_batch_id"] == BATCH
    assert {row["job_id"] for row in result["reused_source_jobs"]} == {"source-0", "source-1"}
    assert len(result["source_checkpoint"]) == 2
    assert "children" not in result
    assert (
        await f.conn.scalar(text("SELECT state FROM load_jobs WHERE job_id=:id"), {"id": BATCH})
        == "failed"
    )
    assert await f.conn.scalar(text("SELECT count(*) FROM load_jobs")) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "incomplete",
        "group",
        "month",
        "truncated",
        "later_writer",
        "active_writer",
        "active_batch",
        "manifest",
    ],
)
async def test_resume_rejects_incomplete_changed_or_concurrent_sources(completed_sources, change):
    f = completed_sources
    previous = await f.service.prepare_consistency_resume(f.match_id, BATCH)
    if change == "incomplete":
        await f.conn.execute(text("UPDATE load_jobs SET state='failed' WHERE job_id='source-1'"))
    elif change == "group":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET payload="
                "jsonb_set(payload,'{group_sha256}','\"다른해시\"') WHERE job_id='source-1'"
            )
        )
    elif change == "month":
        await f.conn.execute(text("UPDATE load_manifest SET source_yyyymm='202610'"))
    elif change == "truncated":
        await f.conn.execute(text("UPDATE load_manifest SET row_count=0,source_yyyymm=NULL"))
    elif change in ("later_writer", "active_writer", "active_batch"):
        await f.conn.execute(
            text("""
INSERT INTO load_jobs(job_id,kind,state,payload,started_at)
VALUES ('다른작업',:kind,:state,'{}',now())
"""),
            {
                "kind": "full_load_batch" if change == "active_batch" else "shp_polygons_load",
                "state": "failed" if change == "later_writer" else "running",
            },
        )
    else:
        await f.conn.execute(
            text("UPDATE load_manifest SET source_set=CAST(:payload AS jsonb)"),
            {"payload": json.dumps({"changed": True})},
        )
    with pytest.raises(ConflictError):
        await f.service.prepare_consistency_resume(
            f.match_id, BATCH, expected_manifest=previous["source_checkpoint"]
        )


@pytest.mark.asyncio
async def test_failed_resume_can_resume_again_with_original_source_lineage(completed_sources):
    f = completed_sources
    payload = await f.service.prepare_consistency_resume(f.match_id, BATCH)
    next_batch = "batch_" + "2" * 32
    await f.conn.execute(
        text("""
INSERT INTO load_jobs(job_id,kind,state,payload)
VALUES (:id,'full_load_batch','failed',CAST(:payload AS jsonb))
"""),
        {"id": next_batch, "payload": json.dumps(payload)},
    )
    result = await f.service.prepare_consistency_resume(f.match_id, next_batch)
    assert result["resume_from_batch_id"] == next_batch
    assert result["source_batch_id"] == BATCH
    assert result["reused_source_jobs"] == payload["reused_source_jobs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("started_minutes_ago", [8, 15])
async def test_resume_rejects_other_writer_interleaved_between_source_stages(
    completed_sources, started_minutes_ago
):
    f = completed_sources
    await f.conn.execute(text("""
INSERT INTO load_jobs(job_id,kind,state,payload,started_at,finished_at)
VALUES ('중간에끼어든변경','shp_polygons_load','failed','{}',
 now()-make_interval(mins => :minutes),now()-interval '7min')
"""), {"minutes": started_minutes_ago})
    with pytest.raises(ConflictError, match="다른 원천"):
        await f.service.prepare_consistency_resume(f.match_id, BATCH)


@pytest.mark.asyncio
async def test_source_writers_share_but_resume_excludes_them(completed_sources):
    engine = completed_sources.engine
    key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_STATE)
    async with (
        cross_process_lock(engine, key, shared=True),
        cross_process_lock(engine, key, shared=True),
    ):
        with pytest.raises(ConcurrentExecutionError):
            async with cross_process_lock(engine, key):
                pytest.fail("재개가 실행 중인 원천 쓰기를 추월했습니다.")
    async with cross_process_lock(engine, key):
        with pytest.raises(ConcurrentExecutionError):
            async with cross_process_lock(engine, key, shared=True):
                pytest.fail("원천 쓰기가 재개 검사 중에 시작됐습니다.")


@pytest.mark.asyncio
async def test_resume_source_history_lookup_can_use_parent_index(completed_sources):
    conn = completed_sources.conn
    await conn.execute(text("SET LOCAL enable_seqscan=off"))
    plan = await conn.scalar(text("""
EXPLAIN (FORMAT JSON) SELECT job_id, kind, state, payload, started_at, finished_at
FROM public.load_jobs WHERE parent_job_id=:id
AND kind NOT IN ('consistency_check','mv_refresh') ORDER BY created_at
"""), {"id": BATCH})
    indexes = []

    def visit(node):
        if "Index Name" in node:
            indexes.append(node["Index Name"])
        for child in node.get("Plans", []):
            visit(child)

    visit(plan[0]["Plan"])
    assert "idx_load_jobs_parent" in indexes


@pytest_asyncio.fixture
async def repaired_sources(completed_sources, monkeypatch):
    f = completed_sources
    groups = await f.service._build_group_refs(f.conn, f.match_id)
    shp = RebuildGroupRef(
        category="electronic_map_full",
        source_file_group_id=str(uuid4()),
        group_sha256="c" * 64,
        user_yyyymm="202610",
        effective_yyyymm="202610",
        load_kinds=("shp_polygons_load",),
        object_keys=(),
        file_ids=(str(uuid4()), str(uuid4())),
        storage_uris=(),
        files=(),
    )
    monkeypatch.setattr(
        SourceRebuildService, "_build_group_refs", AsyncMock(return_value=(*groups, shp))
    )
    plan = f.service._assemble_plan(f.match_id, (*groups, shp))
    await f.conn.execute(
        text("UPDATE load_jobs SET payload=CAST(:payload AS jsonb) WHERE job_id=:id"),
        {"payload": json.dumps(plan.batch_payload), "id": BATCH},
    )
    shp_payload = next(
        c["payload"] for c in plan.batch_payload["children"] if c["kind"] == "shp_polygons_load"
    )
    await f.conn.execute(
        text("""
INSERT INTO load_jobs(job_id,kind,state,payload,parent_job_id,load_batch_id,started_at,finished_at)
VALUES ('original-shp','shp_polygons_load','done',CAST(:payload AS jsonb),:parent,:parent,
 now()-interval '15min',now()-interval '11min')
"""),
        {"payload": json.dumps(shp_payload), "parent": BATCH},
    )
    abandoned = "batch_" + "3" * 32
    repaired = "batch_" + "4" * 32
    payload = dict(plan.batch_payload)
    payload.update(
        source_batch_id=BATCH,
        repair_from_batch_id=abandoned,
        forced_promotion=False,
        reused_source_jobs=[
            {"job_id": "source-0", "kind": "juso_text_load"},
            {"job_id": "source-1", "kind": "juso_parcel_link_load"},
        ],
        repair_preserved_sidos=["보존시도"],
        repair_remaining_sidos=["복구시도"],
    )
    replacement = dict(
        shp_payload,
        mode="append",
        repair_preserved_sidos=["보존시도"],
        repair_remaining_sidos=["복구시도"],
    )
    payload["children"] = [{"kind": "shp_polygons_load", "payload": replacement}]
    for job_id, state, body in (
        (abandoned, "cancelled", plan.batch_payload),
        (repaired, "failed", payload),
    ):
        await f.conn.execute(
            text("""
INSERT INTO load_jobs(job_id,kind,state,payload)
VALUES (:id,'full_load_batch',:state,CAST(:payload AS jsonb))
"""),
            {"id": job_id, "state": state, "payload": json.dumps(body)},
        )
    for i, child in enumerate(plan.batch_payload["children"]):
        await f.conn.execute(
            text("""
INSERT INTO load_jobs(job_id,kind,state,payload,parent_job_id,load_batch_id,started_at,finished_at)
VALUES (:id,:kind,'cancelled',CAST(:payload AS jsonb),:parent,:parent,
 CASE WHEN :kind='shp_polygons_load' THEN now()-interval '4min' END,now()-interval '3min')
"""),
            {
                "id": f"abandoned-{i}",
                "kind": child["kind"],
                "payload": json.dumps(child["payload"]),
                "parent": abandoned,
            },
        )
    await f.conn.execute(
        text("""
INSERT INTO load_jobs(job_id,kind,state,payload,parent_job_id,load_batch_id,started_at,finished_at)
VALUES ('repaired-shp','shp_polygons_load','done',CAST(:payload AS jsonb),:parent,:parent,
 now()-interval '2min',now()-interval '1min')
"""),
        {"payload": json.dumps(replacement), "parent": repaired},
    )
    await f.conn.execute(
        text("""
INSERT INTO load_manifest(table_name,row_count,source_yyyymm,updated_at)
VALUES ('tl_spbd_buld_polygon',100,'202610',now()-interval '90sec')
""")
    )
    f.repaired = repaired
    f.abandoned = abandoned
    return f


@pytest.mark.asyncio
async def test_repaired_sources_resume_with_genuine_completed_source_ids(repaired_sources):
    f = repaired_sources
    result = await f.service.prepare_consistency_resume(f.match_id, f.repaired)
    assert result["source_batch_id"] == BATCH
    assert result["source_cohort_batch_id"] == f.repaired
    assert {r["job_id"] for r in result["reused_source_jobs"]} == {
        "source-0",
        "source-1",
        "repaired-shp",
    }
    assert "children" not in result and len(result["source_checkpoint"]) == 3
    assert (
        await f.conn.scalar(text("SELECT state FROM load_jobs WHERE job_id=:id"), {"id": BATCH})
        == "failed"
    )
    assert (
        await f.conn.scalar(
            text("SELECT state FROM load_jobs WHERE job_id=:id"), {"id": f.abandoned}
        )
        == "cancelled"
    )
    with pytest.raises(ConflictError, match="다른 원천"):
        await f.service.prepare_consistency_resume(f.match_id, BATCH)


@pytest.mark.asyncio
async def test_repaired_consistency_resume_preserves_cohort_on_repeat(repaired_sources):
    f = repaired_sources
    payload = await f.service.prepare_consistency_resume(f.match_id, f.repaired)
    next_batch = "batch_" + "5" * 32
    await f.conn.execute(
        text("""
INSERT INTO load_jobs(job_id,kind,state,payload)
VALUES (:id,'full_load_batch','failed',CAST(:payload AS jsonb))
"""),
        {"id": next_batch, "payload": json.dumps(payload)},
    )
    result = await f.service.prepare_consistency_resume(f.match_id, next_batch)
    assert result["resume_from_batch_id"] == next_batch
    assert result["source_cohort_batch_id"] == f.repaired
    assert result["reused_source_jobs"] == payload["reused_source_jobs"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "incomplete",
        "changed_file",
        "stale_preserved",
        "wrong_reuse",
        "duplicate_partition",
        "other_abandoned_source_ran",
        "overlap",
        "unknown_writer",
        "earlier_unknown_writer",
        "active_writer",
    ],
)
async def test_repaired_sources_reject_unproven_or_concurrent_history(repaired_sources, change):
    f = repaired_sources
    if change == "incomplete":
        await f.conn.execute(
            text("UPDATE load_jobs SET state='failed' WHERE job_id='repaired-shp'")
        )
    elif change == "changed_file":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET payload=jsonb_set(payload,'{group_sha256}','\"다른해시\"') "
                "WHERE job_id='repaired-shp'"
            )
        )
    elif change == "stale_preserved":
        await f.conn.execute(
            text("UPDATE load_manifest SET updated_at=now() WHERE table_name='tl_juso_text'")
        )
    elif change == "wrong_reuse":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET payload=jsonb_set(payload,"
                "'{reused_source_jobs,0,job_id}','\"original-shp\"') WHERE job_id=:id"
            ),
            {"id": f.repaired},
        )
    elif change == "duplicate_partition":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET payload=jsonb_set(payload,"
                "'{repair_remaining_sidos}',CAST(:names AS jsonb)) "
                "WHERE job_id IN (:root,'repaired-shp')"
            ),
            {"root": f.repaired, "names": json.dumps(["보존시도"])},
        )
    elif change == "other_abandoned_source_ran":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET started_at=now()-interval '4min' "
                "WHERE parent_job_id=:id AND kind='juso_text_load'"
            ),
            {"id": f.abandoned},
        )
    elif change == "overlap":
        await f.conn.execute(
            text(
                "UPDATE load_jobs SET finished_at=now() "
                "WHERE parent_job_id=:id AND kind='shp_polygons_load'"
            ),
            {"id": f.abandoned},
        )
    else:
        await f.conn.execute(
            text("""
INSERT INTO load_jobs(job_id,kind,state,payload,started_at,finished_at)
VALUES ('unknown-shp','shp_polygons_load',:state,'{}',
 now()-make_interval(mins => :minutes),now()-make_interval(mins => :minutes)+interval '1min')
"""),
            {
                "state": "running" if change == "active_writer" else "failed",
                "minutes": 14 if change == "earlier_unknown_writer" else 2,
            },
        )
    with pytest.raises(ConflictError):
        await f.service.prepare_consistency_resume(f.match_id, f.repaired)
