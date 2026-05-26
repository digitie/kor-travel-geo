# T-027 후속 데이터 품질 분석 계획

PR #14는 실제 전국 full-load 중 발견한 실행/스키마/로더 문제를 빠르게 막는 fixup 성격이다. PR #14는 close 예정이므로, 남은 C2/C4/C6/C7 `ERROR`는 이 문서 기준으로 별도 PR에서 분석한다.

## 현재 기준

- 실행 환경: WSL2 ext4 작업본, Docker PostGIS `kraddr-geo-t027-db-1`, `localhost:15432`
- 기준 데이터: `~/kraddr-geo-data/juso`
- 기준 검증 명령:

```bash
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo \
KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
.venv/bin/kraddr-geo validate consistency --cases=C2,C4,C6,C7 --scope=t027-data-quality-followup
```

2026-05-25 선택 재검증 결과:

| 케이스 | 건수 | 새 metric | 1차 판단 |
|--------|-----:|-----------|----------|
| C2 | 34,699 | `missing_text=34,118`, `missing_resolve_key=581` | SHP에는 polygon이 있으나 텍스트 정본에는 같은 natural key가 없는 건과 SHP natural key 결측 건이 섞여 있음 |
| C4 | 3,415 | `over_500m=16`, `error_count=16` | 대부분은 50m 초과 WARN이며, 500m 초과 16건은 지도 확인 우선 |
| C6 | 803 | `outside_polygon=803` | `ST_Covers` 전환 후에도 유지되어 경계 위 오탐 가능성은 낮음 |
| C7 | 6,817 | `outside_polygon=6,817` | `ST_Covers` 전환 후에도 유지되어 행정구역 경계/좌표 원천 차이 가능성 |

## 분석 원칙

- 원천 데이터를 임의로 보정하지 않는다. 우선 원천 간 차이를 재현 가능한 sample과 SQL로 분류한다.
- sample은 `bd_mgt_sn`, natural key, 좌표, 거리, 관련 polygon id, 가능한 경우 `source_file`을 함께 남긴다.
- 지도 확인은 디버그 UI와 VWorld/MapLibre wrapper를 사용한다. 범용 wrapper 문제나 표시 한계가 발견되면 `digitie/maplibre-vworld-js`도 수정 대상에 포함하고, 데이터 품질 sample 표시처럼 이 프로젝트에만 의미가 있는 overlay는 `kraddr-geo-ui`에 둔다.
- C6/C7은 `ST_Covers`를 기준으로 한다. `ST_Contains`로 되돌리지 않는다.
- full-load DB를 다시 만들 때는 `docs/t027-fullload-plan.md`의 Docker project/volume/timeout 기준을 따른다.

## 후속 작업

1. C2를 `missing_text`와 `missing_resolve_key`로 나눠 sample CSV를 뽑는다. PR #17에서 `kraddr-geo validate data-quality-samples`로 구현했다.
2. C2 `missing_resolve_key=581`은 SHP row의 `rds_sig_cd`, `rn_cd`, `bjd_cd`, 건물번호 컬럼 결측 여부를 집계한다. PR #17 실제 실행에서는 581건 전부 `rds_sig_cd` 결측이었다.
3. C2 `missing_text=34,118`은 텍스트 정본의 삭제/변동분 누락인지, SHP polygon의 과거 건물 잔존인지 확인한다. PR #17은 우선 sample 좌표와 natural key를 CSV로 남긴다.
4. C4 `over_500m=16`은 디버그 UI 지도에서 출입구 point와 후보 polygon을 함께 표시한다. PR #17 CSV는 출입구/건물 polygon 대표점 좌표와 `delta_lon`/`delta_lat`를 함께 남긴다.
5. C4 50m 초과 WARN 3,399건은 거리 bucket별(`50~100`, `100~500`, `500+`)로 분포를 나눈다. PR #17 실제 실행에서는 `50~100=2,847`, `100~500=552`, `500+=16`으로 확인했다.
6. C6/C7은 `outside_polygon` sample을 우편번호/행정구역별로 묶어 특정 지역 경계 문제인지 확인한다. PR #17은 case별 sample CSV와 region summary CSV를 생성한다.
7. GDAL append 경로에서 `source_file`이 NULL인 문제를 보강한다. PR #17부터 SHP loader는 `source_file=<시도>/<시군구코드>/<레이어>.shp`, `source_yyyymm=<옵션값>`을 SQL projection에 넣는다.
8. 최종 PR에는 SQL, sample 파일 경로, 지도 스크린샷 또는 재현 명령, 기존 건수 대비 변화량을 모두 포함한다.

## PR #17 구현

새 CLI:

```bash
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo \
KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
.venv/bin/kraddr-geo validate data-quality-samples \
  --output-dir artifacts/fullload/pr17-data-quality \
  --cases C2,C4,C6,C7 \
  --limit 200
```

생성 파일:

| 파일 | 내용 |
|------|------|
| `c2_samples.csv` | `missing_resolve_key`/`missing_text`별 SHP polygon sample, natural key, 결측 flag, 대표 좌표 |
| `c2_missing_key_summary.csv` | C2 `missing_resolve_key` 내부 결측 컬럼 집계 |
| `c4_distance_samples.csv` | 출입구 point와 가장 가까운 건물 polygon 대표점, 거리 bucket, 좌표 차이 |
| `c4_distance_buckets.csv` | C4 전체 거리 bucket 집계 |
| `c6_samples.csv` / `c6_region_summary.csv` | 우편번호 기초구역 polygon 불일치 sample 및 우편번호별 집계 |
| `c7_samples.csv` / `c7_region_summary.csv` | 행정구역 polygon 불일치 sample 및 읍면동별 집계 |

현재 실제 Docker DB는 PR #17의 SHP `source_file` 보강 전에 적재된 DB이므로, `c4_distance_samples.csv`의 `polygon_source_file`은 비어 있다. 이후 SHP를 재적재하면 polygon 쪽도 `source_file`이 채워진다.

## PR #17 실제 실행 결과

2026-05-25에 기존 T-027 Docker DB(`kraddr-geo-t027-db-1`, `localhost:15432`)에서 `--limit 5`로 전체 CSV export를 실행했다.

| 항목 | 결과 |
|------|------|
| 경과 | 2분 52.45초 |
| 최대 RSS | 79,956KB |
| 산출물 | CSV 8개, 총 48행(header 포함) |
| C2 missing key | 581건 전부 `rds_sig_cd` 결측. 기존 DB는 SHP `source_file` 미채움 상태라 `null_source_file=581` |
| C4 bucket | `0~50=2,887,827`, `50~100=2,847`, `100~500=552`, `500+=16` |
| C6 상위 region | `54002=49`, `48700=23`, `54004=15` |
| C7 상위 region | `48121103=216`, `28260101=167`, `41273104=165` |

C4 상위 20건은 별도로 `--cases C4 --limit 20`으로 재추출했다. 경과는 2분 22.90초, 최대 RSS는 80,008KB였다. `500+` 16건 중 상위 7건은 출입구 좌표 경도가 건물 polygon 대표점보다 약 `+2.0`도 동쪽으로 이동한 형태다. 예를 들어 부산 sample은 출입구 `(131.02008388, 35.09199694)`, polygon `(129.02021257, 35.09195243)`로 위도는 거의 같고 경도만 크게 어긋난다. 이는 polygon 조인 자체보다 일부 위치정보요약DB 출입구 좌표 또는 좌표계 해석의 원천 이상치 가능성이 높다. 다만 자동 보정은 하지 않고, 다음 단계의 지도 overlay와 원천 row 역추적으로 확정한다.

`delta_lon`/`delta_lat` 컬럼 추가 후 `--cases C4 --limit 3`을 다시 실행했다. 경과는 2분 18.48초, 최대 RSS는 80,124KB였고, 상위 3건의 `delta_lon`은 약 `+1.9998~+1.9999`, `delta_lat`은 `0.00005`도 이하였다. 따라서 180km급 C4 이상치는 "같은 위도대에서 경도만 약 2도 동쪽으로 튐" 패턴으로 우선 분류한다.

성능상으로는 C4 export가 `c4_distance_samples.csv`와 `c4_distance_buckets.csv`에서 같은 nearest distance CTE를 두 번 평가한다. 기능 검증은 통과했지만, 사용자가 요청한 후속 T-032 성능 튜닝 PR에서는 이 중복 스캔 제거, 임시 테이블, case별 materialized intermediate를 우선 반영한다. 2026-05-25 사용자 지시에 따라 이번 T-032 PR의 실제 실행 검증은 세종특별시·경상남도 축소 데이터 1회로 제한하고, 전국 full test와 반복 trial은 후속 안정화 단계로 미룬다.

## 산출물

- `artifacts/fullload/<run_id>/c2_samples.csv`
- `artifacts/fullload/<run_id>/c4_over_500m_samples.csv`
- `artifacts/fullload/<run_id>/c6_c7_region_summary.csv`
- `artifacts/fullload/<run_id>/data-quality-report.md`

`artifacts/`는 로컬 산출물이며 Git에 커밋하지 않는다. PR에는 산출물의 핵심 표와 재현 명령만 문서로 옮긴다.
