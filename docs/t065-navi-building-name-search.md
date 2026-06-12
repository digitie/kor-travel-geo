# T-065 내비게이션용DB 시군구용건물명 검색 반영

## 상태

- 상태: 구현 및 실제 DB 검증 완료
- 대상 브랜치: `codex/t065-navi-building-name`
- 기준 DB: Docker PostGIS `kor_travel_geo` (`localhost:15434`)
- 기준 원천: `202604_내비게이션용DB_전체분`

## 목표

T-064에서 `/v2/geocode`의 상위 주소 후보는 행정구역 polygon으로 해결했다. 남은 문제는 `내비게이션용DB_전체분/match_build_*.txt`에 이미 들어 있는 건물명 보조 정보를 검색 후보에 쓰지 않는 점이었다. 특히 사용자 지시에 따라 원천의 `시군구용건물명`을 적재·정규화하고, `mv_geocode_text_search` 후보 추출에 포함한다.

이 작업은 새 외부 원천을 추가하는 것이 아니다. 기존 full-load 필수 원천인 내비게이션용DB를 더 완전하게 보존하고 검색용 helper MV로 전달하는 보강이다.

## 실제 원천 확인

`match_build_*.txt`는 header 없이 pipe-delimited 33컬럼 파일이다. 202604 전국 파일에서 `시군구용건물명`은 20번째 컬럼, loader 기준 `row[19]`에 들어 있다.

| 항목 | 값 |
|------|---:|
| 전국 raw row | 10,721,310 |
| `시군구용건물명` non-empty | 773,407 |
| distinct `시군구용건물명` | 77,790 |
| 좌표 유효 row 적재 후 `tl_navi_buld_centroid` | 10,687,317 |
| 적재 후 `sigungu_buld_nm` non-empty | 773,407 |

상위 빈도는 `주택`, `1동`, `가동`, `2동`, `나동`, `창고`, `A동`, `B동`, `101동`, `102동` 순서였다. 단순 동명뿐 아니라 `엄마집`, `P-101동`처럼 기존 도로명/건물명 검색만으로는 지역 문맥에서 찾기 어려운 값도 포함한다.

## 구현

- `tl_navi_buld_centroid`에 `sigungu_buld_nm`과 generated column `sigungu_buld_nm_nrm`을 추가했다.
- `navi_loader.py`가 `match_build_*.txt`의 `row[19]`를 `sigungu_buld_nm`으로 적재한다.
- `mv_geocode_target`은 대표 `best_navi` row에서 `sigungu_buld_nm`/`sigungu_buld_nm_nrm`을 함께 가져온다.
- `mv_geocode_text_search`는 `sigungu_buld_nm_nrm`을 포함하고, broad fallback에서 trigram 후보로 사용한다.
- Q4 exact preflight는 `idx_mv_sigungu_buld_nm_nrm_exact`를 추가해 `rn_nrm`/`buld_nm_nrm`과 같은 fast path로 처리한다.
- shadow swap 후 `ANALYZE` transaction에도 `statement_timeout=0`을 적용했다. 실제 검증 중 target/helper swap은 성공했지만 후속 `ANALYZE mv_geocode_target`이 기본 statement timeout에 걸렸기 때문이다.
- MV refresh release metadata 기록 경로에도 `statement_timeout=0`을 적용했다. 두 번째 실제 검증에서는 refresh 이후 `SELECT max(source_yyyymm) FROM tl_navi_buld_centroid` source set inference가 기본 timeout에 걸렸고, 이 경로는 대형 테이블 row count/source month를 읽는 운영 작업이므로 API 기본 timeout을 상속하지 않게 했다.

## 인덱스와 크기

실제 DB에서 새 인덱스 크기는 다음과 같다.

| index | 크기 | 용도 |
|-------|-----:|------|
| `idx_mv_sigungu_buld_nm_nrm_exact` | 18MB | exact preflight |
| `idx_mv_text_search_sigungu_buld_nm_trgm` | 10MB | helper MV broad fallback |
| `idx_navi_centroid_sigungu_buld_nm_trgm` | 19MB | 원천 테이블 분석/후속 검색 보조 |

T-061 당시 helper MV는 약 `2,426MiB`였다. T-065 후 실제 helper는 row count `6,416,642`, heap `904MB`, indexes `1,582MB`, total `2,486MB`였다. daily delta 반영으로 row count가 5행 늘어난 상태라 완전한 apple-to-apple 비교는 아니지만, 새 search 컬럼과 인덱스의 추가 비용은 약 `+60MB` 수준으로 관측됐다.

## 전후 결과

변경 전에는 아래 요청이 모두 `NOT_FOUND`였다.

| 요청 | before |
|------|--------|
| `/v2/search`, `query="엄마집"`, `sig_cd="26110"` | `NOT_FOUND`, total 0 |
| `/v2/search`, `query="P-101동"`, `sig_cd="26110"` | `NOT_FOUND`, total 0 |

변경 후에는 같은 요청이 후보를 반환한다.

| 요청 | after | 20회 API p50 | 20회 API p95 |
|------|-------|-------------:|-------------:|
| `엄마집`, `sig_cd=26110` | 부산광역시 중구 영주로 58, total 1 | 6.03ms | 7.42ms |
| `P-101동`, `sig_cd=26110` | 부산광역시 중구 초량상로 13 등, total 4 | 16.53ms | 20.12ms |

`엄마집` exact path의 SQL plan은 `idx_mv_sigungu_buld_nm_nrm_exact` index scan을 사용했고, execution time은 약 `0.197ms`였다.

`P-101동` broad helper path는 `idx_mv_text_search_sigungu_buld_nm_trgm`와 `idx_mv_text_search_sig_buld`의 `BitmapAnd`를 사용했고, execution time은 약 `6.496ms`였다.

## 적재와 refresh 검증

실제 Docker DB에서 다음 순서로 검증했다.

1. `tl_navi_buld_centroid`에 새 컬럼과 원천 테이블 GIN 인덱스를 적용했다.
2. `ktgctl load navi /home/digitie/kor-travel-geo-data/juso/202604_내비게이션용DB_전체분 --yyyymm 202604`
3. 결과: `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`, 소요 `457초`
4. `ktgctl refresh mv --swap`으로 target/helper MV를 새 컬럼 포함 상태로 재생성했다.
5. 후속 `ANALYZE`는 timeout 보강 전 실행에서 실패했으나 shadow swap 자체는 완료됐고, `SET statement_timeout=0` 수동 `ANALYZE`는 `12초`에 완료됐다. 코드에는 동일 timeout 보강을 반영했다.
6. timeout 보강 후 release metadata 기록 경로만 직접 재검증했고, active release `7b3455b6-e682-4d16-92f7-65fcad33e219`가 생성됐다.

## 검증 명령

- `pytest tests/unit/test_navi_loader.py tests/unit/test_infra_repo_sql.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_alembic_migrations.py -q` → `34 passed`
- `pytest tests/integration/test_real_juso_text_loaders.py::test_actual_navi_files_load_building_centroid_and_entrance_rows -q` → `1 passed`
- `ruff check ...` → 통과
- Docker DB smoke:
  - `/v2/search` `엄마집`, `sig_cd=26110` → `OK`
  - `/v2/search` `P-101동`, `sig_cd=26110` → `OK`
  - UI proxy `/api/proxy/v2/search` `엄마집`, `sig_cd=26110` → `OK`
  - `/v2/geocode` `수지구` → 기존 region 후보 유지

## 후속

- `시군구용건물명`은 동명·상가명·별칭 성격이 섞여 있다. 현재는 검색 후보 recall을 높이는 용도로만 사용하고, API 응답의 공식 건물명은 여전히 도로명주소 한글 정본의 `buld_nm`을 사용한다.
- 다음 대형 refresh 검증에서는 `shadow_swap_mv()`와 `record_mv_refresh_release()`의 `statement_timeout=0` 보강 이후 `ktgctl refresh mv --swap` 전체가 exit code 0으로 끝나는지 다시 확인한다.
