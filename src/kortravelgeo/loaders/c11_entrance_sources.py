"""C11 entrance-source distance comparison prototype."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    AugmentGroupResult,
    AugmentReport,
    DistanceMeasurement,
    JoinKey,
    KeyOverlapMeasurement,
    ShapeStagingSpec,
    SidoPathPattern,
    SidoSourceGroup,
    StagingColumn,
    StagingKeyIndexSpec,
    copy_shape_file_to_staging,
    copy_zip_shape_layer_to_staging,
    create_staging_key_indexes,
    discover_sido_source_groups,
    measure_key_overlap,
    measure_keyed_distance,
    recreate_shape_staging_table,
)
from kortravelgeo.loaders.building_shape_bundle import (
    BUNDLE_ENTRANCE_LAYER,
    ELECTRONIC_ENTRANCE_LAYER,
    ENTRANCE_KEY_FIELDS,
    compare_building_shape_bundle,
)
from kortravelgeo.loaders.juso_map import discover_sido_dataset
from kortravelgeo.loaders.shape_dbf import KeyOverlap

C11_BUNDLE_SOURCE_KEY = "bundle"
C11_ELECTRONIC_SOURCE_KEY = "electronic"

C11_BUNDLE_ENTRANCE_TABLE = "_ktg_c11_bundle_entrc"
C11_ELECTRONIC_ENTRANCE_TABLE = "_ktg_c11_electronic_entrc"

FULL_ENTRANCE_JOIN_KEYS: tuple[JoinKey, ...] = tuple(
    JoinKey(field.lower(), field.lower()) for field in ENTRANCE_KEY_FIELDS
)
WEAK_SIG_ENT_JOIN_KEYS: tuple[JoinKey, ...] = (
    JoinKey("sig_cd", "sig_cd"),
    JoinKey("ent_man_no", "ent_man_no"),
)


@dataclass(frozen=True, slots=True)
class C11PairComparison:
    name: str
    left_source: str
    right_source: str
    key_contract: str
    join_keys: tuple[JoinKey, ...]
    overlap: KeyOverlapMeasurement
    distance: DistanceMeasurement
    note: str | None = None

    def metrics(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "left_source": self.left_source,
            "right_source": self.right_source,
            "key_contract": self.key_contract,
            "join_keys": tuple((key.left, key.right) for key in self.join_keys),
            "key_overlap": _table_key_overlap_metrics(self.overlap),
            "distance_m": _distance_metrics(self.distance),
        }
        if self.note is not None:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True, slots=True)
class C11EntranceComparison:
    sido_name: str
    bundle_zip: str
    electronic_map_dir: str
    source_yyyymm: str | None
    bundle_rows: int
    electronic_rows: int
    dbf_exact_key_overlap: KeyOverlap
    pairs: tuple[C11PairComparison, ...]

    def metrics(self) -> dict[str, object]:
        return {
            "sido_name": self.sido_name,
            "bundle_zip": self.bundle_zip,
            "electronic_map_dir": self.electronic_map_dir,
            "source_yyyymm": self.source_yyyymm,
            "staging_rows": {
                "bundle_tl_spbd_entrc": self.bundle_rows,
                "electronic_tl_spbd_entrc": self.electronic_rows,
            },
            "dbf_exact_key_overlap": _dbf_key_overlap_metrics(self.dbf_exact_key_overlap),
            "comparisons": {pair.name: pair.metrics() for pair in self.pairs},
            "serving_promotion": False,
        }

    def sample(self) -> tuple[Mapping[str, object], ...]:
        rows: list[Mapping[str, object]] = []
        for pair in self.pairs:
            for item in pair.distance.sample:
                row: dict[str, object] = {
                    "comparison": pair.name,
                    "key_contract": pair.key_contract,
                }
                row.update(item)
                rows.append(row)
        return tuple(rows)

    def to_payload(self) -> AugmentGroupPayload:
        return AugmentGroupPayload(
            metrics=self.metrics(),
            sample=self.sample(),
            source_yyyymm=self.source_yyyymm,
        )


def entrance_staging_spec(table_name: str) -> ShapeStagingSpec:
    return ShapeStagingSpec(
        table_name=table_name,
        columns=(
            StagingColumn("sig_cd", source_field="SIG_CD"),
            StagingColumn("bul_man_no", sql_type="bigint", source_field="BUL_MAN_NO"),
            StagingColumn("ent_man_no", sql_type="bigint", source_field="ENT_MAN_NO"),
            StagingColumn("eqb_man_sn", sql_type="bigint", source_field="EQB_MAN_SN"),
        ),
        geometry_type="Point",
    )


def c11_staging_index_specs(
    *,
    bundle_table: str = C11_BUNDLE_ENTRANCE_TABLE,
    electronic_table: str = C11_ELECTRONIC_ENTRANCE_TABLE,
) -> tuple[StagingKeyIndexSpec, ...]:
    return (
        StagingKeyIndexSpec(
            table_name=bundle_table,
            index_name="_idx_ktg_c11_bundle_full_key",
            columns=tuple(key.left for key in FULL_ENTRANCE_JOIN_KEYS),
        ),
        StagingKeyIndexSpec(
            table_name=bundle_table,
            index_name="_idx_ktg_c11_bundle_weak_sig_ent",
            columns=tuple(key.left for key in WEAK_SIG_ENT_JOIN_KEYS),
        ),
        StagingKeyIndexSpec(
            table_name=electronic_table,
            index_name="_idx_ktg_c11_electronic_full_key",
            columns=tuple(key.right for key in FULL_ENTRANCE_JOIN_KEYS),
        ),
    )


def discover_c11_entrance_source_groups(
    *,
    bundle_root: Path | str,
    electronic_map_root: Path | str,
    sido_names: Sequence[str] | None = None,
) -> tuple[SidoSourceGroup, ...]:
    patterns = (
        SidoPathPattern(
            C11_BUNDLE_SOURCE_KEY,
            Path(bundle_root),
            "*{sido}*.zip",
        ),
        SidoPathPattern(
            C11_ELECTRONIC_SOURCE_KEY,
            Path(electronic_map_root),
            "{sido}",
        ),
    )
    if sido_names is None:
        return discover_sido_source_groups(patterns)
    return discover_sido_source_groups(patterns, sido_names=sido_names)


async def compare_c11_entrance_sources(
    engine: AsyncEngine,
    bundle_zip: Path | str,
    electronic_map_sido_dir: Path | str,
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    locsum_table: str = "tl_locsum_entrc",
    roadaddr_table: str = "tl_roadaddr_entrc",
    bundle_table: str = C11_BUNDLE_ENTRANCE_TABLE,
    electronic_table: str = C11_ELECTRONIC_ENTRANCE_TABLE,
) -> C11EntranceComparison:
    bundle_path = Path(bundle_zip)
    electronic_root = Path(electronic_map_sido_dir)
    key_comparison = compare_building_shape_bundle(bundle_path, electronic_root)
    dataset = discover_sido_dataset(electronic_root)
    electronic_entrance = dataset.layer(ELECTRONIC_ENTRANCE_LAYER)

    bundle_spec = entrance_staging_spec(bundle_table)
    electronic_spec = entrance_staging_spec(electronic_table)
    await recreate_shape_staging_table(engine, bundle_spec)
    await recreate_shape_staging_table(engine, electronic_spec)
    bundle_rows = await copy_zip_shape_layer_to_staging(
        engine,
        bundle_spec,
        bundle_path,
        BUNDLE_ENTRANCE_LAYER,
        fields=ENTRANCE_KEY_FIELDS,
    )
    electronic_rows = await copy_shape_file_to_staging(
        engine,
        electronic_spec,
        electronic_entrance.shp_path,
        electronic_entrance.dbf_path,
        fields=ENTRANCE_KEY_FIELDS,
    )
    await create_staging_key_indexes(
        engine,
        c11_staging_index_specs(
            bundle_table=bundle_table,
            electronic_table=electronic_table,
        ),
    )

    pairs = (
        await _measure_pair(
            engine,
            name="bundle_to_electronic_full_key",
            left_source="roadaddr_building_shape_bundle.TL_SPBD_ENTRC",
            left_table=bundle_table,
            right_source="electronic_map_full.TL_SPBD_ENTRC",
            right_table=electronic_table,
            key_contract="full_sig_bul_ent_eqb_key",
            join_keys=FULL_ENTRANCE_JOIN_KEYS,
            sample_limit=sample_limit,
        ),
        await _measure_pair(
            engine,
            name="bundle_to_locsum_weak_sig_ent_key",
            left_source="roadaddr_building_shape_bundle.TL_SPBD_ENTRC",
            left_table=bundle_table,
            right_source="tl_locsum_entrc",
            right_table=locsum_table,
            key_contract="weak_sig_ent_key",
            join_keys=WEAK_SIG_ENT_JOIN_KEYS,
            sample_limit=sample_limit,
            note=(
                "tl_locsum_entrc does not preserve BUL_MAN_NO/EQB_MAN_SN, "
                "so this pair is keyed only by sig_cd + ent_man_no."
            ),
        ),
        await _measure_pair(
            engine,
            name="bundle_to_roadaddr_weak_sig_ent_key",
            left_source="roadaddr_building_shape_bundle.TL_SPBD_ENTRC",
            left_table=bundle_table,
            right_source="tl_roadaddr_entrc",
            right_table=roadaddr_table,
            key_contract="weak_sig_ent_key",
            join_keys=WEAK_SIG_ENT_JOIN_KEYS,
            sample_limit=sample_limit,
            note=(
                "tl_roadaddr_entrc does not preserve BUL_MAN_NO/EQB_MAN_SN "
                "and ent_man_no may be NULL, so this pair is keyed only by "
                "non-null sig_cd + ent_man_no."
            ),
        ),
    )
    return C11EntranceComparison(
        sido_name=key_comparison.sido_name,
        bundle_zip=str(bundle_path),
        electronic_map_dir=str(electronic_root),
        source_yyyymm=source_yyyymm,
        bundle_rows=bundle_rows,
        electronic_rows=electronic_rows,
        dbf_exact_key_overlap=key_comparison.entrance_key_overlap,
        pairs=pairs,
    )


async def build_c11_entrance_report(
    engine: AsyncEngine,
    groups: Iterable[SidoSourceGroup],
    *,
    source_yyyymm: str | None = None,
    sample_limit: int = 20,
    generated_at: datetime | None = None,
) -> AugmentReport:
    results: list[AugmentGroupResult] = []
    for group in groups:
        if group.missing_keys:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="skipped",
                    metrics={},
                    error="missing required source(s): " + ", ".join(group.missing_keys),
                )
            )
            continue
        try:
            comparison = await compare_c11_entrance_sources(
                engine,
                group.path(C11_BUNDLE_SOURCE_KEY),
                group.path(C11_ELECTRONIC_SOURCE_KEY),
                source_yyyymm=source_yyyymm,
                sample_limit=sample_limit,
            )
        except Exception as exc:
            results.append(
                AugmentGroupResult(
                    group_id=group.sido_name,
                    sido_name=group.sido_name,
                    status="failed",
                    metrics={},
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        payload = comparison.to_payload()
        results.append(
            AugmentGroupResult(
                group_id=group.sido_name,
                sido_name=group.sido_name,
                status="used",
                metrics=payload.metrics,
                sample=payload.sample,
                source_yyyymm=payload.source_yyyymm or source_yyyymm,
            )
        )
    return AugmentReport(
        task_id="T-111",
        title="C11 entrance-source distance comparison",
        generated_at=(generated_at or datetime.now(UTC)).isoformat(),
        groups=tuple(results),
        source_yyyymm=source_yyyymm,
    )


async def drop_c11_entrance_staging_tables(
    engine: AsyncEngine,
    *,
    tables: Sequence[str] = (C11_BUNDLE_ENTRANCE_TABLE, C11_ELECTRONIC_ENTRANCE_TABLE),
) -> None:
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))


async def _measure_pair(
    engine: AsyncEngine,
    *,
    name: str,
    left_source: str,
    left_table: str,
    right_source: str,
    right_table: str,
    key_contract: str,
    join_keys: tuple[JoinKey, ...],
    sample_limit: int,
    note: str | None = None,
) -> C11PairComparison:
    overlap = await measure_key_overlap(engine, left_table, right_table, join_keys)
    distance = await measure_keyed_distance(
        engine,
        left_table,
        right_table,
        join_keys,
        sample_limit=sample_limit,
    )
    return C11PairComparison(
        name=name,
        left_source=left_source,
        right_source=right_source,
        key_contract=key_contract,
        join_keys=join_keys,
        overlap=overlap,
        distance=distance,
        note=note,
    )


def _distance_metrics(value: DistanceMeasurement) -> dict[str, object]:
    return {
        "samples": value.samples,
        "p50_m": value.p50_m,
        "p95_m": value.p95_m,
        "max_m": value.max_m,
    }


def _table_key_overlap_metrics(value: KeyOverlapMeasurement) -> dict[str, int]:
    return {
        "left_rows": value.left_rows,
        "right_rows": value.right_rows,
        "left_distinct": value.left_distinct,
        "right_distinct": value.right_distinct,
        "left_duplicate_count": value.left_duplicate_count,
        "right_duplicate_count": value.right_duplicate_count,
        "intersection_count": value.intersection_count,
        "left_only_count": value.left_only_count,
        "right_only_count": value.right_only_count,
    }


def _dbf_key_overlap_metrics(value: KeyOverlap) -> dict[str, int]:
    return {
        "left_rows": value.left.row_count,
        "right_rows": value.right.row_count,
        "left_distinct": value.left.distinct_count,
        "right_distinct": value.right.distinct_count,
        "left_duplicate_count": value.left.duplicate_count,
        "right_duplicate_count": value.right.duplicate_count,
        "intersection_count": value.intersection_count,
        "left_only_count": value.left_only_count,
        "right_only_count": value.right_only_count,
    }
