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
