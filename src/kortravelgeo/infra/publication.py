"""작업 소유권과 중지 요청을 실제 게시 transaction에 결합한다."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kortravelgeo.infra.load_job_executor import LoadJobLeaseLostError

PublicationGuard = Callable[[AsyncConnection], Awaitable[None]]


def load_job_publication_guard(
    *,
    job_id: str,
    owner_run_id: str,
    cancel_event: asyncio.Event,
    parent_job_id: str | None = None,
) -> PublicationGuard:
    """게시가 commit될 때까지 소유 행을 잠근다. API/CLI 수동 경로에는 강제하지 않는다."""
    job_ids = sorted({job_id, *([parent_job_id] if parent_job_id else [])})

    async def guard(conn: AsyncConnection) -> None:
        if cancel_event.is_set():
            raise LoadJobLeaseLostError("중지된 작업은 serving 결과를 게시할 수 없습니다.")
        await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        for owned_id in job_ids:
            active = await conn.scalar(
                text("""
SELECT 1 FROM load_jobs
 WHERE job_id = :job_id AND state = 'running' AND executor = 'dagster'
   AND orchestrator_run_id = :owner_run_id
 FOR UPDATE
"""),
                {"job_id": owned_id, "owner_run_id": owner_run_id},
            )
            if active != 1:
                raise LoadJobLeaseLostError(f"load job {owned_id} 게시 소유권이 만료되었습니다.")
        if cancel_event.is_set():
            raise LoadJobLeaseLostError("게시 중 중지 요청을 확인했습니다.")

    return guard
