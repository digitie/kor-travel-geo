"""T-310: ``/metrics``·Cache 패널의 ``geo_cache`` 전수 scan 제거와 scrape 견고성 (DB-free).

- ``/metrics`` scrape는 DB를 전혀 조회하지 않는다(15초 scrape마다 geo_cache 전수 집계가
  공용 instance 논리 읽기의 대부분이었고, statement timeout·crash 창의 OperationalError가
  그대로 scrape 503이 됐다).
- DB 기반 gauge는 lifespan refresher가 source별로 시간 제한을 두고 갱신한다. 실패한 source는
  last-good 값을 유지하고 ``ktg_metrics_db_refresh_errors_total``로만 센다.
- ``AdminRepository.cache_metrics``의 기본(추정) 모드는 geo_cache heap을 읽지 않고, exact
  모드만 전수 집계를 돌린다.
- pg_stat_statements capture는 현재 DB + 현재 role(=이 tenant의 app role) 항목만 읽는다.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY
from sqlalchemy.exc import OperationalError

from kortravelgeo.api import app as app_module
from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.dto.admin import CacheMetrics, PgStatStatementSnapshot
from kortravelgeo.dto.source import SourceCapacityUsage, SourceCategoryCapacity
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.settings import Settings, get_settings

_SQL_COMMENT_RE = re.compile(r"--[^\n]*")


def _sql(statement: object) -> str:
    """Executed SQL with ``--`` comments stripped and whitespace collapsed.

    Comments are removed so an assertion can only be satisfied by SQL that actually runs,
    never by a comment that happens to mention the same predicate.
    """
    return " ".join(_SQL_COMMENT_RE.sub(" ", str(statement)).split())


def _sample(name: str, **labels: str) -> float | None:
    return REGISTRY.get_sample_value(name, labels or None)


def _refresh_errors(source: str, error_type: str) -> float:
    return (
        _sample("ktg_metrics_db_refresh_errors_total", source=source, error_type=error_type) or 0.0
    )


def _capacity(total_bytes: int) -> SourceCapacityUsage:
    return SourceCapacityUsage(
        categories=(
            SourceCategoryCapacity(
                category="locsum_full",
                object_count=1,
                total_bytes=total_bytes,
            ),
        ),
        total_object_count=1,
        total_bytes=total_bytes,
        quarantined_bytes=0,
        soft_deleted_bytes=0,
        unregistered_bytes=0,
        growth_30d_bytes=0,
        capacity_limit_bytes=None,
        over_threshold=False,
    )


def _pg_stat_row(calls: int) -> PgStatStatementSnapshot:
    return PgStatStatementSnapshot(
        pg_stat_snapshot_id="pg-stat-t310",
        captured_at=datetime.now(UTC),
        rank=1,
        query_fingerprint="t310fingerpr",
        operation="select",
        calls=calls,
        total_exec_time_ms=1.0,
        mean_exec_time_ms=1.0,
        max_exec_time_ms=1.0,
        rows_returned=1,
        query_preview="SELECT ?",
    )


class _MetricsClient:
    """Fake ``AsyncAddressClient`` exposing only the DB-backed metric reads."""

    def __init__(
        self,
        *,
        entries: int = 11,
        total_bytes: int = 600,
        calls: int = 7,
        cache_error: BaseException | None = None,
        capacity_hangs: bool = False,
    ) -> None:
        self.entries = entries
        self.total_bytes = total_bytes
        self.calls = calls
        self.cache_error = cache_error
        self.capacity_hangs = capacity_hangs
        self.pg_stat_limits: list[int] = []

    async def cache_metrics(self) -> CacheMetrics:
        if self.cache_error is not None:
            raise self.cache_error
        return CacheMetrics(enabled=True, entries=self.entries, hits=3, expired=1)

    async def load_job_metric_counts(self) -> list[tuple[str, str, int]]:
        return [("t310_kind", "done", 2)]

    async def source_storage_capacity(self) -> SourceCapacityUsage:
        if self.capacity_hangs:
            await asyncio.Event().wait()
        return _capacity(self.total_bytes)

    async def source_upload_session_state_counts(self) -> dict[str, int]:
        return {"uploading": 1}

    async def list_pg_stat_statement_snapshots(
        self, *, limit: int = 20
    ) -> list[PgStatStatementSnapshot]:
        self.pg_stat_limits.append(limit)
        return [_pg_stat_row(self.calls)]


# --- /metrics scrape path ---------------------------------------------------


class _NoDbClient:
    """Any attribute other than ``engine`` means the scrape touched a DB-backed client call."""

    def __init__(self, engine: object | None) -> None:
        self.engine = engine

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"/metrics scrape must not call client.{name}()")


class _FakePool:
    def size(self) -> int:
        return 13

    def checkedin(self) -> int:
        return 12

    def checkedout(self) -> int:
        return 1

    def overflow(self) -> int:
        return 0


class _FakeEngine:
    class sync_engine:  # noqa: N801 - mimics AsyncEngine.sync_engine attribute
        pool = _FakePool()


@pytest.mark.asyncio
async def test_metrics_scrape_serves_without_any_db_call() -> None:
    app = create_app()
    app.state.client = _NoDbClient(_FakeEngine())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    # The in-process pool gauges are still read on the scrape.
    assert "ktg_pg_pool_size 13.0" in body
    # DB-backed families are still exposed (from the last refresh), names unchanged.
    for name in ("ktg_cache_entries", "ktg_cache_hits", "ktg_cache_expired_entries"):
        assert f"# TYPE {name} gauge" in body


@pytest.mark.asyncio
async def test_metrics_scrape_serves_before_client_exists() -> None:
    app = create_app()  # lifespan not run: no app.state.client yet
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200


# --- off-scrape refresher ---------------------------------------------------


async def test_refresh_sets_db_backed_gauges_and_success_timestamps() -> None:
    client = _MetricsClient(entries=41, total_bytes=4_100, calls=410)

    await app_module._refresh_db_metrics_once(
        client,  # type: ignore[arg-type]
        Settings(_env_file=None, ops_pg_stat_statements_capture_limit=9),
    )

    assert _sample("ktg_cache_entries") == 41
    assert _sample("ktg_cache_hits") == 3
    assert _sample("ktg_cache_expired_entries") == 1
    assert _sample("ktg_load_jobs", kind="t310_kind", state="done") == 2
    assert _sample("ktg_source_storage_total_bytes") == 4_100
    assert _sample("ktg_source_upload_sessions", state="uploading") == 1
    assert (
        _sample(
            "ktg_pg_stat_statements_calls",
            rank="1",
            operation="select",
            query_fingerprint="t310fingerpr",
        )
        == 410
    )
    assert client.pg_stat_limits == [9]
    for source in ("cache_load_jobs", "source_registry", "pg_stat_statements"):
        assert (
            _sample("ktg_metrics_db_refresh_last_success_timestamp_seconds", source=source) or 0
        ) > 0


async def test_refresh_failure_keeps_last_good_values_and_is_counted() -> None:
    settings = Settings(_env_file=None)
    await app_module._refresh_db_metrics_once(
        _MetricsClient(entries=52, total_bytes=5_200),  # type: ignore[arg-type]
        settings,
    )
    assert _sample("ktg_cache_entries") == 52
    before = _refresh_errors("cache_load_jobs", "OperationalError")

    timeout = OperationalError(
        "SELECT ...", {}, Exception("canceling statement due to statement timeout")
    )
    # Must not raise even though the DB read fails.
    await app_module._refresh_db_metrics_once(
        _MetricsClient(entries=999, total_bytes=5_300, cache_error=timeout),  # type: ignore[arg-type]
        settings,
    )

    assert _sample("ktg_cache_entries") == 52  # last-good kept, not zeroed / not 999
    assert _refresh_errors("cache_load_jobs", "OperationalError") == before + 1
    # One failing source does not stop the others from refreshing.
    assert _sample("ktg_source_storage_total_bytes") == 5_300


async def test_refresh_bounds_a_hanging_source_and_continues() -> None:
    settings = Settings(_env_file=None)
    before = _refresh_errors("source_registry", "TimeoutError")
    client = _MetricsClient(total_bytes=6_400, calls=640, capacity_hangs=True)

    await asyncio.wait_for(
        app_module._refresh_db_metrics_once(
            client,  # type: ignore[arg-type]
            settings,
            timeout_s=0.05,
        ),
        timeout=2.0,
    )

    assert _refresh_errors("source_registry", "TimeoutError") == before + 1
    # The source after the hung one still refreshed.
    assert (
        _sample(
            "ktg_pg_stat_statements_calls",
            rank="1",
            operation="select",
            query_fingerprint="t310fingerpr",
        )
        == 640
    )


async def test_refresh_scheduler_honors_interval_setting() -> None:
    client = _MetricsClient()
    disabled = app_module._start_db_metrics_refresh_scheduler(
        client,  # type: ignore[arg-type]
        Settings(_env_file=None, metrics_db_refresh_interval_seconds=0),
    )
    assert disabled is None

    task = app_module._start_db_metrics_refresh_scheduler(
        client,  # type: ignore[arg-type]
        Settings(_env_file=None, metrics_db_refresh_interval_seconds=3_600),
    )
    assert task is not None
    try:
        # The first refresh runs immediately at startup, not after one interval.
        for _ in range(100):
            if client.pg_stat_limits:
                break
            await asyncio.sleep(0.01)
        assert client.pg_stat_limits
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# --- AdminRepository SQL ----------------------------------------------------


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row or {}

    def mappings(self) -> _Result:
        return self

    def one(self) -> dict[str, Any]:
        return self._row

    def all(self) -> list[dict[str, Any]]:
        return []


class _Conn:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

    async def __aenter__(self) -> _Conn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def execute(self, statement: object, _params: object = None) -> _Result:
        self._statements.append(_sql(statement))
        return _Result({"entries": 5, "hits": 2, "expired": 1})

    async def scalar(self, statement: object, _params: object = None) -> bool:
        self._statements.append(_sql(statement))
        return True  # advisory lock acquired


class _Engine:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def connect(self) -> _Conn:
        return _Conn(self.statements)

    def begin(self) -> _Conn:
        return _Conn(self.statements)


async def test_cache_metrics_default_does_not_scan_geo_cache() -> None:
    engine = _Engine()

    metrics = await AdminRepository(engine).cache_metrics(enabled=True)  # type: ignore[arg-type]

    assert metrics.exact is False
    assert (metrics.entries, metrics.hits, metrics.expired) == (5, 2, 1)
    (sql,) = engine.statements
    # Row count / hit count come from catalog statistics, not from geo_cache rows.
    assert "FROM pg_class c" in sql
    assert "n_tup_upd" in sql
    assert "sum(hit_count)" not in sql
    # The only geo_cache read is the index-range count of expired rows.
    assert sql.count("FROM geo_cache") == 1
    assert "FROM geo_cache WHERE expires_at <= now()" in sql


async def test_cache_metrics_exact_runs_full_aggregate_only_on_request() -> None:
    engine = _Engine()

    metrics = await AdminRepository(engine).cache_metrics(enabled=True, exact=True)  # type: ignore[arg-type]

    assert metrics.exact is True
    (sql,) = engine.statements
    assert "COALESCE(sum(hit_count), 0)::bigint AS hits" in sql
    assert sql.endswith("FROM geo_cache")


async def test_pg_stat_statements_capture_is_limited_to_this_database_and_role() -> None:
    engine = _Engine()

    await AdminRepository(engine).capture_pg_stat_statement_snapshots(  # type: ignore[arg-type]
        limit=5, retention_days=None
    )

    (capture_sql,) = [s for s in engine.statements if "x_extension.pg_stat_statements" in s]
    assert "dbid = (SELECT oid FROM pg_database WHERE datname = current_database())" in capture_sql
    assert "userid = (SELECT oid FROM pg_roles WHERE rolname = current_user)" in capture_sql


# --- admin API ----------------------------------------------------------------


class _CacheRouteClient:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def cache_metrics(self, *, exact: bool = False) -> CacheMetrics:
        self.calls.append(exact)
        return CacheMetrics(enabled=True, entries=1, hits=0, expired=0, exact=exact)


@pytest.mark.asyncio
async def test_admin_cache_metrics_is_estimate_unless_exact_requested() -> None:
    fake = _CacheRouteClient()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        geoip_gate_mode="off",
    )
    app.dependency_overrides[get_client] = lambda: fake
    headers = {"X-KTG-Actor": "ui-cache", "X-KTG-Roles": "source_file_viewer"}
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        default = await client.get("/v1/admin/cache/metrics", headers=headers)
        exact = await client.get(
            "/v1/admin/cache/metrics", params={"exact": "true"}, headers=headers
        )

    assert default.status_code == 200
    assert default.json()["exact"] is False
    assert exact.status_code == 200
    assert exact.json()["exact"] is True
    assert fake.calls == [False, True]
