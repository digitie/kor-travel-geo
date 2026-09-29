"""T-319: 원천 기준월은 load_manifest에서 읽고, 적재기가 그 행을 남긴다.

serving release 기록(`admin_repo._infer_current_source_set`)과 백업 manifest
(`backup.infer_source_set`)가 원천 테이블마다 `max(source_yyyymm)`를 전수 scan하던 것을
manifest 조회 한 번으로 바꿨다. 여기서는 (1) 조회가 원천 테이블을 건드리지 않고 manifest 값을
그대로 돌려주는지, manifest가 없으면 scan 대신 active release 기준월(행이 있을 때) 또는 None인지,
(2) 적재기(도로명주소 한글·위치정보요약·내비게이션·SHP 건물)가 적재 row의 최댓값을 같은
transaction에서 manifest에 남기고 테이블을 비우는 경로(SHP·구역 full)가 manifest 행을 지우는지,
(3) Alembic 0028 backfill이 manifest 없는 테이블(과 옛 일변동 ``tl_juso_text`` 행)만 한 번
채우는지를 고정한다.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.engine import make_url

from kortravelgeo.infra import admin_repo, backup
from kortravelgeo.loaders import manifest, sppn_makarea_loader
from kortravelgeo.loaders.shp import polygons_loader
from kortravelgeo.loaders.text import juso_hangul_loader, locsum_loader, navi_loader

# --------------------------------------------------------------------------------------
# 조회: load_manifest만 읽는다
# --------------------------------------------------------------------------------------


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


_PROBE_RE = re.compile(r"SELECT EXISTS \(SELECT 1 FROM public\.(\w+)\)")


class _LookupConn:
    """`_SOURCE_YYYYMM_BY_TABLE_SQL`의 LEFT JOIN을 흉내 낸다(``manifest_months``에 키가 있으면
    manifest 행이 있다 — 값이 None이어도). active serving release 조회와 계보 폴백 조회,
    행 존재 probe도 흉내 낸다. `scalar`는 probe만 받는다 — 옛 `max(source_yyyymm)` scan이 다시
    들어오면 거기서 실패한다."""

    def __init__(
        self,
        *,
        existing: set[str],
        manifest_months: dict[str, str | None],
        active_source_set: dict[str, Any] | None = None,
        active_parent_id: str | None = None,
        snapshots: dict[str, dict[str, Any]] | None = None,
        nonempty: set[str] | None = None,
    ) -> None:
        self.existing = existing
        self.manifest_months = manifest_months
        self.active_source_set = active_source_set
        self.active_parent_id = active_parent_id
        self.snapshots = snapshots or {}
        self.nonempty = nonempty or set()
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        if "ops.serving_releases" in sql:
            assert "sr.state = 'active'" in sql
            if self.active_source_set is None:
                return _Result([])
            return _Result(
                [
                    {
                        "source_set": self.active_source_set,
                        "parent_dataset_snapshot_id": self.active_parent_id,
                    }
                ]
            )
        if "ops.dataset_snapshots" in sql:
            assert params is not None
            snapshot = self.snapshots.get(params["id"])
            return _Result([snapshot] if snapshot is not None else [])
        assert params is not None
        return _Result(
            [
                {
                    "table_name": name,
                    "table_exists": name in self.existing,
                    "has_manifest_row": name in self.manifest_months,
                    "source_yyyymm": self.manifest_months.get(name),
                }
                for name in params["table_names"]
            ]
        )

    async def scalar(self, statement: object, params: dict[str, Any] | None = None) -> object:
        sql = str(statement)
        self.statements.append(sql)
        match = _PROBE_RE.fullmatch(sql.strip())
        assert match is not None, sql
        return match.group(1) in self.nonempty


_ALL_SOURCE_TABLES = {
    "tl_juso_text",
    "tl_juso_parcel_link",
    "tl_locsum_entrc",
    "tl_navi_buld_centroid",
    "tl_spbd_buld_polygon",
    "tl_roadaddr_entrc",
    "tl_sppn_makarea",
}


def _assert_no_source_table_scan(statements: list[str], *, count: int = 1) -> None:
    """manifest 조회 1번(+ manifest 행이 없는 kind가 있으면 active release 조회)뿐이다."""
    assert len(statements) == count, statements
    assert "load_manifest" in statements[0]
    assert all("ops.serving_releases" in sql for sql in statements[1:]), statements
    for sql in statements:
        assert "max(" not in sql.lower()
        for table in _ALL_SOURCE_TABLES:
            assert f"FROM public.{table}" not in sql


@pytest.mark.asyncio
async def test_source_yyyymm_by_kind_reads_manifest_and_reports_unknown_without_scanning() -> None:
    conn = _LookupConn(
        existing={"tl_juso_text", "tl_locsum_entrc", "tl_navi_buld_centroid"},
        manifest_months={
            "tl_juso_text": "202603",
            "tl_locsum_entrc": "202604",
            # 테이블이 없는데 manifest만 남은 경우 — 옛 조회처럼 None.
            "tl_sppn_makarea": "202605",
        },
    )

    result = await admin_repo.source_yyyymm_by_kind(
        conn,
        {
            "juso": "tl_juso_text",
            "locsum": "tl_locsum_entrc",
            "navi": "tl_navi_buld_centroid",  # 테이블은 있고 manifest 행이 없다(legacy)
            "sppn_makarea": "tl_sppn_makarea",
        },
    )

    assert result == {
        "juso": "202603",
        "locsum": "202604",
        "navi": None,
        "sppn_makarea": None,
    }
    # navi는 manifest 행이 없어 active release를 찾아보지만(없음) 원천 테이블은 건드리지 않는다.
    _assert_no_source_table_scan(conn.statements, count=2)


_RELEASE_MONTHS = {
    "juso": "202603",
    "parcel_link": "202603",
    "locsum": "202604",
    "navi": "202604",
    "shp": "202604",
    "roadaddr_entrance": "202605",
    "sppn_makarea": "202605",
}


@pytest.mark.asyncio
async def test_kinds_without_manifest_row_fall_back_to_active_release_months() -> None:
    """T-319 이전 백업(0026/0027)을 복원만 한 DB: 원천 테이블에 행은 있고 0028 manifest 행은
    없다. scan 대신 active release가 기록한 기준월을 이어 쓴다."""
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={
            "tl_juso_text": "202609",  # 복원 뒤 새로 적재 — manifest가 release보다 우선
            "tl_juso_parcel_link": "202603",
            "tl_roadaddr_entrc": None,  # manifest 행이 있으면 NULL이어도 그대로 믿는다
        },
        active_source_set={
            "source": "database_manifest_inference",
            "mixed_yyyymm": True,
            "yyyymm_by_kind": dict(_RELEASE_MONTHS),
        },
        # tl_sppn_makarea는 비어 있다(예: full 적재 TRUNCATE 직후) — release 월을 붙이지 않는다.
        nonempty={"tl_locsum_entrc", "tl_navi_buld_centroid", "tl_spbd_buld_polygon"},
    )

    source_set = await admin_repo._infer_current_source_set(conn)

    assert source_set["yyyymm_by_kind"] == {
        "juso": "202609",
        "parcel_link": "202603",
        "locsum": "202604",
        "navi": "202604",
        "shp": "202604",
        "roadaddr_entrance": None,
        "sppn_makarea": None,
    }
    probes = [sql for sql in conn.statements if sql.startswith("SELECT EXISTS")]
    assert sorted(probes) == sorted(
        f"SELECT EXISTS (SELECT 1 FROM public.{table})"
        for table in (
            "tl_locsum_entrc",
            "tl_navi_buld_centroid",
            "tl_spbd_buld_polygon",
            "tl_sppn_makarea",
        )
    )
    assert not any("max(" in sql.lower() for sql in conn.statements)


@pytest.mark.asyncio
async def test_backup_fallback_follows_release_lineage_for_hot_swap_rows() -> None:
    """hot-swap/rollback이 남긴 form C release는 기준월이 없어 계보(부모 snapshot)를 따라간다
    — ``/v2/dataset/version``과 같은 해석."""
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={},
        active_source_set={"hot_swap": {"target_database": "kor_travel_geo_restore"}},
        active_parent_id="parent-snapshot",
        snapshots={
            "parent-snapshot": {
                "source_set": {"yyyymm_by_kind": dict(_RELEASE_MONTHS)},
                "parent_dataset_snapshot_id": None,
            }
        },
        nonempty=set(_ALL_SOURCE_TABLES),
    )

    class _Connect:
        async def __aenter__(self) -> _LookupConn:
            return conn

        async def __aexit__(self, *_exc: object) -> None:
            return None

    engine = SimpleNamespace(connect=_Connect)

    source_set = await backup.infer_source_set(engine)  # type: ignore[arg-type]

    assert source_set["yyyymm_by_kind"] == {
        kind: month for kind, month in _RELEASE_MONTHS.items() if kind != "sppn_makarea"
    }
    assert source_set["mixed_yyyymm"] is True


@pytest.mark.asyncio
async def test_no_manifest_and_no_active_release_stays_unknown_without_probing() -> None:
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={},
        nonempty=set(_ALL_SOURCE_TABLES),
    )

    source_set = await admin_repo._infer_current_source_set(conn)

    assert set(source_set["yyyymm_by_kind"].values()) == {None}
    assert source_set["mixed_yyyymm"] is False
    _assert_no_source_table_scan(conn.statements, count=2)


@pytest.mark.asyncio
async def test_admin_repo_inference_keeps_form_b_shape_from_manifest() -> None:
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={
            "tl_juso_text": "202603",
            "tl_juso_parcel_link": "202603",
            "tl_locsum_entrc": "202604",
            "tl_navi_buld_centroid": "202604",
            "tl_spbd_buld_polygon": "202604",
            "tl_roadaddr_entrc": "202605",
            "tl_sppn_makarea": "202605",
        },
    )

    source_set = await admin_repo._infer_current_source_set(conn)

    # 2026-09-28 운영 refresh가 max() scan으로 기록한 값과 같은 형태·값.
    assert source_set == {
        "yyyymm_by_kind": {
            "juso": "202603",
            "parcel_link": "202603",
            "locsum": "202604",
            "navi": "202604",
            "shp": "202604",
            "roadaddr_entrance": "202605",
            "sppn_makarea": "202605",
        },
        "mixed_yyyymm": True,
        "source": "database_manifest_inference",
    }
    _assert_no_source_table_scan(conn.statements)


@pytest.mark.asyncio
async def test_admin_repo_inference_single_month_is_not_mixed() -> None:
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={"tl_juso_text": "202609", "tl_locsum_entrc": "202609"},
    )

    source_set = await admin_repo._infer_current_source_set(conn)

    assert source_set["yyyymm_by_kind"]["juso"] == "202609"
    assert source_set["yyyymm_by_kind"]["navi"] is None
    assert source_set["mixed_yyyymm"] is False


@pytest.mark.asyncio
async def test_backup_infer_source_set_keeps_six_kind_shape_from_manifest() -> None:
    conn = _LookupConn(
        existing=set(_ALL_SOURCE_TABLES),
        manifest_months={
            "tl_juso_text": "202603",
            "tl_juso_parcel_link": "202603",
            "tl_locsum_entrc": "202604",
            "tl_navi_buld_centroid": "202604",
            "tl_spbd_buld_polygon": "202604",
            "tl_roadaddr_entrc": "202605",
            "tl_sppn_makarea": "202605",
        },
    )

    class _Connect:
        async def __aenter__(self) -> _LookupConn:
            return conn

        async def __aexit__(self, *_exc: object) -> None:
            return None

    engine = SimpleNamespace(connect=_Connect)

    source_set = await backup.infer_source_set(engine)  # type: ignore[arg-type]

    assert source_set == {
        "yyyymm_by_kind": {
            "juso": "202603",
            "parcel_link": "202603",
            "locsum": "202604",
            "navi": "202604",
            "shp": "202604",
            "roadaddr_entrance": "202605",
        },
        "mixed_yyyymm": True,
    }
    _assert_no_source_table_scan(conn.statements)


def test_max_source_yyyymm_matches_sql_max_semantics() -> None:
    fold: str | None = None
    for value in (None, "202603", None, "202605", "202604"):
        fold = manifest.max_source_yyyymm(fold, value)
    assert fold == "202605"
    assert manifest.max_source_yyyymm(None, None) is None
    assert manifest.max_source_yyyymm("202605", None) == "202605"


# --------------------------------------------------------------------------------------
# 적재기: 같은 transaction에서 manifest를 남긴다
# --------------------------------------------------------------------------------------


class _FakeCopy:
    def __init__(self, log: list[tuple[Any, ...]]) -> None:
        self.log = log

    async def __aenter__(self) -> _FakeCopy:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def write_row(self, row: tuple[object, ...]) -> None:
        self.log.append(("row", row))


class _FakeCursor:
    def __init__(self, log: list[tuple[Any, ...]]) -> None:
        self.log = log

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def execute(self, sql: str, params: object = None) -> None:
        self.log.append(("execute", sql, params))

    def copy(self, sql: str) -> _FakeCopy:
        self.log.append(("copy", sql))
        return _FakeCopy(self.log)


class _FakeConnection:
    def __init__(self, log: list[tuple[Any, ...]]) -> None:
        self.log = log

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.log)

    async def commit(self) -> None:
        self.log.append(("commit",))


def _patch_psycopg(monkeypatch: pytest.MonkeyPatch, module: object) -> list[tuple[Any, ...]]:
    log: list[tuple[Any, ...]] = []

    async def connect(_dsn: str, **_kwargs: object) -> _FakeConnection:
        return _FakeConnection(log)

    monkeypatch.setattr(
        module,
        "psycopg",
        SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect)),
    )
    return log


_ENGINE = SimpleNamespace(url=make_url("postgresql+psycopg://u:p@localhost:5432/kor_travel_geo"))


def _row(cls: type, **values: object) -> SimpleNamespace:
    fields = {field.name: None for field in dataclasses.fields(cls)}
    fields.update(values)
    return SimpleNamespace(**fields)


def _manifest_calls(log: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [
        entry[2]
        for entry in log
        if entry[0] == "execute" and "INSERT INTO load_manifest" in entry[1]
    ]


def _assert_manifest_before_commit(log: list[tuple[Any, ...]]) -> None:
    kinds = [
        "manifest" if entry[0] == "execute" and "INSERT INTO load_manifest" in entry[1]
        else entry[0]
        for entry in log
    ]
    assert kinds.index("manifest") < kinds.index("commit")


@pytest.mark.asyncio
async def test_juso_full_load_records_max_row_month_in_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_psycopg(monkeypatch, juso_hangul_loader)
    rows = [
        _row(juso_hangul_loader.JusoTextRow, source_yyyymm=month)
        for month in ("202603", None, "202605", "202604")
    ]

    count = await juso_hangul_loader.copy_juso_rows(_ENGINE, rows)  # type: ignore[arg-type]

    assert count == 4
    calls = _manifest_calls(log)
    assert len(calls) == 1
    assert calls[0]["table_name"] == "tl_juso_text"
    assert calls[0]["source_yyyymm"] == "202605"
    assert calls[0]["row_count"] == 4
    assert json.loads(calls[0]["source_set"])["kind"] == "juso_text_full"
    _assert_manifest_before_commit(log)


@pytest.mark.asyncio
async def test_juso_full_load_with_no_rows_leaves_manifest_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_psycopg(monkeypatch, juso_hangul_loader)

    count = await juso_hangul_loader.copy_juso_rows(_ENGINE, [])  # type: ignore[arg-type]

    assert count == 0
    assert _manifest_calls(log) == []


@pytest.mark.asyncio
async def test_locsum_load_records_max_row_month_in_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_psycopg(monkeypatch, locsum_loader)
    rows = [
        _row(locsum_loader.LocsumEntranceRow, source_yyyymm=month, x_5179=1.0, y_5179=2.0)
        for month in ("202604", "202602")
    ]

    count = await locsum_loader.copy_locsum_rows(_ENGINE, rows)  # type: ignore[arg-type]

    assert count == 2
    calls = _manifest_calls(log)
    assert len(calls) == 1
    assert calls[0]["table_name"] == "tl_locsum_entrc"
    assert calls[0]["source_yyyymm"] == "202604"
    assert calls[0]["row_count"] == 2
    _assert_manifest_before_commit(log)


@pytest.mark.asyncio
async def test_navi_load_records_building_centroid_month_in_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_psycopg(monkeypatch, navi_loader)
    build_rows = [
        _row(navi_loader.NaviBuildingRow, source_yyyymm=month, centroid_x=1.0, centroid_y=2.0)
        for month in ("202603", "202604", "202604")
    ]
    # 출입구 row의 기준월은 건물 centroid manifest에 섞이지 않는다.
    entrance_rows = [
        _row(navi_loader.NaviEntranceRow, source_yyyymm="202612", x_5179=1.0, y_5179=2.0)
    ]

    counts = await navi_loader.copy_navi_rows(
        _ENGINE,  # type: ignore[arg-type]
        build_rows,  # type: ignore[arg-type]
        entrance_rows,  # type: ignore[arg-type]
    )

    assert counts == (3, 1)
    calls = _manifest_calls(log)
    assert len(calls) == 1
    assert calls[0]["table_name"] == "tl_navi_buld_centroid"
    assert calls[0]["source_yyyymm"] == "202604"
    assert calls[0]["row_count"] == 3
    _assert_manifest_before_commit(log)


class _SyncResult:
    def __init__(self, *, rowcount: int = -1, scalar: object = None) -> None:
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar_one(self) -> object:
        return self._scalar

    def scalar(self) -> object:
        return self._scalar


class _SyncConn:
    def __init__(self, log: list[tuple[str, Any]], *, staged: int, inserted: int) -> None:
        self.log = log
        self.staged = staged
        self.inserted = inserted

    def execute(self, statement: object, params: object = None) -> _SyncResult:
        sql = str(statement)
        self.log.append((sql, params))
        if "count(*)" in sql:
            return _SyncResult(scalar=self.staged)
        if "reltuples" in sql:
            return _SyncResult(scalar=5)
        if sql.lstrip().startswith("INSERT INTO tl_spbd_buld_polygon"):
            return _SyncResult(rowcount=self.inserted)
        return _SyncResult()


class _SyncBegin:
    def __init__(self, conn: _SyncConn) -> None:
        self.conn = conn

    def __enter__(self) -> _SyncConn:
        self.conn.log.append(("BEGIN", None))
        return self.conn

    def __exit__(self, *_exc: object) -> None:
        self.conn.log.append(("COMMIT", None))


_PG_URL = "postgresql+psycopg://u:p@localhost:5432/kor_travel_geo"


def _patch_sync_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    staged: int = 0,
    inserted: int = 0,
    module: object = polygons_loader,
) -> list[tuple[str, Any]]:
    log: list[tuple[str, Any]] = []
    conn = _SyncConn(log, staged=staged, inserted=inserted)
    engine = SimpleNamespace(begin=lambda: _SyncBegin(conn), dispose=lambda: None)
    monkeypatch.setattr(module, "create_engine", lambda _url: engine)
    return log


def _building_plan(month: str | None) -> polygons_loader.ShpLoadPlan:
    return polygons_loader.ShpLoadPlan(
        source_layer=polygons_loader.BUILDING_POLYGON_LAYER_NAME,
        target_table="tl_spbd_buld_polygon",
        shp_path=Path("TL_SPBD_BULD.shp"),
        dbf_path=Path("TL_SPBD_BULD.dbf"),
        source_file="서울특별시/11000/TL_SPBD_BULD.shp",
        source_yyyymm=month,
    )


def test_shp_building_insert_records_month_and_accumulates_row_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_sync_engine(monkeypatch, staged=12, inserted=10)

    polygons_loader._insert_building_polygon_stage(_PG_URL, _building_plan("202604"))

    manifest_calls = [(sql, params) for sql, params in log if "load_manifest" in sql]
    assert len(manifest_calls) == 1
    sql, params = manifest_calls[0]
    assert params["table_name"] == "tl_spbd_buld_polygon"
    assert params["source_yyyymm"] == "202604"
    assert params["row_count"] == 10
    assert "row_count = load_manifest.row_count + EXCLUDED.row_count" in sql
    assert "source_yyyymm = EXCLUDED.source_yyyymm" in sql
    # 건물 INSERT와 같은 transaction(BEGIN..COMMIT 사이)에서 남긴다.
    order = [sql for sql, _ in log]
    insert_at = next(i for i, sql in enumerate(order) if "INSERT INTO tl_spbd_buld_polygon" in sql)
    manifest_at = next(i for i, sql in enumerate(order) if "load_manifest" in sql)
    assert order.index("BEGIN") < insert_at < manifest_at < order.index("COMMIT")


def test_shp_building_insert_without_rows_leaves_manifest_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_sync_engine(monkeypatch, staged=3, inserted=0)

    polygons_loader._insert_building_polygon_stage(_PG_URL, _building_plan("202604"))

    assert not [sql for sql, _ in log if "load_manifest" in sql]


def test_shp_full_truncate_marks_manifest_month_unknown_in_same_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # T-323: 행을 지우면 lookup이 legacy로 보고 active release의 옛 기준월로 메운다 — 재적재가
    # TRUNCATE 뒤 실패하면 옛 달이 붙는다. 행은 두고 기준월만 NULL("모름")로 둔다.
    log = _patch_sync_engine(monkeypatch)

    polygons_loader._truncate_target_tables(
        _PG_URL, ("tl_spbd_buld_polygon", "tl_sprd_intrvl")
    )

    order = [sql for sql, _ in log]
    truncate_at = next(i for i, sql in enumerate(order) if sql.startswith("TRUNCATE TABLE"))
    mark_at = next(i for i, sql in enumerate(order) if "UPDATE load_manifest" in sql)
    assert truncate_at < mark_at < order.index("COMMIT")
    assert "source_yyyymm = NULL" in order[mark_at]
    assert not any("DELETE FROM load_manifest" in sql for sql in order)
    assert log[mark_at][1] == {"table_names": ["tl_spbd_buld_polygon", "tl_sprd_intrvl"]}


def test_sppn_full_truncate_marks_manifest_month_unknown_in_same_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _patch_sync_engine(monkeypatch, module=sppn_makarea_loader)

    sppn_makarea_loader._truncate_target(_PG_URL)

    order = [sql for sql, _ in log]
    truncate_at = next(i for i, sql in enumerate(order) if sql.startswith("TRUNCATE TABLE"))
    mark_at = next(i for i, sql in enumerate(order) if "UPDATE load_manifest" in sql)
    assert order.index("BEGIN") < truncate_at < mark_at < order.index("COMMIT")
    assert order.count("BEGIN") == 1
    assert "source_yyyymm = NULL" in order[mark_at]
    assert not any("DELETE FROM load_manifest" in sql for sql in order)
    assert log[mark_at][1] == {"table_names": ["tl_sppn_makarea"]}


@pytest.mark.asyncio
async def test_truncated_manifest_row_stays_unknown_instead_of_stale_release_month() -> None:
    """T-323: sppn 재적재가 TRUNCATE 뒤 실패해 새 달 행만 일부 들어간 테이블 — manifest 행은 남고
    기준월이 NULL이므로 active release의 옛 달(202605)로 메우지 않고 None(모름)이다."""
    conn = _LookupConn(
        existing={"tl_sppn_makarea"},
        manifest_months={"tl_sppn_makarea": None},
        active_source_set={"yyyymm_by_kind": dict(_RELEASE_MONTHS)},
        nonempty={"tl_sppn_makarea"},
    )

    result = await admin_repo.source_yyyymm_by_kind(conn, {"sppn_makarea": "tl_sppn_makarea"})

    assert result == {"sppn_makarea": None}
    assert not any(sql.startswith("SELECT EXISTS") for sql in conn.statements)


# --------------------------------------------------------------------------------------
# Alembic 0028 backfill
# --------------------------------------------------------------------------------------

_MIGRATION_PATH = Path("alembic/versions/0028_t319_source_month_manifest.py")


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("_t319_migration", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_t319_migration_backfills_every_table_the_lookup_reads() -> None:
    migration = _load_migration()

    assert migration.revision == "0028_t319_source_month_manifest"
    assert migration.down_revision == "0027_t311_road_rn_trgm"
    # admin_repo가 읽는 7개(백업의 6개 포함)를 빠짐없이 채운다.
    inference_source = inspect.getsource(admin_repo._infer_current_source_set)
    backup_source = inspect.getsource(backup.infer_source_set)
    for table in _ALL_SOURCE_TABLES:
        assert table in migration.SOURCE_MONTH_TABLES
        assert f'"{table}"' in inference_source
    for table in migration.SOURCE_MONTH_TABLES:
        assert f'"{table}"' in inference_source
        if table != "tl_sppn_makarea":
            assert f'"{table}"' in backup_source


def test_t319_migration_scans_only_tables_without_manifest_and_skips_empty() -> None:
    migration = _load_migration()
    sql = migration.backfill_sql("tl_navi_buld_centroid")

    assert "count(*), max(source_yyyymm)" in sql
    assert "FROM public.tl_navi_buld_centroid" in sql
    assert (
        "WHERE NOT EXISTS (SELECT 1 FROM load_manifest WHERE table_name = "
        "'tl_navi_buld_centroid')"
    ) in sql
    assert "HAVING count(*) > 0" in sql
    assert "ON CONFLICT (table_name) DO NOTHING" in sql
    upgrade_source = inspect.getsource(migration.upgrade)
    assert 'SET LOCAL statement_timeout = 0' in upgrade_source
    assert upgrade_source.index("statement_timeout") < upgrade_source.index("backfill_sql")
    # downgrade는 backfill이 넣은 행만 지운다(그 뒤 적재기가 덮어쓴 행은 kind가 달라 남는다).
    assert migration.BACKFILL_KIND in migration.backfill_sql("tl_juso_text")
    downgrade_source = inspect.getsource(migration.downgrade)
    assert "DELETE FROM load_manifest WHERE source_set ->> 'kind' = '{BACKFILL_KIND}'" in (
        downgrade_source
    )


def test_t319_migration_rescans_juso_when_its_manifest_row_is_a_daily_delta() -> None:
    """T-319 이전에는 일변동만 ``tl_juso_text`` 행을 쓰고 전체분 적재기는 갱신하지 않았다 —
    일변동 뒤 더 새 전체분을 적재한 DB의 그 행은 옛 월이다(리뷰 재현: 202604 vs max 202606)."""
    migration = _load_migration()
    sql = migration.backfill_sql("tl_juso_text")

    assert (
        "WHERE NOT EXISTS (SELECT 1 FROM load_manifest WHERE table_name = 'tl_juso_text'"
        " AND source_set ->> 'kind' IS DISTINCT FROM 'daily_juso_delta')"
    ) in sql
    conflict = sql.split("ON CONFLICT (table_name)", 1)[1]
    assert "DO UPDATE SET" in conflict
    assert "GREATEST(load_manifest.source_yyyymm, EXCLUDED.source_yyyymm)" in conflict
    assert "WHERE load_manifest.source_set ->> 'kind' = 'daily_juso_delta'" in conflict
    # 일변동 watermark·통계와 kind(→ downgrade 대상 아님)는 그대로 둔다.
    for column in ("last_delta_at", "last_mvmn_de", "row_count", "source_set ="):
        assert column not in conflict
    # 다른 테이블은 manifest 행이 있으면 무조건 믿는다.
    for table in migration.SOURCE_MONTH_TABLES:
        if table != "tl_juso_text":
            other = migration.backfill_sql(table)
            assert other.rstrip().endswith("ON CONFLICT (table_name) DO NOTHING")
            assert "daily_juso_delta" not in other
