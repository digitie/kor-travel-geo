# T-213 phase ② 전국 라이브데이터 로딩

T-213은 전국 실 원천 archive를 T-109 계열 source registry 경로로 등록하고, active source match set을 기준으로 rebuild-db 적재와 serving MV swap까지 검증하는 작업이다. PR #165의 세종 단일 slice와 달리, 이번 실행은 `serving_recommended` profile의 전국 6개 category를 사용했다.

## 실행 환경

- 실행일: 2026-06-15 KST
- 실행 위치: WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`
- Git source of truth: NTFS `F:\dev\kor-travel-geo-codex`
- 대상 DB: `kor_travel_geo`
- RustFS endpoint: 기존 실행 중인 `tripmate-rustfs` S3 API
- 실행 산출물: `artifacts/t213-live-proper-20260614T225300Z/`
- recovery 요약: `artifacts/t213-live-proper-20260614T225300Z/t213-live-recovery-summary.json`

> 2026-06-15 이후 기준: 위 최초 실행은 당시의 실행 기록으로 남긴다. T-214/T-215에서 재사용할 T-213 기준 데이터는 기본 개발 DB가 아니라 `docs/t213-data-preservation.md`의 전용 PostgreSQL DB, 전용 RustFS prefix, NTFS `F:\dev\geodata\t213-baseline\<run-id>\` artifact 조합으로 보존한다. 기본 `kor_travel_geo`가 T-213 row count와 active release를 갖지 않으면 T-214 입력으로 쓰지 않는다. 입력 원천은 공용 루트 `F:\dev\geodata\juso`이며, 현재 쓰지 않는 파일은 `F:\dev\geodata\juso\unused\`에 둔다.

## 추가한 실행기

`scripts/run_t213_live_pipeline.py`를 추가했다. 기본은 plan-only이며, 실제 실행은 다음 조건을 요구한다.

- `--execute`
- `--dsn` 또는 `KTG_TEST_PG_DSN`/`KTG_PG_DSN` (기본 DSN fallback 없음)
- `--allow-destructive`
- `--typed-confirmation "RUN-T213-LIVE <database>"`
- `--force-promotion` 사용 시 `--force-promotion-reason`
- 실행 전 queued/running `load_jobs` 차단

runbook은 실행 직전 기존 active source match set을 기록한다. 기본 동작은 성공/실패와 관계없이 새 T-213 match set이 displace한 기존 active match set **포인터**를 복구하는 검증 실행이다. 실제 운영 serving 구성을 새 T-213 산출물로 유지하려면 `--promote-active-match-set`을 명시한다.

> **주의 — default 모드도 serving 데이터는 displace한다.** `--promote-active-match-set` 없이도 이 runbook은 `mv_refresh strategy='swap'`로 serving MV(`mv_geocode_target`/`mv_geocode_text_search`)를 새 T-213 데이터로 **물리적으로 교체**하고 새 active `serving_release`/snapshot FK를 생성한다. default 복구는 `ops.source_match_sets.active` **포인터만** 되돌리며 MV swap이나 serving_release는 원복하지 않는다(되돌리면 match-set 포인터와 serving 데이터가 불일치). 따라서 이 runbook은 **scratch DB에서만** 실행한다(필수 `--dsn`/`KTG_TEST_PG_DSN` + `--allow-destructive` + `RUN-T213-LIVE <db>` typed confirmation 가드가 사고성 prod 실행을 막는다).

기본 profile은 `serving_recommended`이며 다음 source category를 등록한다.

| category | 기준월 | 입력 |
| --- | --- | --- |
| `roadname_hangul_full` | `202605` | `202605_도로명주소 한글_전체분.zip` |
| `locsum_full` | `202604` | `202604_위치정보요약DB_전체분.zip` |
| `navi_full` | `202604` | `202604_내비게이션용DB_전체분.7z` |
| `electronic_map_full` | `202604` | 도로명주소 전자지도 시도별 ZIP 17개 |
| `roadaddr_entrance_full` | `202604` | 도로명주소 출입구 정보 시도별 ZIP 17개 |
| `zone_shape_full` | `202604` | 구역의도형 시도별 ZIP 17개. 파일명에는 기준년월이 없어 사용자 지시에 따라 등록/매칭 기준년월은 `202604`로 갈음한다. 물리 원천 경로는 현재 보유 파일 위치인 `구역의도형/202603`을 사용한다. |

전자지도 rebuild staging은 source registry materialization 특성상 `electronic_map_full/<시도명>/<SIG_CD>/...` 형태의 parent directory가 된다. 이를 수용하도록 `discover_sido_datasets()`와 SHP load plan을 보강했다.

## 실행 결과

source match set은 `6eb2b07b-f34f-460a-91ab-a5847a1e979e`로 활성화했다. source load 6개 job은 모두 성공했다.

| job | 결과 | 주요 row |
| --- | --- | ---: |
| `juso_text_load` | 성공 | 6,419,795 |
| `locsum_load` | 성공 | 6,405,091 |
| `navi_load` | 성공 | 10,687,317 centroid / 12,830 entrance |
| `shp_polygons_load` | 성공 | 153 layers |
| `roadaddr_entrance_load` | 성공 | 6,404,697 |
| `sppn_makarea_load` | 성공 | 24,204 |

최종 serving row count는 다음과 같다.

| table | row count |
| --- | ---: |
| `tl_juso_text` | 6,419,795 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_sppn_makarea` | 24,204 |
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |

T-027 최종 실 데이터 클린 재적재의 `mv_geocode_target=6,416,642`와 비교하면 T-213은 3,153행 많다(+0.05%). T-213은 source registry 경로로 `roadname_hangul_full=202605`, `locsum/navi/electronic_map/roadaddr_entrance=202604`, `zone_shape=202603` 조합을 사용했고(초기 run; 이후 사용자 지시로 zone_shape의 register/match 기준월은 202604로 갈음 — 위 표 및 r3 재실행 섹션 참조), T-027은 당시 클린 재적재 fixture와 기준월 조합을 사용했다. 차이는 loader 동작 차이로 단정하지 않고 원천 기준월·배포 파일 차이로 관리하며, T-214/T-215에서는 현재 active release row count를 기준값으로 삼는다.

active serving release는 다음으로 생성됐다.

| 항목 | 값 |
| --- | --- |
| `serving_release_id` | `96e60a10-695c-4a45-ad26-91422eb2f855` |
| `dataset_snapshot_id` | `856537e1-c8f2-44c9-8b8a-c51d0b99c494` |
| `source_match_set_id` | `6eb2b07b-f34f-460a-91ab-a5847a1e979e` |
| `activated_by_job_id` | `job_9d3adfe221214bf3aceb69563a86812e` |
| `consistency_report_id` | `consistency_7238f3fb50e347ccb8b3c6808402e656` |

간단 smoke로 `AsyncAddressClient.geocode("경기도 용인시 수지구 성복1로 35")`가 `OK` 후보를 반환했다.

## 정합성 결과

최신 consistency report는 `severity_max=ERROR`다. 이는 T-027 계열과 같은 source-quality gate 성격이며, production 경로에서는 수동 DB recovery가 아니라 `--force-promotion --force-promotion-reason "<사유>"`로 `forced_promotion` provenance를 남긴 뒤 serving release를 생성한다. 이 우회는 consistency ERROR promotion gate에만 적용되고, source archive integrity gate나 unavailable group은 우회하지 않는다.

주요 non-OK case:

- C1: 33,897건, `WARN`
- C2: 32,496건, `ERROR` (`missing_text=31,915`, `missing_resolve_key=581`)
- C3: 6,419,795건, `WARN`
- C5: 202건, `WARN`
- C10: 기준월 3종 혼합, `WARN`

## 실행 중 발견해 고친 문제

1. upload session terminal state에서 `registered`가 빠져 동일 `(category, user_yyyymm)` 재실행이 막혔다. `registered`를 terminal state에 포함했다.
2. source registry rebuild staging의 전자지도 parent directory를 SHP loader가 단일 시도 directory로만 해석했다. parent 아래 여러 시도 directory를 탐색하도록 보강했다.
3. batch consistency ERROR는 forced promotion gate에서 처리해야 하는데, handler가 먼저 실패를 던졌다. `load_batch_id`가 있는 batch consistency는 report를 기록하고 promotion gate로 넘기도록 바꿨다.
4. 전국 consistency case가 기본 5초 `statement_timeout`에 걸렸다. case별 트랜잭션에서 `SET LOCAL statement_timeout = 0`을 적용했다.
5. fresh rebuild DB에서는 consistency report 저장 시 아직 `mv_geocode_target`이 없을 수 있다. sample point 보강은 MV가 존재할 때만 실행하도록 바꿨다.

## 기준 데이터 보존

초기 batch root `batch_e00d8fa30a964b549090a602fd6a8fe3`는 위 4번과 5번 때문에 `state=failed` 이력을 남긴다. source load 6개는 모두 성공했고, 패치 후 post-load recovery로 consistency report와 `mv_refresh`를 완료해 active serving release는 정상 생성됐다. T-214는 active release와 `t213-live-recovery-summary.json`을 기준 입력으로 사용한다.

T-214 재현성을 위해 이후 T-213 기준 DB는 기본 개발 DB `kor_travel_geo`와 분리한다. 표준 보존 정책은 `docs/t213-data-preservation.md`를 따른다. 기준년월이 파일명/manifest에 없는 자료는 `202604`로 갈음한다. 핵심은 다음과 같다.

- PostgreSQL: `kor_travel_geo_t213` 또는 run별 `kor_travel_geo_t213_<YYYYMMDD>` 전용 DB.
- RustFS: 같은 bucket을 쓰더라도 `kor-travel-geo/t213/<run-id>` 전용 prefix.
- Artifact: WSL 테스트 미러의 `artifacts/`가 아니라 NTFS `F:\dev\geodata\t213-baseline\<run-id>\`에 기준 사본 보존.
- T-214 preflight: DB 이름, source registry full-prefix schema, active serving release id, `mv_geocode_target`/`mv_geocode_text_search` row count가 summary와 일치해야 benchmark 입력으로 인정한다.

## 2026-06-15 전용 baseline 재실행

T-214 착수 preflight에서 기본 개발 DB `kor_travel_geo`가 T-213 기준 상태가 아님을 확인해, 전용 DB와 RustFS prefix로 T-213을 재실행했다.

| 항목 | 값 |
| --- | --- |
| run id | `20260615-rerun3` |
| DB | `kor_travel_geo_t213_20260615_r3` |
| RustFS prefix | `kor-travel-geo/t213/20260615-rerun3` |
| artifact 사본 | `F:\dev\geodata\t213-baseline\20260615-rerun3\` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| load batch | `batch_ee0c66494eac490ba927e0a689dfd29a` |
| consistency report | `consistency_d3aa7ef74e374bb1babe2bb280c89475` |

최종 row count는 다음과 같다.

| table | row count |
| --- | ---: |
| `tl_juso_text` | 6,419,795 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_sppn_makarea` | 24,204 |
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |

`경기도 용인시 수지구 성복1로 35` smoke geocode는 `OK` 후보 1건을 반환했다. 기준년월이 파일명/manifest에 없는 `zone_shape_full`은 사용자 지시에 따라 `202604`로 등록했으며, 물리 파일은 `F:\dev\geodata\juso\구역의도형\202603\`을 사용했다.
