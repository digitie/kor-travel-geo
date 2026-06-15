# T-110 보강 검증 공통 harness

T-110은 T-111~T-117 보강 원천 prototype이 반복해서 필요로 하는 공통 기반을 추가한다. 목적은 특정 원천의 결론을 미리 내리는 것이 아니라, 각 prototype이 같은 방식으로 시도별 파일 묶음을 순회하고 SHP geometry를 staging에 올린 뒤 PostGIS metric을 산출하게 하는 것이다.

## 구현 범위

- `src/kortravelgeo/loaders/augment_harness.py`
  - 17개 시도 기준 `SidoSourceGroup` 순회 driver
  - `AugmentReport` / `AugmentGroupResult` / `AugmentGroupPayload`
  - SHP body parser: `Point`, `PolyLine`, `Polygon`
  - DBF row와 SHP record를 맞춘 `ShapeFeature` iterator
  - ZIP 내부 layer iterator
  - PostGIS staging table 생성 SQL, `COPY FROM STDIN` helper
  - key join 기반 `ST_Distance` / `ST_Covers` / distinct key overlap 측정 helper
- `tests/unit/test_augment_harness.py`
  - synthetic SHP/DBF로 point/polyline/polygon parser와 DBF alignment 검증
  - 시도 group discovery, report used/skipped/failed 집계 검증
  - staging SQL과 measurement SQL 계약 검증
- `tests/integration/test_optional_real_postgres_augment_harness.py`
  - `KTG_SLOW_REAL_DATA=1`과 `KTG_TEST_PG_DSN`이 모두 있을 때만 실행하는 PostGIS smoke test
  - staging COPY 후 `ST_Distance` / `ST_Covers` helper를 실제 DB에서 검증

## 비범위

- C11~C17 각 case의 도메인 판정은 T-111~T-117에서 구현한다.
- serving 좌표 ranking, `mv_geocode_target`, v1/v2 응답 구조는 변경하지 않는다.
- `ops.source_*` registry나 T-200대 upload/match-set 구현에 의존하지 않는다.
- 기존 `building_shape_bundle.py` / `extra_shape_layers.py`의 DBF key overlap 로직은 중복 구현하지 않고 후속 task에서 계속 재사용한다.

## 사용 예시

```python
from pathlib import Path

from kortravelgeo.loaders.augment_harness import (
    JoinKey,
    ShapeStagingSpec,
    SidoPathPattern,
    StagingColumn,
    copy_zip_shape_layer_to_staging,
    discover_sido_source_groups,
    measure_key_overlap,
    measure_keyed_distance,
    recreate_shape_staging_table,
)

groups = discover_sido_source_groups(
    (
        SidoPathPattern(
            "building_bundle",
            Path("data/juso/unused/도로명주소 건물 도형"),
            "*{sido}*.zip",
        ),
    )
)

spec = ShapeStagingSpec(
    "_ktg_aug_bundle_entrc",
    (
        StagingColumn("sig_cd", source_field="SIG_CD"),
        StagingColumn("ent_man_no", source_field="ENT_MAN_NO"),
    ),
    geometry_type="Point",
)

await recreate_shape_staging_table(engine, spec)
await copy_zip_shape_layer_to_staging(
    engine,
    spec,
    groups[0].path("building_bundle"),
    "TL_SPBD_ENTRC",
    fields=("SIG_CD", "ENT_MAN_NO"),
)

overlap = await measure_key_overlap(
    engine,
    "_ktg_aug_bundle_entrc",
    "tl_locsum_entrc",
    (JoinKey("sig_cd", "sig_cd"), JoinKey("ent_man_no", "ent_man_no")),
)

distance = await measure_keyed_distance(
    engine,
    "_ktg_aug_bundle_entrc",
    "tl_locsum_entrc",
    (JoinKey("sig_cd", "sig_cd"), JoinKey("ent_man_no", "ent_man_no")),
)
```

파일 경로와 ZIP layer iterator는 실제 대용량 원천에서 SHP/DBF 전체를 `bytes`로 올리지 않고 header와 record를 순차 읽는다. 단위 테스트용 `iter_shape_features_from_buffers()`는 synthetic fixture 편의를 위해 유지하지만, 라이브 원천 copy 경로는 stream iterator를 사용한다.

`measure_key_overlap()`은 양쪽 key tuple의 `left_rows`, `right_rows`, distinct 수, intersection, left/right-only 수를 산출한다. C11~C17 문서에서 `coverage_ratio`가 `NULL`이면 비교 가능한 sample 자체가 없다는 뜻이며, 0% coverage와 구분해서 해석한다.

## 후속 작업 메모

- T-111은 `building_shape_bundle.py`의 `ENTRANCE_KEY_FIELDS`를 유지하면서 새 point staging helper로 출입구 간 거리 분포를 산출한다.
- T-112는 `TL_SPOT_CNTC` polyline staging과 도로 layer 인접성 측정을 이 harness 위에 얹는다.
- T-113은 상세주소 동 polygon / 동 출입구 point를 staging하고 `ST_Covers` metric을 사용한다.
- T-121~T-123 전국 실행·벤치 단계에서는 이 harness의 wall-time/RSS/I/O를 case별 artifact로 남긴다.
