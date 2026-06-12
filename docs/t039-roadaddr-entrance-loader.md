# T-039: `도로명주소 출입구 정보` direct entrance loader 구현

## 상태

- 상태: 구현 완료
- 대상 브랜치: `codex/t039-direct-entrance-loader`
- 관련 ADR: ADR-023, ADR-024
- 대상 원천: `data/juso/도로명주소 출입구 정보/도로명주소출입구_전체분_*.zip`
- ZIP member: `RNENTDATA_2605_<시군구코드>.txt`

## 목적

기존 대표 출입구 좌표는 `tl_locsum_entrc`에 적재한 위치정보요약DB를 기반으로 한다. 이 원천은 좌표 품질은 좋지만 실제 `entrc_*.txt`가 `bd_mgt_sn`을 직접 제공하지 않아, 적재 후 `rncode_full + 건물번호 + bjd_cd + zip_no`로 `tl_juso_text`와 후해소해야 한다. 전국 full-load에서 `tl_locsum_entrc.bd_mgt_sn` 해소 실패가 C3 WARN의 큰 원인이었다.

`도로명주소 출입구 정보`는 direct `bd_mgt_sn + EPSG:5179 point`를 제공한다. T-039는 이 원천을 별도 테이블 `tl_roadaddr_entrc`에 저장한다. T-027 최종 클린 적재 재검증 전에는 이 테이블이 채워져 있으면 `mv_geocode_target`의 대표 출입구 후보로 `tl_locsum_entrc`보다 먼저 사용하도록 설계했지만, 2026-05-27 전국 실제 적재에서 기준월이 다른 direct 출입구(`202605`)를 `juso=202603`, SHP/locsum/navi=`202604` 세트에 즉시 섞으면 C4/C6/C7 오류가 크게 늘어나는 것이 확인됐다.

따라서 현재 운영 기본값은 `tl_locsum_entrc` 대표 출입구를 먼저 사용하고, `tl_roadaddr_entrc`는 `source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 기준월일 때만 fallback serving 후보로 승격한다. 기준월이 다른 direct 출입구는 테이블에 적재해 원천 추적, 분석, 미래 같은 기준월 세트 검증에는 사용하되, 기본 `mv_geocode_target` 좌표와 C3/C4/C6/C7/C8 serving CTE에는 반영하지 않는다.

이 원천은 202605 계열이고 기존 full-load 기준월(`juso=202603`, `locsum/navi/shp=202604`)과 다르다. 따라서 기본 `full_load_batch` child에는 넣지 않고, 운영자가 별도 job/CLI로 명시 실행한다. 기준월 혼합은 C10에 `tl_roadaddr_entrc`를 포함해 드러낸다. C10은 T-027 최종 클린 적재 보강 이후 `load_manifest`뿐 아니라 각 테이블의 row-level `source_yyyymm`도 집계하므로, 현재 로컬 조합은 `distinct_months=3` WARN으로 기록된다.

## 실제 파일 구조와 계측

전국 17개 ZIP을 직접 읽어 확인했다.

| 항목 | 값 |
|------|----|
| ZIP 수 | 17 |
| 총 원천 행 수 | 6,418,169 |
| 컬럼 수 | 모든 행 19컬럼 |
| `ent_source_cd` | 모든 행 `RM` |
| `ent_detail_cd` | 모든 행 `01` |

시도별 원천 행 수:

| ZIP | 행 수 |
|-----|------:|
| 강원특별자치도 | 369,166 |
| 경기도 | 1,030,545 |
| 경상남도 | 657,845 |
| 경상북도 | 723,220 |
| 광주광역시 | 120,046 |
| 대구광역시 | 228,854 |
| 대전광역시 | 112,414 |
| 부산광역시 | 297,738 |
| 서울특별시 | 524,613 |
| 세종특별자치시 | 27,868 |
| 울산광역시 | 104,734 |
| 인천광역시 | 182,709 |
| 전라남도 | 602,747 |
| 전북특별자치도 | 438,336 |
| 제주특별자치도 | 158,064 |
| 충청남도 | 499,389 |
| 충청북도 | 339,881 |

세종/경남 정밀 계측:

| 지역 | 원천 행 수 | distinct `bd_mgt_sn` | 중복 `bd_mgt_sn` | 빈 `ent_man_no` | 유효 좌표 적재 행 수 |
|------|-----------:|---------------------:|-----------------:|----------------:|--------------------:|
| 세종특별자치시 | 27,868 | 27,868 | 0 | 9 | 27,779 |
| 경상남도 | 657,845 | 657,845 | 0 | 100 | 별도 전체 적재는 PR에서 수행하지 않음 |

중요 결정:

- 실제 샘플에서는 `bd_mgt_sn`이 행마다 유일했다. 따라서 `tl_roadaddr_entrc`는 `bd_mgt_sn` 단독 PK를 사용한다.
- `ent_man_no`는 일부 행에서 비어 있으므로 nullable 보존 필드로 둔다.
- 좌표가 비었거나 `0/0` sentinel인 행은 `geom NOT NULL` 테이블에 넣지 않는다.

첫 행 예시:

```text
36110101200000200181100000|3611010100|세종특별자치시||반곡동||361102000002|한누리대로|0|1811|0|30145|20181204||32169|RM|01|983296.172464|1833330.968984
```

## 스키마

```sql
CREATE TABLE tl_roadaddr_entrc (
  bd_mgt_sn       TEXT PRIMARY KEY,
  bjd_cd          TEXT NOT NULL,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  li_kor_nm       TEXT,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn              TEXT,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  zip_no          TEXT,
  notice_de       TEXT,
  raw_col_13      TEXT,
  ent_man_no      BIGINT,
  ent_source_cd   TEXT NOT NULL,
  ent_detail_cd   TEXT NOT NULL,
  geom            geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

인덱스:

- `idx_roadaddr_entrc_geom`: reverse/MV 공간 확인용 GiST.
- `idx_roadaddr_entrc_bd`: `bd_mgt_sn` 기반 확인용.
- `idx_roadaddr_entrc_road`: 도로명 건물번호 키 기반 cross-check용.

## 로더

파일: `src/kortravelgeo/loaders/text/roadaddr_entrance_loader.py`

CLI:

```bash
ktgctl load roadaddr-entrances "data/juso/도로명주소 출입구 정보" --yyyymm 202605
```

동작:

1. 입력이 ZIP이면 ZIP member 중 `RNENTDATA_*.txt`를 찾는다.
2. 입력이 디렉터리이면 디렉터리 내부의 `*.zip`을 열어 모든 `RNENTDATA_*.txt` member를 찾는다.
3. 19컬럼 pipe-delimited row를 읽는다.
4. 좌표가 없거나 `0/0` sentinel이면 skip한다.
5. `RNENTDATA_2605_*.txt` 파일명에서 `source_yyyymm=202605`를 추론한다. 사용자가 `--yyyymm`을 주면 그 값을 우선한다.
6. 기본값으로 `tl_roadaddr_entrc`를 `TRUNCATE`한 뒤 `bd_mgt_sn` 기준 UPSERT한다.
7. `load_manifest(table_name='tl_roadaddr_entrc')`에 `source_yyyymm`, checksum, `source_set.kind='roadaddr_entrance_full'`을 기록한다.

적재 직후 조회 표면에 반영하려면 `ktgctl refresh mv --swap`을 실행한다. 기존 DB가 T-039 이전 MV 정의를 갖고 있으면 `REFRESH MATERIALIZED VIEW CONCURRENTLY`만으로는 direct 출입구 fallback 규칙이 생기지 않는다. shadow swap은 현재 코드의 `MV_SQL`로 새 MV를 빌드하므로 T-039/T-027 정의 전환까지 함께 처리한다.

API job kind:

- `roadaddr_entrance_load`

`roadaddr_entrance_load`는 경로 기반 작업이므로 명시적 `full_load_batch.children`에 넣을 수 있다. 하지만 기본 `BATCH_SOURCE_KINDS`에는 포함하지 않는다. 기준월 혼합과 운영 의도 확인이 필요하기 때문이다.

## MV/정합성 병합 규칙

`mv_geocode_target`의 대표 좌표 선택 순서:

1. `tl_locsum_entrc` 대표 출입구(`ent_se_cd='0'` 우선)
2. `tl_roadaddr_entrc` direct entrance 중 `source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 후보
3. `tl_navi_buld_centroid` centroid fallback

응답의 `pt_source`는 direct entrance와 locsum entrance 모두 기존 계약처럼 `entrance`로 유지한다. API 응답의 호환성을 깨지 않기 위해 새 `pt_source` 값을 만들지 않았다. 원천별 세부 추적은 `source_file`, `source_yyyymm`, 정합성 sample의 `source_kind`로 확인한다.

정합성 변경:

- C3/C4/C6/C7/C8은 `tl_locsum_entrc`와 same-month `tl_roadaddr_entrc`를 합친 대표 출입구 CTE를 사용한다.
- C10은 `tl_roadaddr_entrc`의 row-level `source_yyyymm`도 기준월 비교 대상에 포함한다.

### T-027 최종 클린 적재에서 확인한 정책 보정

2026-05-27 Docker PostGIS 최종 클린 적재에서 `tl_roadaddr_entrc` 전국 6,404,697건을 `202605`로 적재했다. 기존 우선순위(`roadaddr → locsum → navi`)로 C1~C10을 실행하면 direct 출입구가 `juso=202603`/SHP=`202604`와 다른 기준월이라 C4/C6/C7이 다음처럼 증가했다.

| 조건 | C4 `over_50m` | C4 `over_500m` | C6 | C7 |
|------|--------------:|---------------:|---:|---:|
| `roadaddr` 우선 | 12,225 | 91 | 3,593 | 9,827 |
| `locsum`만 임시 비교 | 3,415 | 16 | 803 | 6,817 |
| same-month gate 적용 후 | 3,415 | 16 | 803 | 6,817 |

따라서 direct 출입구는 "있으면 무조건 더 정확한 좌표"로 보지 않는다. 같은 기준월 세트가 확보되기 전에는 분석용 테이블로 유지하고, serving 좌표는 기존 locsum/navi 경로를 사용한다. 같은 기준월의 `rnaddrkor_*`와 `RNENTDATA_*`를 확보한 뒤 direct 출입구를 다시 승격하려면 `ktgctl refresh mv --swap`과 C3/C4/C6/C7/C8 재검증 결과를 PR 또는 운영 로그에 남긴다.

## 검증

단위/실제 파일 테스트:

- `tests/unit/test_roadaddr_entrance_loader.py`
  - direct `bd_mgt_sn`, `rncode_full`, EPSG:5179 좌표 파싱.
  - 디렉터리 안 ZIP member discovery.
  - 빈 좌표와 `0/0` sentinel skip.
  - 잘못된 `rncode_full` 오류.
- `tests/integration/test_real_roadaddr_entrance_files.py`
  - 실제 세종 ZIP의 유효 좌표 27,779행 파싱.
  - 실제 `data/juso/도로명주소 출입구 정보` 디렉터리에서 17개 ZIP member discovery.

선택형 Docker PostgreSQL 검증:

```bash
dropdb -h localhost -p 15432 -U addr --if-exists kor_travel_geo_t039
createdb -h localhost -p 15432 -U addr kor_travel_geo_t039
KTG_TEST_PG_DSN='postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t039' \
  .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q
```

결과:

- `1 passed in 2.74s`
- 실제 세종 `RNENTDATA_2605_36110.txt` 3행을 `tl_roadaddr_entrc`에 적재.
- `load_manifest.kind='roadaddr_entrance_full'`, `row_count=3`, `source_yyyymm='202605'`, `upserted_rows=3` 확인.
- 같은 `bd_mgt_sn`과 같은 `source_yyyymm`을 가진 테스트 parent를 `tl_juso_text`에 넣고 MV를 생성하면, `pt_source='entrance'`와 `pt_5179` 좌표가 `tl_roadaddr_entrc` 좌표와 일치해야 한다. 기준월이 다르면 direct 출입구는 적재되어도 serving 후보로 쓰지 않는다.

## 남은 작업

- T-040: 완료. `도로명주소 건물 도형` bundle과 전자지도 `TL_SPBD_BULD` 비교.
- T-041: 완료. 상세주소 동 도형과 구역 추가 레이어는 기본 full-load/MV에 섞지 않고 별도 overlay/분석 후보로 둔다.
- T-027 최종 클린 적재: 완료. `tl_roadaddr_entrc`는 적재하되 기준월이 다른 경우 serving 후보에서 제외하는 same-month gate를 추가했다. C10은 row-level 기준월 집계로 `202603/202604/202605` 혼합을 WARN으로 보고한다.
