# T-133 C11 shadow serving 성능·rollback 리허설

작성일: 2026-06-16

## 목적

T-132에서 반복 검증한 `guarded_centroid_c4_50_c6_c7_move_500` 정책을 active serving으로 승격하지 않고, shadow schema에서만 조회 경로를 리허설한다. 검증 목표는 다음 세 가지다.

1. flag off 상태의 public `mv_geocode_target`/`mv_geocode_text_search` row count, 대표 표본 hash, active serving release가 변하지 않는다.
2. flag on 상태의 shadow `mv_geocode_target`/`mv_geocode_text_search`는 같은 row count를 유지하면서 guarded C11 후보점만 사용한다.
3. SQL/REST benchmark p95 회귀가 5% 이하이고 오류가 0건이다. 최종 run은 shadow schema drop으로 rollback을 증명해야 하며, active serving promotion은 하지 않는다.

## 구현

새 스크립트는 `scripts/run_t133_c11_shadow_serving_rehearsal.py`다.

- T-125 후보 table과 T-131 feature table을 필요 시 다시 만든다.
- public `mv_geocode_target`의 column metadata를 읽고, shadow schema에 같은 column set의 `mv_geocode_target` table을 만든다.
- column 중 `pt_5179`와 `pt_4326`만 guarded C11 후보로 치환한다. `pt_source`는 기존 값(`centroid`)을 유지해 v1 호환 표면을 바꾸지 않는다.
- shadow `mv_geocode_text_search`도 shadow target에서 다시 만든다.
- public MV와 같은 hot-path index를 shadow table에 생성하고 `ANALYZE`한다.
- SQL benchmark는 같은 corpus를 public engine과 shadow search path engine에서 각각 실행한다.
- REST benchmark는 `scripts/benchmark_api_latency.py`가 만든 public/shadow JSON report를 받아 같은 비교 함수를 적용한다.

shadow REST 서버를 위해 `KTG_PG_SEARCH_PATH` 설정을 추가했다. 기본값은 `public,x_extension`이라 기존 실행 경로는 변하지 않는다. shadow API 프로세스만 `KTG_PG_SEARCH_PATH=_ktg_t133_shadow,public,x_extension`으로 실행한다.

## 실행 절차

1차 prep run은 staging/feature/shadow table을 만들고 유지한다. 이 단계는 REST benchmark 전에 shadow API 서버를 띄우기 위한 준비 단계라 최종 gate는 통과하지 않는다.

```bash
python scripts/run_t133_c11_shadow_serving_rehearsal.py \
  --pg-database kor_travel_geo_t213_20260615_r3 \
  --output-dir /mnt/f/dev/geodata/t133-c11-shadow-serving-rehearsal/20260616-r1-prep \
  --keep-staging \
  --keep-shadow \
  --skip-sql-benchmark \
  --sample-hash-limit 1000 \
  --sample-limit 50
```

REST benchmark는 같은 corpus로 public API와 shadow API를 따로 측정한다. public API는 기본 search path를 쓰고, shadow API는 `_ktg_t133_shadow,public,x_extension`을 먼저 보게 한다.

```bash
KTG_PG_DSN='postgresql+psycopg://<user>:<password>@127.0.0.1:5432/kor_travel_geo_t213_20260615_r3' \
KTG_GEOIP_GATE_MODE=off \
python -m uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12531

KTG_PG_DSN='postgresql+psycopg://<user>:<password>@127.0.0.1:5432/kor_travel_geo_t213_20260615_r3' \
KTG_PG_SEARCH_PATH=_ktg_t133_shadow,public,x_extension \
KTG_GEOIP_GATE_MODE=off \
python -m uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12532
```

최종 run은 prep run에서 남긴 candidate/feature/shadow를 재사용하고, SQL benchmark와 REST report 비교를 수행한 뒤 shadow schema를 drop한다.

```bash
python scripts/run_t133_c11_shadow_serving_rehearsal.py \
  --pg-database kor_travel_geo_t213_20260615_r3 \
  --output-dir /mnt/f/dev/geodata/t133-c11-shadow-serving-rehearsal/20260616-r1 \
  --reuse-candidate \
  --reuse-features \
  --reuse-shadow \
  --public-rest-report /mnt/f/dev/geodata/t133-c11-shadow-serving-rehearsal/20260616-r1/rest-public/benchmark.json \
  --shadow-rest-report /mnt/f/dev/geodata/t133-c11-shadow-serving-rehearsal/20260616-r1/rest-shadow/benchmark.json \
  --sample-hash-limit 1000 \
  --sample-limit 50
```

## Gate

`gate_result.status`가 `passed`가 되려면 다음을 모두 만족해야 한다.

| 항목 | 조건 |
|------|------|
| 정책 | T-132 정책 hard block 0건 |
| flag off | public target/text-search row count, 표본 hash, active release identity 동일 |
| flag on | shadow target/text-search row count가 public과 동일, 적용 row 1건 이상 |
| SQL | public 대비 shadow p95 회귀 5% 이하, 오류 0건 |
| REST | public 대비 shadow p95 회귀 5% 이하, 오류 0건 |
| rollback | shadow schema drop 완료 |
| 승격 | `active_serving_promotion_allowed=false` 유지 |

`--keep-shadow` 상태는 최종 gate로 인정하지 않는다. REST report가 없거나 `--skip-sql-benchmark`를 사용한 run도 최종 gate에서 blocked 처리한다.

## Live 실행 결과

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| shadow schema | `_ktg_t133_shadow` |
| 산출물 | `F:\dev\geodata\t133-c11-shadow-serving-rehearsal\20260616-r1\` |
| 최종 gate | `blocked` |
| active serving promotion | `false` |

prep run은 C11 후보 staging을 새로 적재한 뒤 shadow index 문법 오류로 한 번 실패했다. PostgreSQL `CREATE INDEX`에서 index 이름은 schema-qualified로 쓰지 않고 schema-qualified table에 unqualified index name을 붙여야 하므로 스크립트를 수정했다. 이후 `_ktg_t125_*` candidate table을 재사용해 feature/shadow 단계부터 재실행했다.

최종 run에서 flag off identity는 전후 동일했다.

| metric | flag off before | flag off after |
|--------|----------------:|---------------:|
| `mv_geocode_target` rows | 6,419,795 | 6,419,795 |
| point rows | 6,404,343 | 6,404,343 |
| `mv_geocode_text_search` rows | 6,419,795 | 6,419,795 |
| sample hash | `98b0cc91c67176575a87ddd856156d8d` | `98b0cc91c67176575a87ddd856156d8d` |

shadow identity도 row count는 public과 같았다.

| metric | 값 |
|--------|---:|
| shadow target rows | 6,419,795 |
| shadow point rows | 6,404,343 |
| shadow text-search rows | 6,419,795 |
| guarded C11 적용 row | 3,482,270 |
| movement >100m warning | 10,099 |
| movement >500m | 0 |

성능 gate는 통과하지 못했다.

| benchmark | 비교 기준 | 결과 |
|-----------|-----------|------|
| SQL | 같은 run의 public vs shadow, 100-case corpus, concurrency 1/4/16/64 | `failed`, max p95 regression 83.087% |
| REST | T-216 `rest-c64-425` baseline vs shadow c64-425 | `failed`, max p95 regression 132.447% |

대표 회귀 row:

| benchmark | group / path | concurrency | baseline/public p95 | shadow p95 | regression |
|-----------|--------------|------------:|--------------------:|-----------:|-----------:|
| SQL | `Q3_FUZZY_GEOCODE/fuzzy_geocode` | 64 | 74.586ms | 136.557ms | 83.087% |
| SQL | `Q1_ROAD_EXACT/road_exact` | 1 | 4.466ms | 7.037ms | 57.568% |
| REST | `Q2_PARCEL_EXACT/geocode_parcel` | 64 | 208.037ms | 483.575ms | 132.447% |
| REST | `Q1_ROAD_EXACT/geocode_road` | 64 | 251.753ms | 501.433ms | 99.177% |

오류 수는 SQL/REST 비교 row 모두 0건이었다. 즉 실패 원인은 correctness가 아니라 shadow search path/table 경로의 latency 회귀다.

## Rollback·cleanup

최종 run은 shadow schema를 drop했고, 작업 table cleanup도 통과했다.

| 항목 | 결과 |
|------|------|
| shadow schema drop | `dropped=true` |
| `_ktg_t125_*` 잔존 relation | 0 |
| `_ktg_t131_c11_policy_features` 잔존 relation | 0 |
| public flag off identity | 전후 동일 |

따라서 T-133은 리허설 자체와 rollback 증명은 완료됐지만, 성능 gate가 `blocked`라 C11 guarded policy를 active serving으로 승격할 수 없다.

## 후속

T-133은 shadow 리허설이므로 active serving object를 바꾸지 않는다. 결과가 통과하더라도 T-134에서 v1/v2 노출 계약(`pt_source`, `coord_source_detail`, `x_extension`)을 먼저 확정하고, T-137에서 C11 최종 gate와 ADR-051을 다시 판단한다. T-119는 사용자 승인 전까지 계속 금지한다.
