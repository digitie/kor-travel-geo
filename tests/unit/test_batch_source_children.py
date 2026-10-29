"""준비 작업이 같은 배치에 연결돼도 실제 자식만 순서대로 고른다."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine

from kortravelgeo.loaders.batch_dag import _fetch_source_children

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_source_children_exclude_linked_upstream_prepare_job() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    jobs = Table(
        "load_jobs", metadata,
        Column("job_id", String, primary_key=True), Column("kind", String),
        Column("payload", JSON), Column("load_batch_id", String),
        Column("parent_job_id", String), Column("created_at", String),
    )
    metadata.create_all(engine)
    rows = [
        ("prepare", "source_rebuild_db", None, "0"),
        ("batch", "full_load_batch", None, "1"),
        ("source-second", "locsum_load", "batch", "3"),
        ("source-first", "juso_text_load", "batch", "2"),
    ]
    with engine.begin() as conn:
        conn.execute(jobs.insert(), [
            {"job_id": job_id, "kind": kind, "payload": {"path": job_id},
             "load_batch_id": "batch", "parent_job_id": parent, "created_at": order}
            for job_id, kind, parent, order in rows
        ])

    class Connection:
        async def execute(self, statement: Any, parameters: Any) -> Any:
            with engine.connect() as conn:
                return conn.execute(statement.columns(payload=JSON), parameters)

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield Connection()

    try:
        actual = await _fetch_source_children(cast("AsyncEngine", Engine()), "batch")
        assert actual == [
            ("source-first", "juso_text_load", {"path": "source-first"}),
            ("source-second", "locsum_load", {"path": "source-second"}),
        ]
    finally:
        engine.dispose()
