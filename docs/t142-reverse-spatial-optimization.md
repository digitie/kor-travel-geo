# T-142 reverse-geocoder 공간 조회 최적화

작성일: 2026-06-16

## 결론

T-142에서는 reverse 공간 조회를 런타임 nearest 경로와 radius-heavy benchmark 경로로
분리했다. 기존에는 Q5 reverse nearest와 Q6 reverse radius benchmark가 같은
`_NEAREST_SQL`을 공유해, 실제 API가 요구하는 "가장 가까운 주소 후보 몇 개"와
반경 prefilter 성능 측정을 구분하기 어려웠다.

이제 런타임 `ReverseRepository.nearest()`는 `_NEAREST_SQL`의 KNN 후보 CTE를 사용한다.
`mv_geocode_target.pt_5179` GiST KNN으로 작은 후보군을 먼저 가져오고, outer query에서
`distance_m <= :radius_m`로 반경을 적용한다. 반경 경계는 포함한다. 후보 CTE는 tie-break
안정성을 위해 `GREATEST(:limit * 8, 64)`까지 over-fetch한다.

Q6 benchmark는 새 `_RADIUS_SQL`을 사용해 기존 `ST_DWithin(t.pt_5179, p.geom, :radius_m)`
prefilter 경로를 계속 측정한다. 이로써 T-141/T-164 matrix에서 Q5와 Q6가 서로 다른 plan
surface를 갖는다.

## 공간 조회 표면

| 경로 | SQL | 기준 | 인덱스 기대 |
|------|-----|------|-------------|
| Reverse nearest runtime | `_NEAREST_SQL` | KNN 후보 CTE → `distance_m <= :radius_m` | `idx_mv_geom5179` KNN |
| Reverse radius benchmark | `_RADIUS_SQL` | `ST_DWithin` prefilter + KNN 정렬 | `idx_mv_geom5179` |
| 우편번호 point lookup | `_ZIP_BY_POINT` | `ST_Covers(k.geom, p.geom)` | `idx_kodis_bas_geom` |
| 국가지점번호 reverse context | `_SPPN_AREAS_SQL` | `ST_Covers(m.geom, p.geom)` | `idx_sppn_makarea_geom` |
| 반경 행정구역 | `_REGIONS_WITHIN_RADIUS_SQL` | `region_radius_parts` + `ST_DWithin` | `idx_region_radius_parts_geom` |

`_ZIP_BY_POINT`는 `ST_Contains`에서 `ST_Covers`로 바꿨다. 우편번호 polygon 경계 위 좌표를
누락하지 않기 위한 변경이며, C6 consistency의 polygon 포함 기준과도 맞춘다.

## 변경하지 않은 범위

- 새 DB table, MV, migration, index는 추가하지 않았다.
- 좌표 외부 인터페이스는 계속 `(lon, lat)`이다.
- reverse 응답 schema, OpenAPI, 프론트엔드 typegen은 바뀌지 않는다.
- `region_radius_parts` 구조와 refresh SQL은 그대로 둔다.
- 건물 polygon reverse point-in-polygon lookup은 아직 API surface가 아니므로 이번 PR에서
  추가하지 않았다. 필요하면 T-144 API 계약 재설계 또는 별도 detail endpoint에서 다룬다.

## Live smoke

WSL ext4 미러에서 기존 benchmark corpus 중 reverse/zipcode/SPPN reverse 7건만 분리해
실행했다.

- artifact: `artifacts/perf/t142-reverse-spatial-smoke/` (WSL 테스트 미러, git ignore)
- 대상 row count: `mv_geocode_target=6,416,637`,
  `mv_geocode_text_search=6,416,637`, `tl_sppn_makarea=24,204`
- error: 0
- p95:
  - `reverse_nearest=18.649ms`
  - `reverse_nearest_sig=3.342ms`
  - `reverse_radius=4.034ms`
  - `reverse_radius_sig=4.253ms`
  - `zipcode_point=3.406ms`
  - `sppn_reverse=8.858ms`
  - `no_result_reverse=7.934ms`
- EXPLAIN:
  - `reverse_nearest`, `reverse_nearest_sig`, `no_result_reverse`: `knn_candidates` CTE,
    `idx_mv_geom5179`
  - `reverse_radius`, `reverse_radius_sig`: `idx_mv_geom5179`
  - `zipcode_point`: `idx_kodis_bas_geom`
  - `sppn_reverse`: `idx_sppn_makarea_geom`

## 검증

```bash
python -m pytest tests/unit/test_infra_repo_sql.py tests/unit/test_t176_reverse_boundary.py tests/unit/test_query_performance_benchmark.py -q
python -m ruff check .
python -m mypy src/kortravelgeo
lint-imports
python scripts/export_openapi.py --check
```
