"""DB 수명주기 capability의 Dagster측 방어선 (T-312, T-321).

geo admin API는 hot-swap / restore drill / blue-green scratch full-load / ``db_restore``를
연결 role이 실행할 수 없는 instance(공용 PostgreSQL instance의 app role — ``CREATEDB`` 없음,
maintenance DB ``postgres`` ``CONNECT`` 없음)에서 job을 만들기 전에 ``E0410``으로 거절한다.
Dagster UI에서 run을 직접 launch하거나 schedule(daily restore drill)이 돌면 API를 거치지
않으므로, 해당 op도 시작하자마자 같은 판정을 보고 명확한 메시지의 ``Failure``로 멈춘다 —
``CREATE DATABASE`` 단계의 raw ``permission denied``까지 가지 않는다.

schedule은 한 단계 앞에서 거른다(T-321): 운영자가 공용 instance에서 daily restore drill
schedule을 켜도 매일 ``Failure`` run이 쌓이지 않도록 tick 평가가 ``SkipReason``을 돌려준다.
op guard는 수동 launch용 2차 방어선으로 남는다.

이 모듈에는 ``@op``가 없으므로 ``from __future__ import annotations``를 써도 된다
(dagster-boundary §10은 decorated module만 금지한다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dagster import Failure, SkipReason
from kortravelgeo.exceptions import UnsupportedOnInstanceError

from .resources import run_coroutine_blocking

if TYPE_CHECKING:
    import logging

    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.dto.admin import DbLifecycleFeature

__all__ = ["db_lifecycle_skip_reason", "refuse_unsupported_db_lifecycle"]


def _unsupported_description(exc: UnsupportedOnInstanceError) -> str:
    detail = f" ({exc.hint})" if exc.hint else ""
    return f"{exc.message}{detail}"


async def refuse_unsupported_db_lifecycle(
    client: AsyncAddressClient, feature: DbLifecycleFeature
) -> None:
    """``feature``를 이 instance에서 실행할 수 없으면 사유를 담은 ``Failure``를 던진다."""
    try:
        await client.require_db_lifecycle(feature)
    except UnsupportedOnInstanceError as exc:
        raise Failure(description=_unsupported_description(exc)) from exc


def db_lifecycle_skip_reason(
    client: AsyncAddressClient,
    feature: DbLifecycleFeature,
    log: logging.Logger,
) -> SkipReason | None:
    """schedule tick 평가용: ``feature``를 실행할 수 없는 instance면 ``SkipReason``을 돌려준다.

    판정 자체가 실패하면(DB 연결 불가 등) 건너뛰지 않고 ``None``을 돌려준다 — run을 만들면
    op guard가 같은 판정을 다시 하고, 실패는 run-failure sensor 경로로 알림이 간다(tick 오류는
    알림이 없다).
    """
    try:
        run_coroutine_blocking(client.require_db_lifecycle(feature))
    except UnsupportedOnInstanceError as exc:
        return SkipReason(_unsupported_description(exc))
    except Exception as exc:
        log.warning(
            "DB lifecycle capability check failed; launching the run so its op guard decides: "
            "%s: %s",
            type(exc).__name__,
            exc,
        )
    return None
