"""T-325a/b unit coverage: data_token derivation, fingerprint SQL shape and fail-open,
activation-helper ordering, the v2 ``dataset`` stamp and its TTL cache (ADR-069)."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from kortravelgeo.api.app import create_app
from kortravelgeo.api.dataset_ref import DatasetRefCache, get_dataset_ref
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
        "md5(string_agg(table_name || ':' || coalesce(h, 0)::text, ',' ORDER BY table_name))"
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


class _FingerprintConn:
    def __init__(self, *, fail: BaseException | None = None) -> None:
        self.log: list[str] = []
        self.fail = fail

    async def begin_nested(self) -> _Nested:
        self.log.append("SAVEPOINT")
        return _Nested(self.log)

    async def execute(self, statement: Any, params: Any = None) -> _Rows:
        sql = str(statement)
        self.log.append(sql.splitlines()[0])
        if sql == DATA_FINGERPRINT_SQL:
            if self.fail is not None:
                raise self.fail
            return _Rows(
                [
                    {"table_name": "mv_geocode_target", "h": 12, "fingerprint": "f" * 32},
                    {"table_name": "tl_kodis_bas", "h": None, "fingerprint": "f" * 32},
                ]
            )
        return _Rows([])


@pytest.mark.asyncio
async def test_compute_fingerprint_runs_inside_a_savepoint_that_is_always_rolled_back() -> None:
    conn = _FingerprintConn()
    result = await compute_data_fingerprint(conn)

    assert result.fingerprint == "f" * 32
    assert result.error_code is None
    assert result.table_hashes == {"mv_geocode_target": "12", "tl_kodis_bas": None}
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


def test_activation_helper_fingerprints_before_the_lock_and_clears_cache_after_insert() -> None:
    """Source-order pin for ADR-069 D4/D6 (the integration suite checks the timing effect)."""
    source = inspect.getsource(admin_repo._insert_dataset_snapshot_and_release)
    fingerprint_at = source.index("await compute_data_fingerprint(conn)")
    lock_at = source.index("pg_advisory_xact_lock")
    release_insert_at = source.index("INSERT INTO ops.serving_releases")
    clear_at = source.index("await GeoCacheRepository.clear_on(conn)")
    assert fingerprint_at < lock_at < release_insert_at < clear_at
    assert 'if release_state == "active" and data_fingerprint is None:' in source
    # the cache clear is NOT conditioned on the data_fingerprint argument
    clear_guard = source[:clear_at].rsplit("\n    if ", 1)[1]
    assert clear_guard.startswith('release_state == "active":')
    assert "data_fingerprint_failed: " in source


def test_hotswap_restore_and_postload_paths_are_not_touched() -> None:
    """ADR-069 D4: the four activation paths are covered through the shared helper."""
    from kortravelgeo.infra import hotswap, partial_restore
    from kortravelgeo.loaders import postload

    for module in (hotswap, partial_restore, postload):
        assert "compute_data_fingerprint" not in inspect.getsource(module)
    assert data_fingerprint.DATA_FINGERPRINT_STATEMENT_TIMEOUT == "10min"


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
async def test_dataset_ref_cache_does_not_cache_failures_and_caches_no_active_release() -> None:
    cache = DatasetRefCache(ttl_s=10.0, clock=lambda: 0.0)
    attempts: list[int] = []

    async def failing() -> tuple[str, str | None] | None:
        attempts.append(1)
        raise RuntimeError("ledger down")

    assert await cache.get(failing) is None
    assert await cache.get(failing) is None
    assert len(attempts) == 2

    async def no_release() -> tuple[str, str | None] | None:
        attempts.append(1)
        return None

    assert await cache.get(no_release) is None
    assert await cache.get(no_release) is None
    assert len(attempts) == 3


class _StampClient:
    """Each method returns a fixed v2 response, as a cache hit would."""

    async def geocode(self, **kwargs: Any) -> GeocodeV2Response:
        return GeocodeV2Response(status="OK", input=GeocodeV2Input(query=kwargs["query"]))

    async def reverse(self, lon: float, lat: float, **_: Any) -> ReverseV2Response:
        return ReverseV2Response(status="OK", input=ReverseV2Input(lon=lon, lat=lat))

    async def search(self, **kwargs: Any) -> SearchV2Response:
        return SearchV2Response(status="OK", input=SearchV2Input(query=kwargs["query"]))

    async def regions_within_radius(self, **kwargs: Any) -> RegionsWithinRadiusResponse:
        inp = RegionsWithinRadiusInput(lon=kwargs["lon"], lat=kwargs["lat"])
        return RegionsWithinRadiusResponse(
            status="OK",
            input=inp,
            center=RegionWithinRadiusCenter(lon=inp.lon, lat=inp.lat),
            radius_km=inp.radius_km,
        )


_V2_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/v2/geocode", {"query": "테헤란로 152"}),
    ("/v2/reverse", {"lon": 127.036, "lat": 37.501}),
    ("/v2/search", {"query": "테헤란로"}),
    ("/v2/regions/within-radius", {"lon": 127.036, "lat": 37.501}),
)


async def _post_all(ref: DatasetRef | None) -> list[dict[str, Any]]:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: _StampClient()
    app.dependency_overrides[require_public_api_key] = lambda: None
    app.dependency_overrides[get_dataset_ref] = lambda: ref
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


@pytest.mark.asyncio
async def test_dataset_stamp_survives_a_ledger_failure_by_omission() -> None:
    """The stamp is metadata: if the release lookup fails the lookup answer still returns."""

    class _BrokenEngineClient(_StampClient):
        def _engine(self) -> Any:
            raise RuntimeError("no engine")

    app = create_app()
    app.dependency_overrides[get_client] = lambda: _BrokenEngineClient()
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post("/v2/reverse", json={"lon": 127.036, "lat": 37.501})
    assert response.status_code == 200
    assert "dataset" not in response.json()


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
