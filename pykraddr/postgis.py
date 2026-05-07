"""PostgreSQL/PostGIS loaders for legal-dong codes and GIS boundaries."""

from __future__ import annotations

import tempfile
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Engine, RowMapping

from .legal_dong import iter_legal_dong_records
from .models import LegalDongRecord

LEGAL_DONG_TABLE = "legal_dong_codes"
LEGAL_DONG_BOUNDARY_TABLE = "legal_dong_boundaries"
LEGAL_DONG_BOUNDARY_ISSUES_VIEW = "legal_dong_boundary_mapping_issues"
LEGAL_DONG_COPY_COLUMNS = (
    "legal_dong_code",
    "legal_dong_name",
    "status_name",
    "is_active",
    "previous_legal_dong_code",
    "sido_code",
    "sigungu_code",
    "eup_myeon_dong_code",
    "ri_code",
    "legal_dong_level",
    "source",
    "loaded_at",
)
BOUNDARY_CODE_COLUMN_CANDIDATES = (
    "BJCD",
    "BJD_CD",
    "BJD_CODE",
    "LEGAL_DONG_CODE",
    "법정동코드",
    "ADM_CD",
    "EMD_CD",
    "SIG_CD",
    "CTPRVN_CD",
)
BOUNDARY_NAME_COLUMN_CANDIDATES = ("NAME", "BJD_NM", "법정동명", "ADM_NM", "EMD_NM", "SIG_KOR_NM")


@dataclass(frozen=True, slots=True)
class BoundaryLoadResult:
    """Summary of one or more boundary ZIP loads."""

    loaded: int = 0
    matched: int = 0
    missing: int = 0
    inactive: int = 0
    files: tuple[str, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True)
class PostGISLegalDongStore:
    """SQLAlchemy 2/PostGIS store for legal-dong code and boundary data."""

    url_or_engine: str | Engine
    schema: str | None = "public"
    srid: int = 5179
    echo: bool = False
    engine: Engine = field(init=False)
    metadata: MetaData = field(init=False)
    legal_dong_table: Table = field(init=False)
    boundary_table: Table = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.url_or_engine, Engine):
            self.engine = self.url_or_engine
        else:
            self.engine = create_engine(self.url_or_engine, future=True, echo=self.echo)
        self.metadata = make_postgis_metadata(schema=self.schema, srid=self.srid)
        self.legal_dong_table = self.metadata.tables[_table_key(LEGAL_DONG_TABLE, self.schema)]
        self.boundary_table = self.metadata.tables[
            _table_key(LEGAL_DONG_BOUNDARY_TABLE, self.schema)
        ]

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> PostGISLegalDongStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_schema(self) -> None:
        with self.engine.begin() as connection:
            if self.schema and self.schema != "public":
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {_quote_ident(self.schema)}"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        self.metadata.create_all(self.engine)
        self.create_mapping_issues_view()

    def create_mapping_issues_view(self) -> None:
        boundary = _qualified_name(LEGAL_DONG_BOUNDARY_TABLE, self.schema)
        codes = _qualified_name(LEGAL_DONG_TABLE, self.schema)
        view = _qualified_name(LEGAL_DONG_BOUNDARY_ISSUES_VIEW, self.schema)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    CREATE OR REPLACE VIEW {view} AS
                    SELECT
                        b.id,
                        b.source_file,
                        b.source_layer,
                        b.source_code,
                        b.source_name,
                        b.legal_dong_code,
                        c.legal_dong_name,
                        c.status_name,
                        c.is_active,
                        b.mapping_status
                    FROM {boundary} AS b
                    LEFT JOIN {codes} AS c
                      ON b.legal_dong_code = c.legal_dong_code
                    WHERE b.legal_dong_code IS NULL
                       OR c.is_active IS NOT TRUE
                       OR b.mapping_status <> 'matched'
                    """
                )
            )

    def load_legal_dong_csv(
        self,
        path: str | Path,
        *,
        source: str | None = None,
        replace: bool = True,
        batch_size: int = 10_000,
        use_copy: bool = True,
    ) -> int:
        records = iter_legal_dong_records(path)
        return self.load_legal_dong_records(
            records,
            source=source or str(path),
            replace=replace,
            batch_size=batch_size,
            use_copy=use_copy,
        )

    def load_legal_dong_records(
        self,
        records: Iterable[LegalDongRecord],
        *,
        source: str,
        replace: bool = True,
        batch_size: int = 10_000,
        use_copy: bool = True,
    ) -> int:
        if use_copy and self.engine.dialect.name == "postgresql":
            return self._copy_legal_dong_records(records, source=source, replace=replace)
        return self._insert_legal_dong_records(
            records,
            source=source,
            replace=replace,
            batch_size=batch_size,
        )

    def load_boundary_zips(
        self,
        paths: Sequence[str | Path],
        *,
        replace: bool = True,
        encoding: str = "cp949",
        batch_size: int = 20_000,
    ) -> BoundaryLoadResult:
        """Load zipped shapefiles with GeoPandas and map BJCD/source codes to FK codes."""

        if replace:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "TRUNCATE TABLE "
                        f"{_qualified_name(LEGAL_DONG_BOUNDARY_TABLE, self.schema)}"
                    )
                )

        legal_status = self._legal_status_lookup()
        total_loaded = 0
        total_matched = 0
        total_missing = 0
        total_inactive = 0
        files: list[str] = []
        issues: list[dict[str, Any]] = []
        for path in paths:
            frame = read_boundary_zip(path, srid=self.srid, encoding=encoding)
            code_column = _pick_column(frame.columns, BOUNDARY_CODE_COLUMN_CANDIDATES)
            name_column = _pick_column(frame.columns, BOUNDARY_NAME_COLUMN_CANDIDATES)
            if code_column is None:
                raise ValueError(f"{path}: legal-dong code column was not found")
            source_layer = boundary_level_from_path(path)
            source_file = Path(path).name
            files.append(source_file)
            frame["source_code"] = frame[code_column].astype(str).str.strip()
            frame["source_name"] = frame[name_column].astype(str).str.strip() if name_column else ""
            frame["legal_dong_code"] = frame["source_code"].where(
                frame["source_code"].isin(legal_status.keys())
            )
            frame["mapping_status"] = "matched"
            missing_mask = frame["legal_dong_code"].isna()
            inactive_mask = frame["legal_dong_code"].map(
                lambda code: legal_status.get(str(code), True) is False
            )
            frame.loc[missing_mask, "mapping_status"] = "missing_legal_dong_code"
            frame.loc[inactive_mask, "mapping_status"] = "inactive_legal_dong_code"
            missing_count = int(missing_mask.sum())
            inactive_count = int(inactive_mask.sum())
            matched_count = int(len(frame) - missing_count)
            if missing_count or inactive_count:
                issues.extend(_boundary_issues(frame, missing_mask | inactive_mask, source_file))
            out = frame[
                [
                    "legal_dong_code",
                    "source_code",
                    "source_name",
                    "mapping_status",
                    "geom",
                ]
            ].copy()
            out["boundary_level"] = source_layer
            out["source_layer"] = source_layer
            out["source_file"] = source_file
            out.to_postgis(
                LEGAL_DONG_BOUNDARY_TABLE,
                self.engine,
                schema=self.schema,
                if_exists="append",
                index=False,
                chunksize=batch_size,
                dtype={"geom": _geometry_type(self.srid)},
            )
            total_loaded += len(out)
            total_matched += matched_count
            total_missing += missing_count
            total_inactive += inactive_count
        return BoundaryLoadResult(
            loaded=total_loaded,
            matched=total_matched,
            missing=total_missing,
            inactive=total_inactive,
            files=tuple(files),
            issues=tuple(issues),
        )

    def boundary_mapping_issues(self, *, limit: int = 100) -> list[RowMapping]:
        view = _qualified_name(LEGAL_DONG_BOUNDARY_ISSUES_VIEW, self.schema)
        with self.engine.connect() as connection:
            return list(
                connection.execute(
                    text(
                        f"SELECT * FROM {view} ORDER BY source_file, source_code LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )

    def _copy_legal_dong_records(
        self,
        records: Iterable[LegalDongRecord],
        *,
        source: str,
        replace: bool,
    ) -> int:
        table = _qualified_name(LEGAL_DONG_TABLE, self.schema)
        columns = ", ".join(_quote_ident(column) for column in LEGAL_DONG_COPY_COLUMNS)
        copy_sql = f"COPY {table} ({columns}) FROM STDIN"
        count = 0
        with self.engine.begin() as connection:
            if replace:
                connection.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            driver_connection = getattr(connection.connection, "driver_connection", None)
            if driver_connection is None or not driver_connection.__class__.__module__.startswith(
                "psycopg"
            ):
                return self._insert_legal_dong_records(
                    records,
                    source=source,
                    replace=False,
                    batch_size=10_000,
                )
            with driver_connection.cursor() as cursor:
                with cursor.copy(copy_sql) as copy:
                    for record in records:
                        copy.write_row(_legal_dong_row(record, source))
                        count += 1
        return count

    def _insert_legal_dong_records(
        self,
        records: Iterable[LegalDongRecord],
        *,
        source: str,
        replace: bool,
        batch_size: int,
    ) -> int:
        count = 0
        batch: list[dict[str, Any]] = []
        with self.engine.begin() as connection:
            if replace:
                connection.execute(
                    text(
                        "TRUNCATE TABLE "
                        f"{_qualified_name(LEGAL_DONG_TABLE, self.schema)} CASCADE"
                    )
                )
            for record in records:
                batch.append(
                    dict(zip(LEGAL_DONG_COPY_COLUMNS, _legal_dong_row(record, source), strict=True))
                )
                if len(batch) >= batch_size:
                    connection.execute(insert(self.legal_dong_table), batch)
                    count += len(batch)
                    batch = []
            if batch:
                connection.execute(insert(self.legal_dong_table), batch)
                count += len(batch)
        return count

    def _legal_status_lookup(self) -> dict[str, bool]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    self.legal_dong_table.c.legal_dong_code,
                    self.legal_dong_table.c.is_active,
                )
            )
            return {str(code): bool(is_active) for code, is_active in rows}


def make_postgis_metadata(*, schema: str | None = "public", srid: int = 5179) -> MetaData:
    metadata = MetaData(schema=schema)
    legal = Table(
        LEGAL_DONG_TABLE,
        metadata,
        Column("legal_dong_code", String(10), primary_key=True),
        Column("legal_dong_name", String(200), nullable=False),
        Column("status_name", String(20), nullable=False, default=""),
        Column("is_active", Boolean, nullable=False, default=True),
        Column("previous_legal_dong_code", String(10)),
        Column("sido_code", String(2), nullable=False),
        Column("sigungu_code", String(5), nullable=False),
        Column("eup_myeon_dong_code", String(8), nullable=False),
        Column("ri_code", String(2), nullable=False),
        Column("legal_dong_level", String(20), nullable=False),
        Column("source", String(300), nullable=False),
        Column("loaded_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("char_length(legal_dong_code) = 10", "ck_legal_dong_code_len"),
        CheckConstraint("char_length(sido_code) = 2", "ck_legal_dong_sido_len"),
        Index("ix_legal_dong_codes_sigungu", "sigungu_code"),
        Index("ix_legal_dong_codes_emd", "eup_myeon_dong_code"),
        Index("ix_legal_dong_codes_active", "is_active"),
    )
    Table(
        LEGAL_DONG_BOUNDARY_TABLE,
        metadata,
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column(
            "legal_dong_code",
            String(10),
            ForeignKey(legal.c.legal_dong_code, name="fk_boundary_legal_dong_code"),
            nullable=True,
        ),
        Column("boundary_level", String(30), nullable=False),
        Column("source_layer", String(80), nullable=False),
        Column("source_file", String(260), nullable=False),
        Column("source_code", String(30), nullable=False),
        Column("source_name", String(200), nullable=False),
        Column("mapping_status", String(40), nullable=False),
        Column("geom", _geometry_type(srid), nullable=False),
        UniqueConstraint("source_layer", "source_code", name="uq_boundary_source_layer_code"),
        Index("ix_legal_dong_boundaries_legal_code", "legal_dong_code"),
        Index("ix_legal_dong_boundaries_source_code", "source_code"),
        Index("ix_legal_dong_boundaries_mapping_status", "mapping_status"),
    )
    return metadata


def read_boundary_zip(path: str | Path, *, srid: int = 5179, encoding: str = "cp949") -> Any:
    """Read one zipped shapefile with GeoPandas and normalize geometry to geom."""

    try:
        import geopandas as gpd
        from shapely.geometry import MultiPolygon, Polygon
    except ImportError as exc:
        raise RuntimeError(
            "geopandas and shapely are required for boundary ZIP loading. "
            "Install pykraddr[postgis]."
        ) from exc

    archive_path = Path(path)
    with tempfile.TemporaryDirectory(prefix="pykraddr-shp-") as tmp:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(tmp)
        shp_files = list(Path(tmp).glob("*.shp"))
        if not shp_files:
            raise ValueError(f"{archive_path}: shapefile member was not found")
        frame = gpd.read_file(shp_files[0], encoding=encoding)
    if frame.crs is None:
        frame = frame.set_crs(epsg=srid, allow_override=True)
    elif frame.crs.to_epsg() != srid:
        frame = frame.to_crs(epsg=srid)
    frame = frame.rename_geometry("geom")

    def force_multipolygon(geometry: Any) -> Any:
        if isinstance(geometry, Polygon):
            return MultiPolygon([geometry])
        return geometry

    frame["geom"] = frame["geom"].apply(force_multipolygon)
    return frame


def boundary_level_from_path(path: str | Path) -> str:
    stem = Path(path).stem.upper()
    if "G001" in stem:
        return "sido"
    if "G010" in stem:
        return "sigungu"
    if "G011" in stem:
        return "eup_myeon_dong"
    return "unknown"


def _legal_dong_row(record: LegalDongRecord, source: str) -> tuple[Any, ...]:
    return (
        record.legal_dong_code,
        record.legal_dong_name,
        record.status_name,
        record.is_active,
        record.previous_legal_dong_code,
        record.sido_code,
        record.sigungu_code,
        record.eup_myeon_dong_code,
        record.ri_code,
        record.legal_dong_level,
        source,
        datetime.now(UTC),
    )


def _geometry_type(srid: int) -> Any:
    try:
        from geoalchemy2 import Geometry
    except ImportError as exc:
        raise RuntimeError("geoalchemy2 is required for PostGIS support") from exc
    return Geometry("MULTIPOLYGON", srid=srid, spatial_index=True)


def _pick_column(columns: Iterable[Any], candidates: Iterable[str]) -> str | None:
    available = {str(column).upper(): str(column) for column in columns}
    for candidate in candidates:
        value = available.get(candidate.upper())
        if value is not None:
            return value
    return None


def _boundary_issues(frame: Any, mask: Any, source_file: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for row in frame.loc[mask, ["source_code", "source_name", "mapping_status"]].to_dict("records"):
        row["source_file"] = source_file
        issues.append(row)
    return issues


def _table_key(name: str, schema: str | None) -> str:
    return f"{schema}.{name}" if schema else name


def _qualified_name(name: str, schema: str | None) -> str:
    return f"{_quote_ident(schema)}.{_quote_ident(name)}" if schema else _quote_ident(name)


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
