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
- 지도 확인은 디버그 UI와 VWorld/MapLibre wrapper를 사용한다. wrapper 문제나 표시 한계가 발견되면 `digitie/maplibre-vworld-js`도 수정 대상에 포함한다.
- C6/C7은 `ST_Covers`를 기준으로 한다. `ST_Contains`로 되돌리지 않는다.
- full-load DB를 다시 만들 때는 `docs/t027-fullload-plan.md`의 Docker project/volume/timeout 기준을 따른다.

## 후속 작업

1. C2를 `missing_text`와 `missing_resolve_key`로 나눠 sample CSV를 뽑는다.
2. C2 `missing_resolve_key=581`은 SHP row의 `rds_sig_cd`, `rn_cd`, `bjd_cd`, 건물번호 컬럼 결측 여부를 집계한다.
3. C2 `missing_text=34,118`은 텍스트 정본의 삭제/변동분 누락인지, SHP polygon의 과거 건물 잔존인지 확인한다.
4. C4 `over_500m=16`은 디버그 UI 지도에서 출입구 point와 후보 polygon을 함께 표시한다.
5. C4 50m 초과 WARN 3,399건은 거리 bucket별(`50~100`, `100~500`, `500+`)로 분포를 나눈다.
6. C6/C7은 `outside_polygon` sample을 우편번호/행정구역별로 묶어 특정 지역 경계 문제인지 확인한다.
7. GDAL append 경로에서 `source_file`이 NULL인 문제를 보강한다. 필요하면 SHP layer별 staging table 또는 후처리 update 전략을 설계한다.
8. 최종 PR에는 SQL, sample 파일 경로, 지도 스크린샷 또는 재현 명령, 기존 건수 대비 변화량을 모두 포함한다.

## 산출물

- `artifacts/fullload/<run_id>/c2_samples.csv`
- `artifacts/fullload/<run_id>/c4_over_500m_samples.csv`
- `artifacts/fullload/<run_id>/c6_c7_region_summary.csv`
- `artifacts/fullload/<run_id>/data-quality-report.md`

`artifacts/`는 로컬 산출물이며 Git에 커밋하지 않는다. PR에는 산출물의 핵심 표와 재현 명령만 문서로 옮긴다.
