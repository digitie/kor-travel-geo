import asyncio
import sys
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.engine import create_engine, get_session
from kraddr.geo.settings import Settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    engine_obj = create_engine(Settings())
    yield engine_obj
    await engine_obj.dispose()


@pytest.mark.asyncio
async def test_engine_connection_and_session(engine: AsyncEngine) -> None:
    # Check connection
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

    # Check session generator
    async for session in get_session(engine):
        result2 = await session.execute(text("SELECT 2"))
        assert result2.scalar() == 2
        break
