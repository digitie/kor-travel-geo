from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from kraddr.geo.settings import Settings, get_settings


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    if settings is None:
        settings = get_settings()

    connect_args = {"options": f"-c statement_timeout={settings.pg_statement_timeout_ms}"}

    return create_async_engine(
        settings.pg_dsn,
        pool_size=settings.pg_pool_size,
        max_overflow=settings.pg_max_overflow,
        pool_recycle=settings.pg_pool_recycle_s,
        connect_args=connect_args,
        echo=False,
    )


async def get_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
