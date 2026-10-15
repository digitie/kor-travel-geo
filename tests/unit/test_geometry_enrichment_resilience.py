"""요청 내부 geometry 조회 공유와 보조 단계 실패 격리 회귀."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.protocols import GeometryLookup
from kortravelgeo.dto.v2 import CandidateV2, GeometryV2, PointV2
from kortravelgeo.exceptions import GeometryTimeoutError
from kortravelgeo.infra.geometry_repo import GeometryRepository


def candidate(**updates: Any) -> CandidateV2:
    return CandidateV2(
        confidence=0.97,
        match_kind="road",
        point=PointV2(lon=127.036, lat=37.501),
        metadata={
            "bd_mgt_sn": "building-1", "rncode_full": "road-1",
            "bjd_cd": "dong-1", "detail": "152",
        },
    ).model_copy(update=updates)


def polygon() -> GeometryLookup:
    return GeometryLookup(kind="building", geometry=GeometryV2(
        kind="building", geojson={"type": "Polygon", "coordinates": []},
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [True, False])
async def test_identical_building_query_is_shared_only_within_one_request(
    monkeypatch: pytest.MonkeyPatch, found: bool,
) -> None:
    calls: list[dict[str, Any]] = []

    async def lookup(self: GeometryRepository, **kwargs: Any) -> GeometryLookup | None:
        calls.append(kwargs)
        return polygon() if found else None

    monkeypatch.setattr(GeometryRepository, "building_geometry", lookup)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    road = candidate()
    parcel = candidate(match_kind="parcel")
    first = await client._enrich_candidates_with_geometry((road, parcel), include_geometry=True)
    assert len(calls) == 1
    assert len(first) == 2
    assert first[0].point == road.point and first[1].point == parcel.point
    assert (first[0].geometry is not None) is found
    await client._enrich_candidates_with_geometry((road, parcel), include_geometry=True)
    assert len(calls) == 2  # 별도 요청은 miss와 geometry 객체를 전역 보존하지 않는다.


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["bd_mgt_sn", "rncode_full", "bjd_cd", "detail"])
async def test_every_actual_lookup_argument_participates_in_memo_key(
    monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    calls: list[dict[str, Any]] = []

    async def lookup(self: GeometryRepository, **kwargs: Any) -> GeometryLookup:
        calls.append(kwargs)
        return polygon()

    monkeypatch.setattr(GeometryRepository, "building_geometry", lookup)
    first = candidate()
    second = candidate(metadata={**first.metadata, field: "different"})
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    await client._enrich_candidates_with_geometry((first, second), include_geometry=True)
    assert len(calls) == 2
    assert calls[0][field] != calls[1][field]


@pytest.mark.asyncio
async def test_existing_geometry_is_kept_without_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(self: GeometryRepository, **kwargs: Any) -> None:
        raise AssertionError("이미 확보한 geometry를 다시 조회하면 안 된다")

    monkeypatch.setattr(GeometryRepository, "building_geometry", forbidden)
    existing = candidate(geometry=polygon().geometry)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    result = await client._enrich_candidates_with_geometry((existing,), include_geometry=True)
    assert result[0] is existing


@pytest.mark.asyncio
async def test_no_geometry_option_does_not_query_or_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(self: GeometryRepository, **kwargs: Any) -> None:
        raise AssertionError("geometry 미선택 요청에서 조회하면 안 된다")

    monkeypatch.setattr(GeometryRepository, "building_geometry", forbidden)
    candidates = (candidate(),)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    result = await client._enrich_candidates_with_geometry(candidates, include_geometry=False)
    assert result is candidates


@pytest.mark.asyncio
async def test_optional_timeout_keeps_points_and_marks_partial_failure_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def timeout(self: GeometryRepository, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise GeometryTimeoutError("보조 geometry 조회 제한 시간 초과")

    monkeypatch.setattr(GeometryRepository, "building_geometry", timeout)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    road, parcel = candidate(), candidate(match_kind="parcel")
    result = await client._enrich_candidates_with_geometry((road, parcel), include_geometry=True)
    assert calls == 1
    for before, after in zip((road, parcel), result, strict=True):
        assert after.point == before.point and after.confidence == before.confidence
        assert after.metadata == before.metadata
        assert after.geometry is None
        assert after.geometry_error is not None
        assert after.geometry_error.model_dump() == {"code": "statement_timeout", "retryable": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_geometry_timeout_without_primary_point_is_not_success(
    monkeypatch: pytest.MonkeyPatch, cached: bool,
) -> None:
    async def timeout(self: GeometryRepository, **kwargs: Any) -> None:
        raise GeometryTimeoutError("timeout")

    monkeypatch.setattr(GeometryRepository, "building_geometry", timeout)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    candidates = (candidate(), candidate(point=None)) if cached else (candidate(point=None),)
    with pytest.raises(GeometryTimeoutError):
        await client._enrich_candidates_with_geometry(candidates, include_geometry=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("schema bug"), asyncio.CancelledError()])
async def test_programming_and_caller_cancellation_propagate(
    monkeypatch: pytest.MonkeyPatch, error: BaseException,
) -> None:
    async def failed(self: GeometryRepository, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(GeometryRepository, "building_geometry", failed)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    with pytest.raises(type(error)):
        await client._enrich_candidates_with_geometry((candidate(),), include_geometry=True)


class DriverError(Exception):
    def __init__(self, sqlstate: str | None, message: str) -> None:
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(message_primary=message)
        super().__init__(message)


class FailedEngine:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.exits = 0

    @asynccontextmanager
    async def connect(self) -> Any:
        try:
            yield self
        finally:
            self.exits += 1

    async def execute(self, *_: Any) -> None:
        raise self.error

    def begin(self) -> Any:
        return self.connect()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["building", "region", "road"])
@pytest.mark.parametrize("sqlstate,message,partial", [
    ("57014", "canceling statement due to statement timeout", True),
    ("57014", "canceling statement due to user request", False),
    ("55P03", "canceling statement due to lock timeout", False),
    ("42601", "syntax error near statement timeout", False),
    (None, "connection timed out", False),
])
async def test_only_confirmed_statement_timeout_becomes_optional_geometry_error(
    kind: str, sqlstate: str | None, message: str, partial: bool,
) -> None:
    original = OperationalError("SELECT geometry", {}, DriverError(sqlstate, message))
    engine = FailedEngine(original)
    repo = GeometryRepository(engine)  # type: ignore[arg-type]
    expected = GeometryTimeoutError if partial else OperationalError
    with pytest.raises(expected) as raised:
        if kind == "building":
            await repo.building_geometry(bd_mgt_sn="building-1")
        elif kind == "region":
            await repo.region_geometry(sig_cd="11680")
        else:
            await repo.road_geometries("테헤란로")
    assert engine.exits == 1  # 오류가 나도 요청의 connection context는 반드시 종료된다.
    if partial:
        assert raised.value.__cause__ is original
    else:
        assert raised.value is original


@pytest.mark.asyncio
async def test_driver_cancellation_remains_cancellation_and_releases_connection() -> None:
    error = asyncio.CancelledError()
    engine = FailedEngine(error)
    repo = GeometryRepository(engine)  # type: ignore[arg-type]
    with pytest.raises(asyncio.CancelledError):
        await repo.building_geometry(bd_mgt_sn="building-1")
    assert engine.exits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["building", "region", "road"])
@pytest.mark.parametrize(
    "diagnostic", ["missing_diag", "missing_primary", "nonstring_primary", "user_cancel_primary"],
)
async def test_ambiguous_detail_never_becomes_confirmed_geometry_timeout(
    kind: str, diagnostic: str,
) -> None:
    driver = DriverError(
        "57014",
        "canceling statement due to user request\nDETAIL: unrelated statement timeout text",
    )
    if diagnostic == "missing_diag":
        del driver.diag
    elif diagnostic == "missing_primary":
        driver.diag = SimpleNamespace()
    elif diagnostic == "nonstring_primary":
        driver.diag = SimpleNamespace(message_primary=123)
    else:
        driver.diag = SimpleNamespace(message_primary="canceling statement due to user request")
    original = OperationalError("SELECT geometry", {}, driver)
    engine = FailedEngine(original)
    repo = GeometryRepository(engine)  # type: ignore[arg-type]
    with pytest.raises(OperationalError) as raised:
        if kind == "building":
            await repo.building_geometry(bd_mgt_sn="building-1")
        elif kind == "region":
            await repo.region_geometry(sig_cd="11680")
        else:
            await repo.road_geometries("테헤란로")
    assert raised.value is original
    assert engine.exits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("programming", [False, True])
async def test_ambiguous_database_error_is_not_a_partial_point_success(programming: bool) -> None:
    driver = DriverError(
        "42601" if programming else "57014",
        "unconfirmed database failure\nDETAIL: unrelated statement timeout text",
    )
    driver.diag = SimpleNamespace()
    error_type = ProgrammingError if programming else OperationalError
    original = error_type("SELECT geometry", {}, driver)
    client = AsyncAddressClient(engine=FailedEngine(original))  # type: ignore[arg-type]
    with pytest.raises(error_type) as raised:
        await client._enrich_candidates_with_geometry((candidate(),), include_geometry=True)
    assert raised.value is original


def test_geometry_metrics_do_not_accept_address_or_error_text_as_labels() -> None:
    from kortravelgeo.infra import metrics

    metrics.record_geometry_lookup(kind="private-address", outcome="private-SQL", elapsed_s=1.0)
    body = metrics.render_prometheus().decode()
    assert 'ktg_geometry_lookup_duration_seconds_count{kind="other",outcome="other"}' in body
    assert "private-address" not in body and "private-SQL" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_repository_records_geometry_boundary_without_raw_error_labels(
    monkeypatch: pytest.MonkeyPatch, cancelled: bool,
) -> None:
    from kortravelgeo.infra import geometry_repo

    observations: list[dict[str, Any]] = []
    monkeypatch.setattr(
        geometry_repo, "record_geometry_lookup", lambda **kw: observations.append(kw),
    )
    error = asyncio.CancelledError() if cancelled else OperationalError(
        "private SQL", {}, DriverError("57014", "canceling statement due to statement timeout"),
    )
    repo = GeometryRepository(FailedEngine(error))  # type: ignore[arg-type]
    with pytest.raises(asyncio.CancelledError if cancelled else GeometryTimeoutError):
        await repo.building_geometry(bd_mgt_sn="private-building")
    assert len(observations) == 1
    assert observations[0]["kind"] == "building"
    assert observations[0]["outcome"] == ("cancelled" if cancelled else "statement_timeout")
    assert observations[0]["elapsed_s"] >= 0
    assert set(observations[0]) == {"kind", "outcome", "elapsed_s"}
