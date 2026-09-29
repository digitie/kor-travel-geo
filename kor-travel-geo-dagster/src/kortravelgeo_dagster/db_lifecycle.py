"""DB 수명주기 capability의 Dagster측 2차 방어선 (T-312).

geo admin API는 hot-swap / restore drill / blue-green scratch full-load / ``db_restore``를
연결 role이 실행할 수 없는 instance(공용 PostgreSQL instance의 app role — ``CREATEDB`` 없음,
maintenance DB ``postgres`` ``CONNECT`` 없음)에서 job을 만들기 전에 ``E0410``으로 거절한다.
Dagster UI에서 run을 직접 launch하거나 schedule(daily restore drill)이 돌면 API를 거치지
않으므로, 해당 op도 시작하자마자 같은 판정을 보고 명확한 메시지의 ``Failure``로 멈춘다 —
``CREATE DATABASE`` 단계의 raw ``permission denied``까지 가지 않는다.

이 모듈에는 ``@op``가 없으므로 ``from __future__ import annotations``를 써도 된다
(dagster-boundary §10은 decorated module만 금지한다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dagster import Failure
from kortravelgeo.exceptions import UnsupportedOnInstanceError

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.dto.admin import DbLifecycleFeature

__all__ = ["refuse_unsupported_db_lifecycle"]


async def refuse_unsupported_db_lifecycle(
    client: AsyncAddressClient, feature: DbLifecycleFeature
) -> None:
    """``feature``를 이 instance에서 실행할 수 없으면 사유를 담은 ``Failure``를 던진다."""
    try:
        await client.require_db_lifecycle(feature)
    except UnsupportedOnInstanceError as exc:
        detail = f" ({exc.hint})" if exc.hint else ""
        raise Failure(description=f"{exc.message}{detail}") from exc
