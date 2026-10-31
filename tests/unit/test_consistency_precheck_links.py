from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kortravelgeo.loaders import batch_dag


@pytest.mark.asyncio
async def test_consistency_resolves_links_before_reading_entrances(monkeypatch):
    events = []
    engine = object()
    report = SimpleNamespace(report_id="report-1", severity_max="WARN")

    async def resolve(received_engine):
        assert received_engine is engine
        events.append("resolved")

    async def cases(received_engine, **kwargs):
        assert received_engine is engine
        assert events == ["resolved"]
        events.append("checked")
        return report

    monkeypatch.setattr(batch_dag, "resolve_text_geometry_links", resolve)
    monkeypatch.setattr(batch_dag, "run_all_cases", cases)
    result = await batch_dag.run_consistency_check(
        engine, payload={"load_batch_id": "batch-1"}, progress=AsyncMock()
    )
    assert result is report
    assert events == ["resolved", "checked"]


@pytest.mark.asyncio
async def test_failed_link_resolution_does_not_publish_a_consistency_report(monkeypatch):
    resolve = AsyncMock(side_effect=RuntimeError("link resolution failed"))
    cases = AsyncMock()
    monkeypatch.setattr(batch_dag, "resolve_text_geometry_links", resolve)
    monkeypatch.setattr(batch_dag, "run_all_cases", cases)

    with pytest.raises(RuntimeError, match="link resolution failed"):
        await batch_dag.run_consistency_check(
            object(), payload={"load_batch_id": "batch-1"}, progress=AsyncMock()
        )
    cases.assert_not_awaited()
