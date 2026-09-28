"""T-312: 연결 DB role이 DB 수명주기 기능을 실행할 수 있는지 판정하고 일찍 거절한다.

공용 control-plane PostgreSQL instance(T-308)에서 geo app role은 ``NOSUPERUSER``/
``NOCREATEDB``이고 maintenance DB ``postgres``에 ``CONNECT`` 권한도 없다. 그런데 다음 기능은
모두 ``CREATE DATABASE``/``ALTER DATABASE RENAME``(= ``CREATEDB`` 필요)과 maintenance DB 연결을
전제로 한다.

- ``hot_swap`` — ADR-036 plan/execute/rollback (maintenance DB에서 ``ALTER DATABASE RENAME``)
- ``restore_drill`` — T-242 throwaway DB ``CREATE DATABASE`` → 복원 → ``DROP DATABASE``
- ``scratch_full_load`` — T-290j blue-green scratch DB ``CREATE DATABASE``
- ``db_restore`` — ADR-030 새 DB/``replace_current`` 복원 (실패 시 대상 DB drop/quarantine)

그래서 이 기능들은 job을 만든 뒤 raw DB 오류(``permission denied to create database`` 등)로
늦게 실패했다. 이 모듈은 role 속성을 한 번 조회해 캐시하고(TTL 5분), 게이트가 job을 만들기
전에 :class:`UnsupportedOnInstanceError` (``E0410``/HTTP 409)로 거절하게 한다.

``KTG_DB_LIFECYCLE_MODE``:

- ``auto`` (기본) — role을 조회한다. ``CREATEDB``(또는 superuser)이고 maintenance DB에
  ``CONNECT``할 수 있으면 지원. 전용 superuser instance(dev/테스트)는 그대로 전부 허용된다.
- ``enabled`` — 조회 없이 허용 (운영자가 권한을 따로 준 경우의 override).
- ``disabled`` — 조회 없이 차단.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from kortravelgeo.dto.admin import DbLifecycleCapabilities, DbLifecycleFeature, DbLifecycleMode
from kortravelgeo.exceptions import UnsupportedOnInstanceError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.settings import Settings

__all__ = [
    "DB_LIFECYCLE_FEATURES",
    "DB_LIFECYCLE_UNSUPPORTED_MESSAGE",
    "MAINTENANCE_DATABASE",
    "DbRoleProbe",
    "clear_db_capability_cache",
    "db_lifecycle_capabilities",
    "evaluate_db_lifecycle",
    "probe_db_role",
    "require_db_lifecycle",
]

#: hot-swap/restore drill/scratch/cleanup가 ``CREATE``/``DROP``/``RENAME DATABASE``에 쓰는 DB.
MAINTENANCE_DATABASE: Final = "postgres"

DB_LIFECYCLE_FEATURES: Final[tuple[DbLifecycleFeature, ...]] = (
    "hot_swap",
    "restore_drill",
    "scratch_full_load",
    "db_restore",
)

DB_LIFECYCLE_UNSUPPORTED_MESSAGE: Final = (
    "공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행"
)

_FEATURE_LABELS: Final[dict[DbLifecycleFeature, str]] = {
    "hot_swap": "restore hot-swap",
    "restore_drill": "restore drill",
    "scratch_full_load": "blue-green scratch full-load",
    "db_restore": "DB 복원",
}

#: role 권한은 운영자가 바꿀 때만 달라진다 — 요청마다 catalog를 읽지 않도록 5분 캐시한다.
_PROBE_TTL_SECONDS: Final = 300.0

_PROBE_SQL: Final = text(
    """
SELECT current_user::text AS role,
       r.rolsuper AS is_superuser,
       (r.rolsuper OR r.rolcreatedb) AS can_create_database,
       COALESCE(
           (SELECT has_database_privilege(d.oid, 'CONNECT')
              FROM pg_database d
             WHERE d.datname = :maintenance_database),
           false
       ) AS can_connect_maintenance_database
  FROM pg_roles r
 WHERE r.rolname = current_user
"""
)


@dataclass(frozen=True, slots=True)
class DbRoleProbe:
    """연결 role의 DB 수명주기 관련 속성 (``pg_roles`` + maintenance DB ``CONNECT``)."""

    role: str
    is_superuser: bool
    can_create_database: bool
    can_connect_maintenance_database: bool


_probe_cache: dict[str, tuple[float, DbRoleProbe]] = {}


def clear_db_capability_cache() -> None:
    """캐시된 role probe를 비운다 (테스트·권한 변경 직후용)."""
    _probe_cache.clear()


async def probe_db_role(engine: AsyncEngine) -> DbRoleProbe:
    """연결 role의 속성을 캐시 없이 읽는다.

    ``has_database_privilege``에 DB 이름 대신 ``pg_database``에서 찾은 oid를 넘기므로
    maintenance DB가 없는 cluster에서도 오류 대신 ``False``가 된다.
    """
    async with engine.connect() as conn:
        row = (
            (await conn.execute(_PROBE_SQL, {"maintenance_database": MAINTENANCE_DATABASE}))
            .mappings()
            .one()
        )
    return DbRoleProbe(
        role=str(row["role"]),
        is_superuser=bool(row["is_superuser"]),
        can_create_database=bool(row["can_create_database"]),
        can_connect_maintenance_database=bool(row["can_connect_maintenance_database"]),
    )


async def _cached_probe(engine: AsyncEngine) -> DbRoleProbe:
    # password를 가린 URL(드라이버·role·host·port·DB)이 key — role/instance가 다르면 따로 조회한다.
    key = engine.url.render_as_string(hide_password=True)
    now = monotonic()
    cached = _probe_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    probe = await probe_db_role(engine)
    _probe_cache[key] = (now + _PROBE_TTL_SECONDS, probe)
    return probe


def evaluate_db_lifecycle(
    mode: DbLifecycleMode,
    probe: DbRoleProbe | None,
    *,
    checked_at: datetime,
) -> DbLifecycleCapabilities:
    """``mode``와 role probe로 지원 여부·사유를 계산한다 (pure).

    ``auto``에서는 ``CREATEDB``(superuser 포함)와 maintenance DB ``CONNECT``가 둘 다 있어야
    지원한다. ``enabled``/``disabled``는 probe 없이(``probe=None``) 결정한다.
    """
    if mode == "enabled":
        return DbLifecycleCapabilities(
            mode=mode, supported=True, features=DB_LIFECYCLE_FEATURES, checked_at=checked_at
        )
    if mode == "disabled":
        return DbLifecycleCapabilities(
            mode=mode,
            supported=False,
            features=DB_LIFECYCLE_FEATURES,
            reason="KTG_DB_LIFECYCLE_MODE=disabled",
            checked_at=checked_at,
        )
    if probe is None:
        msg = "db lifecycle mode 'auto' requires a role probe"
        raise ValueError(msg)
    missing: list[str] = []
    if not probe.can_create_database:
        missing.append("CREATEDB 권한 없음")
    if not probe.can_connect_maintenance_database:
        missing.append(f"maintenance DB '{MAINTENANCE_DATABASE}' CONNECT 권한 없음")
    return DbLifecycleCapabilities(
        mode=mode,
        supported=not missing,
        features=DB_LIFECYCLE_FEATURES,
        reason=f"role {probe.role}: {', '.join(missing)}" if missing else None,
        role=probe.role,
        is_superuser=probe.is_superuser,
        can_create_database=probe.can_create_database,
        can_connect_maintenance_database=probe.can_connect_maintenance_database,
        checked_at=checked_at,
    )


async def db_lifecycle_capabilities(
    engine: AsyncEngine, settings: Settings
) -> DbLifecycleCapabilities:
    """현재 설정·연결 role 기준 DB 수명주기 기능 지원 여부 (``auto``만 DB를 조회한다)."""
    mode = settings.db_lifecycle_mode
    probe = await _cached_probe(engine) if mode == "auto" else None
    return evaluate_db_lifecycle(mode, probe, checked_at=datetime.now(UTC))


async def require_db_lifecycle(
    engine: AsyncEngine, settings: Settings, feature: DbLifecycleFeature
) -> None:
    """``feature``를 지원하지 않는 instance면 job을 만들기 전에 E0410/409로 거절한다."""
    capabilities = await db_lifecycle_capabilities(engine, settings)
    if capabilities.supported:
        return
    raise UnsupportedOnInstanceError(
        f"{_FEATURE_LABELS[feature]}: {DB_LIFECYCLE_UNSUPPORTED_MESSAGE}",
        hint=capabilities.reason,
    )
