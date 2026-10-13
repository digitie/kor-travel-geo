"""T-325a/b unit coverage: data_token derivation, fingerprint SQL shape and fail-open,
activation-helper ordering, the v2 ``dataset`` stamp and its TTL cache (ADR-069)."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.core.dataset_version import (
    DATA_TOKEN_RE,
    derive_data_token,
    derive_version_token,
)
from kortravelgeo.dto.v2 import (
    DatasetRef,
    DatasetVersionEntry,
    GeocodeV2Input,
    GeocodeV2Response,
    RegionsWithinRadiusInput,
    RegionsWithinRadiusResponse,
    RegionWithinRadiusCenter,
    ReverseV2Input,
    ReverseV2Response,
    SearchV2Input,
    SearchV2Response,
)
from kortravelgeo.infra import admin_repo, data_fingerprint
from kortravelgeo.infra.data_fingerprint import (
    DATA_FINGERPRINT_SQL,
    DATA_FINGERPRINT_TABLE_SPECS,
    compute_data_fingerprint,
)
from kortravelgeo.infra.dataset_ref import DatasetRefCache

_VERSION = derive_version_token("00000000-0000-0000-0000-000000000001")
_DATA = derive_data_token("0123456789abcdef0123456789abcdef")

# --- derivation -------------------------------------------------------------------------------


def test_derive_data_token_is_prefixed_sha256_of_the_fingerprint() -> None:
    import hashlib

    fingerprint = "0123456789abcdef0123456789abcdef"
    token = derive_data_token(fingerprint)
    assert token == "dd1-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    assert token is not None and DATA_TOKEN_RE.match(token)
    assert derive_data_token("ffffffffffffffffffffffffffffffff") != token


@pytest.mark.parametrize("fingerprint", [None, ""])
def test_missing_fingerprint_has_no_data_token(fingerprint: str | None) -> None:
    assert derive_data_token(fingerprint) is None


def test_dataset_ref_and_version_entry_enforce_token_patterns() -> None:
    assert DatasetRef(version_token=_VERSION, data_token=_DATA).data_token == _DATA
    with pytest.raises(ValidationError):
        DatasetRef(version_token="dv1-nothex", data_token=None)
    with pytest.raises(ValidationError):
        DatasetRef(version_token=_VERSION, data_token=_VERSION)  # wrong prefix


def test_version_entry_omits_absent_data_token_on_the_wire() -> None:
    from datetime import UTC, datetime

    entry = DatasetVersionEntry(
        version_token=_VERSION, activated_at=datetime.now(UTC), change_type="full"
    )
    assert "data_token" not in entry.model_dump(exclude_none=True)
    with_token = entry.model_copy(update={"data_token": _DATA})
    assert with_token.model_dump(exclude_none=True)["data_token"] == _DATA


# --- fingerprint SQL shape --------------------------------------------------------------------


def test_fingerprint_sql_scans_every_spec_table() -> None:
    for spec in DATA_FINGERPRINT_TABLE_SPECS:
        assert f"FROM public.{spec.name} t)" in DATA_FINGERPRINT_SQL
        assert f"'{spec.name}'::text AS table_name" in DATA_FINGERPRINT_SQL


def test_fingerprint_sql_geometry_rules() -> None:
    sql = DATA_FINGERPRINT_SQL
    # point exact, ST_Transform product dropped (ADR-069 D2/D3)
    assert "coalesce(md5(ST_AsBinary(t.pt_5179)), '')" in sql
    assert "pt_4326" not in sql
    # polygons/lines summarized, never hashed as full WKB or serialized as GeoJSON
    assert "concat(ST_NPoints(t.geom), '|', Box2D(t.geom)::text)" in sql
    assert "ST_AsBinary(t.geom)" not in sql
    assert "to_jsonb" not in sql
    assert "ROW(t.geom" not in sql and ", t.geom," not in sql and ", t.geom)" not in sql
    # load metadata and the reload surrogate key never hashed
    for column in ("source_file", "source_yyyymm", "loaded_at", "refreshed_at", "bulk_id"):
        assert f"t.{column}" not in sql
    assert (
        "md5(string_agg(table_name || ':' || coalesce(h, 0)::text, ','"
        ' ORDER BY table_name COLLATE "C"))'
        in sql
    )


class _Nested:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def rollback(self) -> None:
        self.log.append("ROLLBACK TO SAVEPOINT")


class _OrigError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("boom")
        self.sqlstate = sqlstate


class _DBError(Exception):
    def __init__(self, orig: BaseException) -> None:
        super().__init__("wrapped")
        self.orig = orig


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


def _live_columns(drop: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for spec in DATA_FINGERPRINT_TABLE_SPECS:
        columns = [*sorted(spec.accounted_columns), "loaded_at"]
        if spec.name == drop:
            columns.append("new_unhashed_col")
        rows.append({"table_name": spec.name, "columns": columns})
    return rows


class _FingerprintConn:
    def __init__(
        self, *, fail: BaseException | None = None, drift_table: str | None = None
    ) -> None:
        self.log: list[str] = []
        self.fail = fail
        self.drift_table = drift_table

    async def begin_nested(self) -> _Nested:
        self.log.append("SAVEPOINT")
        return _Nested(self.log)

    async def execute(self, statement: Any, params: Any = None) -> _Rows:
        sql = str(statement)
        self.log.append(sql.strip().splitlines()[0])
        if "pg_attribute" in sql:
            return _Rows(_live_columns(self.drift_table))
        if sql == DATA_FINGERPRINT_SQL:
            if self.fail is not None:
                raise self.fail
            return _Rows(
                [
                    {"table_name": "mv_geocode_target", "h": 12, "fingerprint": "f" * 32},
                    {"table_name": "tl_scco_sig", "h": None, "fingerprint": "f" * 32},
                ]
            )
        return _Rows([])


@pytest.mark.asyncio
async def test_compute_fingerprint_runs_inside_a_savepoint_that_is_always_rolled_back() -> None:
    conn = _FingerprintConn()
    result = await compute_data_fingerprint(conn)

    assert result.fingerprint == "f" * 32
    assert result.error_code is None
    assert result.table_hashes == {"mv_geocode_target": "12", "tl_scco_sig": None}
    assert conn.log[0] == "SAVEPOINT"
    assert conn.log[1] == "SET LOCAL statement_timeout = '10min'"
    assert conn.log[-1] == "ROLLBACK TO SAVEPOINT"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (_DBError(_OrigError("57014")), "timeout"),
        (_DBError(_OrigError("42P01")), "exception:_OrigError"),
        (RuntimeError("no orig"), "exception:RuntimeError"),
    ],
)
@pytest.mark.asyncio
async def test_compute_fingerprint_fails_open_with_an_error_code(
    error: BaseException, code: str
) -> None:
    conn = _FingerprintConn(fail=error)
    result = await compute_data_fingerprint(conn)

    assert result.fingerprint is None
    assert result.error_code == code
    assert conn.log[-1] == "ROLLBACK TO SAVEPOINT"


@pytest.mark.asyncio
async def test_compute_fingerprint_fails_open_on_schema_drift_before_scanning() -> None:
    conn = _FingerprintConn(drift_table="tl_sprd_manage")
    result = await compute_data_fingerprint(conn)

    assert result.fingerprint is None
    assert result.error_code == "schema_drift:tl_sprd_manage"
    assert not any(line.startswith("WITH parts") for line in conn.log)
    assert conn.log[-1] == "ROLLBACK TO SAVEPOINT"


def test_schema_drift_detects_missing_extra_and_absent_tables() -> None:
    live = {
        spec.name: [*spec.accounted_columns, "source_file"]
        for spec in DATA_FINGERPRINT_TABLE_SPECS
    }
    assert data_fingerprint.schema_drift(live) is None
    assert data_fingerprint.schema_drift({**live, "tl_scco_li": ["li_cd", "geom"]}) == "tl_scco_li"
    absent = {k: v for k, v in live.items() if k != "region_radius_parts"}
    assert data_fingerprint.schema_drift(absent) == "region_radius_parts"


@pytest.mark.asyncio
async def test_compute_fingerprint_honours_a_caller_timeout() -> None:
    conn = _FingerprintConn()
    await compute_data_fingerprint(conn, statement_timeout="2min")
    assert conn.log[1] == "SET LOCAL statement_timeout = '2min'"


def test_activation_helper_fingerprints_before_the_lock_and_clears_cache_after_insert() -> None:
    """Source-order pin for ADR-069 D4/D6 (the integration suite checks the timing effect)."""
    source = inspect.getsource(admin_repo._insert_dataset_snapshot_and_release)
    fingerprint_at = source.index("await fingerprint_for_activation(conn)")
    lock_at = source.index("pg_advisory_xact_lock")
    superseded_at = source.index('"superseded_during_scan"')
    release_insert_at = source.index("INSERT INTO ops.serving_releases")
    clear_at = source.index("await GeoCacheRepository.clear_on(conn)")
    assert fingerprint_at < lock_at < superseded_at < release_insert_at < clear_at
    # the cache clear is NOT conditioned on the data_fingerprint argument
    clear_guard = source[:clear_at].rsplit("\n    if ", 1)[1]
    assert clear_guard.startswith('release_state == "active":')
    assert "data_fingerprint_failed: " in source


def test_mv_refresh_release_scans_before_the_publication_guard() -> None:
    source = inspect.getsource(admin_repo.AdminRepository.record_mv_refresh_release)
    scan_at = source.index("await fingerprint_for_activation(conn)")
    guard_at = source.index("await publication_guard(conn)")
    assert scan_at < guard_at
    assert "fingerprint_attempt=fingerprint_attempt" in source


def test_activation_paths_route_through_the_helper() -> None:
    """ADR-069 D4: partial_restore/postload only reach the helper; hot-swap pre-computes."""
    from kortravelgeo.infra import hotswap, partial_restore
    from kortravelgeo.loaders import postload

    for module in (partial_restore, postload):
        assert "fingerprint" not in inspect.getsource(module)
    hotswap_source = inspect.getsource(hotswap)
    assert hotswap_source.count("fingerprint_attempt=fingerprint_attempt") == 2
    assert data_fingerprint.DATA_FINGERPRINT_STATEMENT_TIMEOUT == "10min"


@pytest.mark.parametrize(
    ("current", "target", "blocked"),
    [
        ("0029_t325a_data_fingerprint", "0029_t325a_data_fingerprint", False),
        ("0029_t325a_data_fingerprint", "0028_t319_source_month_manifest", True),
        ("0029_t325a_data_fingerprint", None, True),
    ],
)
def test_hot_swap_refuses_a_restore_database_on_another_schema_revision(
    current: str, target: str | None, blocked: bool
) -> None:
    from kortravelgeo.infra.hotswap import alembic_revision_mismatch_blocker

    message = alembic_revision_mismatch_blocker(current_revision=current, target_revision=target)
    assert (message is not None) is blocked
    if blocked:
        assert "alembic upgrade head" in str(message)


# --- v2 dataset stamp -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_ref_cache_serves_within_ttl_and_refreshes_after() -> None:
    now = [100.0]
    cache = DatasetRefCache(ttl_s=10.0, clock=lambda: now[0])
    calls: list[int] = []
    values = [(_VERSION, _DATA), (_VERSION, None)]

    async def loader() -> tuple[str, str | None] | None:
        calls.append(1)
        return values[len(calls) - 1]

    first = await cache.get(loader)
    now[0] = 109.9
    assert await cache.get(loader) == first
    assert len(calls) == 1
    now[0] = 110.0
    second = await cache.get(loader)
    assert len(calls) == 2
    assert first == DatasetRef(version_token=_VERSION, data_token=_DATA)
    assert second == DatasetRef(version_token=_VERSION, data_token=None)


@pytest.mark.asyncio
async def test_dataset_ref_cache_remembers_failures_briefly() -> None:
    now = [0.0]
    cache = DatasetRefCache(ttl_s=10.0, failure_ttl_s=1.0, clock=lambda: now[0])
    attempts: list[int] = []

    async def failing() -> tuple[str, str | None] | None:
        attempts.append(1)
        raise RuntimeError("ledger down")

    assert await cache.get(failing) is None
    now[0] = 0.9
    assert await cache.get(failing) is None
    assert len(attempts) == 1  # the failure is shared, not retried by every waiter
    now[0] = 1.0
    assert await cache.get(failing) is None
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_concurrent_waiters_share_one_failing_load() -> None:
    import asyncio

    cache = DatasetRefCache(ttl_s=10.0, failure_ttl_s=1.0)
    attempts: list[int] = []

    async def slow_failing() -> tuple[str, str | None] | None:
        attempts.append(1)
        await asyncio.sleep(0.05)
        raise RuntimeError("ledger down")

    results = await asyncio.gather(*(cache.get(slow_failing) for _ in range(5)))
    assert results == [None] * 5
    assert len(attempts) == 1


def _stub_client(monkeypatch: pytest.MonkeyPatch, ref: DatasetRef | None) -> Any:
    """A client whose stamp is ``ref`` and whose v1 lookups record the stamp they were given."""
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.dto.common import Point, ServiceMeta
    from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse

    seen: list[Any] = []

    async def fake_ref(self: AsyncAddressClient) -> DatasetRef | None:
        return ref

    async def fake_reverse_v1(
        self: AsyncAddressClient, x: float, y: float, **kwargs: Any
    ) -> ReverseResponse:
        seen.append(kwargs["dataset"])
        return ReverseResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
            status="NOT_FOUND",
            input=ReverseInput(point=Point(x=x, y=y)),
        )

    monkeypatch.setattr(AsyncAddressClient, "dataset_ref", fake_ref)
    monkeypatch.setattr(AsyncAddressClient, "_reverse_geocode_v1", fake_reverse_v1)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    client._t325_seen = seen  # type: ignore[attr-defined]
    return client


@pytest.mark.asyncio
async def test_client_stamps_the_answer_with_the_ref_it_keyed_the_cache_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = DatasetRef(version_token=_VERSION, data_token=_DATA)
    client = _stub_client(monkeypatch, ref)
    response = await client.reverse(127.036, 37.501)
    assert response.dataset == ref
    assert client._t325_seen == [ref]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_client_omits_the_stamp_without_an_active_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _stub_client(monkeypatch, None)
    response = await client.reverse(127.036, 37.501)
    assert response.dataset is None
    assert "dataset" not in response.model_dump(exclude_none=True)


def test_cache_keys_carry_the_release() -> None:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.dto.common import Point
    from kortravelgeo.dto.geocode import GeocodeInput
    from kortravelgeo.dto.reverse import ReverseInput

    r1 = DatasetRef(version_token=_VERSION, data_token=_DATA)
    r2 = DatasetRef(version_token=derive_version_token("00000000-0000-0000-0000-000000000002"))
    rev = ReverseInput(point=Point(x=127.0, y=37.5))
    geo = GeocodeInput(address="서울특별시 중구 세종대로 110")
    keys = {
        AsyncAddressClient._reverse_cache_key(rev, sig_cd=None, bjd_cd=None, dataset=r)
        for r in (r1, r2, None)
    }
    assert len(keys) == 3
    keys = {
        AsyncAddressClient._geocode_cache_key(geo, sig_cd=None, bjd_cd=None, dataset=r)
        for r in (r1, r2, None)
    }
    assert len(keys) == 3


@pytest.mark.asyncio
async def test_client_survives_a_ledger_failure_by_omission() -> None:
    from kortravelgeo.client import AsyncAddressClient

    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    assert await client.dataset_ref() is None


class _StampClient:
    """Each method returns a fixed, already-stamped v2 response."""

    def __init__(self, ref: DatasetRef | None) -> None:
        self.ref = ref

    async def geocode(self, **kwargs: Any) -> GeocodeV2Response:
        inp = GeocodeV2Input(query=kwargs["query"])
        return GeocodeV2Response(status="OK", input=inp, dataset=self.ref)

    async def reverse(self, lon: float, lat: float, **_: Any) -> ReverseV2Response:
        inp = ReverseV2Input(lon=lon, lat=lat)
        return ReverseV2Response(status="OK", input=inp, dataset=self.ref)

    async def search(self, **kwargs: Any) -> SearchV2Response:
        inp = SearchV2Input(query=kwargs["query"])
        return SearchV2Response(status="OK", input=inp, dataset=self.ref)

    async def regions_within_radius(self, **kwargs: Any) -> RegionsWithinRadiusResponse:
        inp = RegionsWithinRadiusInput(lon=kwargs["lon"], lat=kwargs["lat"])
        return RegionsWithinRadiusResponse(
            status="OK",
            input=inp,
            center=RegionWithinRadiusCenter(lon=inp.lon, lat=inp.lat),
            radius_km=inp.radius_km,
            dataset=self.ref,
        )


_V2_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/v2/geocode", {"query": "테헤란로 152"}),
    ("/v2/reverse", {"lon": 127.036, "lat": 37.501}),
    ("/v2/search", {"query": "테헤란로"}),
    ("/v2/regions/within-radius", {"lon": 127.036, "lat": 37.501}),
)


async def _post_all(ref: DatasetRef | None) -> list[dict[str, Any]]:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: _StampClient(ref)
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    bodies = []
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        for path, payload in _V2_CALLS:
            response = await http_client.post(path, json=payload)
            assert response.status_code == 200, (path, response.text)
            bodies.append(response.json())
    return bodies


@pytest.mark.asyncio
async def test_four_v2_lookups_carry_the_dataset_stamp() -> None:
    ref = DatasetRef(version_token=_VERSION, data_token=_DATA)
    for body in await _post_all(ref):
        assert body["dataset"] == {"version_token": _VERSION, "data_token": _DATA}


@pytest.mark.asyncio
async def test_dataset_stamp_omits_absent_data_token_and_absent_release() -> None:
    for body in await _post_all(DatasetRef(version_token=_VERSION, data_token=None)):
        assert body["dataset"] == {"version_token": _VERSION}
    for body in await _post_all(None):
        assert "dataset" not in body


def test_openapi_publishes_dataset_on_the_four_lookup_responses() -> None:
    components = create_app().openapi()["components"]["schemas"]
    for name in (
        "GeocodeV2Response",
        "ReverseV2Response",
        "SearchV2Response",
        "RegionsWithinRadiusResponse",
    ):
        assert "dataset" in components[name]["properties"], name
        assert "dataset" not in components[name].get("required", [])
    assert set(components["DatasetRef"]["properties"]) == {"version_token", "data_token"}
    assert "data_token" in components["DatasetVersionEntry"]["properties"]
