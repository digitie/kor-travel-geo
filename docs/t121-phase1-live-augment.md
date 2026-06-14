# T-121 phase ① 전국 라이브데이터 보강 실행

T-111~T-117 prototype을 fixture가 아니라 `F:\dev\kor-travel-geo\data\juso` 전국 원천으로 실행했다. 범위는 C11~C17 `AugmentReport` 산출과 `source_yyyymm` 기록이며, ADR-051은 아직 `proposed` 상태이므로 T-119 serving 좌표 scoring은 포함하지 않았다.

## 실행

WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 NTFS `data/`를 symlink로 참조했다. 전자지도는 시도별 ZIP을 artifact 아래에 materialize했고, C17은 `202604_내비게이션용DB_전체분.7z`에서 `match_jibun_*.txt`만 materialize했다.

```bash
.venv/bin/python scripts/run_phase1_augment_reports.py \
  --data-root data/juso \
  --output-dir artifacts/augment/t121-live \
  --case C11 --case C12 --case C13 --case C14 --case C15 --case C16 --case C17 \
  --materialize-navi-7z \
  --pg-statement-timeout-ms 3600000 \
  --git-repo F:/dev/kor-travel-geo-codex
```

산출물은 테스트 미러의 `artifacts/augment/t121-live/` 아래에 남겼다. 실행 로그는 `run.log`, case별 원문은 `c11-t-111.json`~`c17-t-117.json`, 전체 요약은 `summary.json`/`summary.md`다. materialized 입력까지 포함하면 디렉터리 크기는 약 17GiB라 Git에는 커밋하지 않는다.

## 원천 기준월

| case | 원천 | `source_yyyymm` |
|------|------|-----------------|
| C11 | 도로명주소 건물 도형 bundle + 도로명주소 전자지도 | `bundle=202604; electronic=202604` |
| C12 | 도로명주소 건물 도형 bundle + 도로명주소 전자지도 | `bundle=202604; electronic=202604` |
| C13 | 건물군 내 상세주소 동 도형 + 상세주소DB | `detail_dong=202604; detail_address_db=202605` |
| C14 | 국가지점번호 도형 + 중심점 | `202405` |
| C15 | 민원행정기관전자지도 | `202401` |
| C16 | 주소DB + 건물DB | `address_db=202605; building_db=202605` |
| C17 | 내비게이션용DB `match_jibun_*` | `202604` |

## 실행 요약

| case | used | skipped | failed | seconds |
|------|------|---------|--------|---------|
| C11 | 17 | 0 | 0 | 1394.216 |
| C12 | 17 | 0 | 0 | 435.208 |
| C13 | 17 | 0 | 0 | 329.995 |
| C14 | 1 | 0 | 0 | 379.991 |
| C15 | 1 | 0 | 0 | 21.241 |
| C16 | 1 | 0 | 0 | 638.849 |
| C17 | 1 | 0 | 0 | 233.344 |

전체 실행 시간은 4305.836초다. `git_commit`은 `9a8f7ede2246a6b5b33abb59fab47033ca4d1888`로 기록됐다.

## 주요 metric

| case | 핵심 결과 |
|------|-----------|
| C11 | bundle ↔ 전자지도 full key는 left 6,454,571 / intersection 6,405,305 / left overlap 0.992367이고, 거리 p95/max는 0.0m다. `tl_locsum_entrc` weak key overlap은 0.992323, `tl_roadaddr_entrc` weak key overlap은 0.991791이다. weak key의 roadaddr 거리 max 182,347.711957m는 `sig_cd+ent_man_no`만 쓰는 비교 한계로 해석해야 한다. |
| C12 | road key left overlap은 0.999850이다. connection 6,402,036건 중 matched 6,400,903건, missing 1,133건, tolerance 1m 초과 35,932건, dangling 37,065건이다. 거리 p95는 0.088280057m, max는 1,678,706.725722m다. |
| C13 | 상세주소DB `building_management_no` ↔ 동 도형 `BD_MGT_SN` overlap은 0.006066이고, 상세주소DB 도로명주소 key ↔ shape key overlap은 0.008298이다. 동 출입구 `SIG_CD+BUL_MAN_NO`는 polygon key에 195,019/195,019로 모두 매칭된다. 출입구 point containment는 409,672/424,639(0.964754), 상세주소DB address-matched pair containment는 1,927/2,051(0.939542)이다. |
| C14 | shape row와 center row는 각각 10,184,741건이고 resolution별 row count가 일치한다. center invalid row는 0건, center mismatch는 1,489건이며 모두 1km layer bbox mismatch로 나타났다. formatter parent mismatch는 0건이다. |
| C15 | 26,142건 모두 주소 parse에 성공했다. geocode matched 25,534건, missing 608건, point missing 4건, measured 25,530건이다. 거리 p50/p95/max는 8.420146m / 194.349738m / 2,949.396322m이고, 100m 초과 outlier는 3,588건(0.140541)이다. |
| C16 | 건물DB build ↔ `tl_spbd_buld_polygon` natural key overlap은 0.994684, 건물DB build ↔ `tl_juso_text` natural key overlap은 0.998793, 건물DB 지번 ↔ `tl_juso_parcel_link` `pnu+road key` overlap은 0.997444다. 주소DB/건물DB `bd_mgt_sn` 직접 비교 3종은 intersection 0으로 나와 key 계약 또는 parser 차이 분석이 필요하다. |
| C17 | `match_jibun_*` staging row는 8,188,623건이다. `bd_mgt_sn+pnu` 비교는 intersection 0이고, `pnu+road key` 비교는 left 8,188,616 / intersection 1,767,965 / left overlap 0.215905다. `bd_mgt_sn+pnu` 0%는 C16과 같이 T-123에서 key 계약을 재검토한다. |

C11~C13의 일부 right distinct 값은 시도별 group metric의 단순 합산이므로, 같은 운영 테이블 right key가 group마다 반복 집계될 수 있다. 전국 단일 distinct 판단이 필요한 값은 T-123에서 별도 쿼리로 재측정한다.

## 실데이터 실행 중 보정

- C13 실제 `TL_SGCO_RNADR_DONG`에는 `MULTIPOLYGON`이 포함되어 있어 staging geometry type을 `Polygon`에서 `Geometry`로 넓혔다.
- C15 staging SQL type validator는 `double precision` 문자열을 허용하지 않으므로 좌표 보조 컬럼을 동등한 PostgreSQL alias인 `float8`로 고정했다.
- 장기 실행에서 PostGIS 측정 쿼리가 기본 statement timeout에 걸릴 수 있어 T-121 runner에 `--pg-statement-timeout-ms`를 추가하고 full run은 3,600,000ms로 실행했다.
- 기존 C11/C12 prototype은 전자지도 입력을 추출된 디렉터리로 기대하므로 runner가 시도별 ZIP을 artifact 아래에 materialize한다.

## 판정

T-121은 "전국 실데이터로 prototype이 끝까지 도는가"를 확인하는 작업이며 serving 계약은 바꾸지 않는다. C11 full key의 0m 일치는 강한 evidence지만, weak key 거리 이상치와 C16/C17 `bd_mgt_sn` 0% 교집합은 T-122 벤치와 T-123 튜닝·최종 검증에서 다시 다룬다. 다음 작업은 T-122로, 같은 harness의 wall-time/RSS/I/O와 case별 병목을 artifact로 남기는 것이다.
