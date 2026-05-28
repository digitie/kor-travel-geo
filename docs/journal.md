# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-05-28 19:48 (T-052/T-053 선행 정리 — PR #67 리뷰 후속)

**작업**: PR #67 리뷰 후속과 사용자 확인사항을 T-052/T-053 본작업 전 선행 정리로 반영했다.

**반영**:
- 사용자 확인에 따라 T-056 RFC의 "조합/분리"는 주소 문자열 parse/compose가 아니라 코드 식별자의 조합·분해·정규화 의도였음을 문서화했다.
- 엄밀하지 않은 `clean-room` 표현을 "공개 주소 코드 규칙 기반 독립 구현, GPL 원본 코드 미복사"로 바로잡았다.
- Juso 검색 결과에 `admCd`/`rnMgtSn` 등 좌표 API 필수 코드가 없으면 coord API를 호출하지 않고 graceful `None`으로 끝나는 회귀 테스트를 추가했다.

**후속**:
- 이 선행 정리 PR을 머지한 뒤 T-052 v1/v2 API/provider 작업을 시작한다.

## 2026-05-28 19:20 (T-056 `python-kraddr-base` Address 코드 helper 정리)

**작업**: `~/dev/python-kraddr-base`의 실제 Address 표면을 확인하고, 본 저장소에서 필요한 주소 코드 helper를 clean-room으로 구현했다.

**확인**:
- `/home/digitie/dev/python-kraddr-base`는 Git checkout이 아니었다. `.git`이 없어 `git rev-parse HEAD`는 실패했다.
- package license는 `GPL-3.0-or-later`였고, 본 저장소는 MIT이므로 원본 코드를 복사하지 않았다.
- 실제 Address 표면은 예상했던 `kraddr.base.address.*` package가 아니라 `src/kraddr/base/addresses.py` 단일 파일이었다.

**반영**:
- `src/kraddr/geo/core/address/codes.py`에 `SigunguCode`, `LegalDongCode`, `RoadNameCode`, `RoadNameAddressCode`, `AddressCodeSet`과 mapping/정규화 helper를 추가했다.
- Juso fallback 좌표 API 호출은 `AddressCodeSet`으로 `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`를 정규화한 뒤 요청한다.
- `docs/t056-kraddr-base-address-merge.md`, ADR-035, 백엔드/아키텍처 문서, resume/tasks/CHANGELOG를 갱신했다.

**후속**:
- 사용자 최신 지시에 따라 T-056 이후에는 T-052/T-053 선행 정리 → T-052 → T-053 순서로 진행한다.

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 0.1.0 기준으로 upstream code/API를 재확인하고, upstream 코드는 직접 수정하지 않은 채 이 저장소 문서에만 T-044 보완점을 반영했다.

**확인**:
- GitHub tag `v0.1.0`은 commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb`이고, commit message는 `chore: release v0.1.0`이다.
- GitHub release는 없었고, npm registry에서도 `maplibre-vworld@0.1.0`과 `maplibre-vworld-js@0.1.0`은 `E404`였다.
- package name/version은 `maplibre-vworld`/`0.1.0`이며, `dist/`, `exports`, `types`, `style.css`, `VWorldMap`, marker/layer primitive, VWorld helper가 포함되어 있었다.
- 현재 `kraddr-geo-ui` dependency는 여전히 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`에 고정되어 있고, 이번 작업에서는 dependency를 갱신하지 않았다.

**결론**:
- T-044는 0.1.0 기준 문서-only 재확인으로 완료한다.
- 실제 `CoordinateMap` 전환은 별도 구현 PR에서 `VWorldMap`/`Marker`/`PolygonArea` 소비를 검토한다.
- upstream 범용 기능 보강이 필요하면 이번 T-044 안에서 수정하지 않고 별도 upstream task/PR로 분리한다.

**문서**:
- `docs/t044-maplibre-vworld-010-review.md`
- `docs/tasks.md`
- `docs/frontend-package.md`
- `docs/external-apis.md`
- `docs/decisions.md`
- `docs/resume.md`

**검증**:
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
- 전체 pytest 결과는 216 passed, 6 skipped, 3 warnings다.

## 2026-05-28 17:42 (T-062 PR #53~#64 리뷰 audit/fixup)

**작업**: T-057 merge 직후 사용자 지시에 따라 PR #53부터 #64까지 아직 별도 audit하지 않은 PR 리뷰를 모두 재확인했다.

**확인**:
- 각 PR의 conversation comment, formal review, inline review thread, GraphQL `reviewThreads`를 확인했다.
- 모든 PR의 unresolved review thread는 0건이었다.

**직접 반영**:
- PR #53: search exact preflight의 Python/SQL 정규화 규칙을 문서화하고, shadow MV index 문서 오타를 수정했다. exact preflight가 없는 broad trigram fallback을 계속 측정하도록 `search_fuzzy` benchmark case와 REST 변환 case를 추가했다.
- PR #55: `pg_stat_statements` 조회/reset을 `x_extension` schema-qualified SQL로 고정했다.
- PR #59: reverse 좌표 bounds validation을 `PydanticCustomError("kraddr_geo.coordinate_bounds", ...)` 기반 structured mapping으로 바꿔 문자열 전체 매칭 의존을 제거했다.
- PR #62: REST admission repeat 문서에 c64 tail 중심 비교 이유를 추가했다.
- PR #63: `tar.zst` SHA256 checksum 시간을 측정하고, backup envelope와 `tar.zst`의 의미를 단일 artifact 포장/checksum 단순화 중심으로 보강했다.

**후속**:
- 다음 작업은 사용자 추가 지시에 따라 T-044를 `maplibre-vworld-js` 0.1.0 기준으로 다시 확인하는 문서-only PR이다. upstream 코드는 직접 수정하지 않고 `python-kraddr-geo` 문서에 보완점을 남긴다.

**검증**:
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
- 전체 pytest 결과는 216 passed, 6 skipped, 3 warnings다.

## 2026-05-28 16:20 (T-057 행정구역 hint 기반 검색 가속)

**작업**: `sig_cd`/`bjd_cd` 명시 hint를 라이브러리와 REST API, raw SQL repository, T-047 SQL/REST benchmark harness에 연결했다.

**반영 상세**:
- `RegionHint` DTO를 추가했다. `sig_cd`는 2자리 시도 prefix 또는 5자리 시군구 코드, `bjd_cd`는 8자리 법정동 prefix 또는 10자리 법정동 코드를 받는다.
- `/v1/address/geocode`, `/v1/address/search`, `/v1/address/reverse`는 선택 `sig_cd`/`bjd_cd` query parameter를 받는다.
- 응답 구조는 vworld 호환 그대로 유지한다. hint가 있는 geocode 요청에서 로컬 `NOT_FOUND`가 나오면 외부 fallback은 호출하지 않는다.
- 현재 `mv_geocode_target`에는 물리 `sig_cd`가 없으므로 `sig_cd`는 `bjd_cd` prefix filter로 적용한다.
- OpenAPI와 프론트엔드 생성 타입을 갱신했다.

**측정**:
- SQL standard artifact: `artifacts/perf/t057-region-hint-standard-20260528`.
- SQL corpus SHA: `e38bff5631a3b68fe6094e9124641a22f24770b9a040e8a70d067f1ea651d61f`.
- SQL run: 900 case, 8,100 measurement, error 0.
- SQL Q3 fuzzy c64 p95: 307.45ms → 267.99ms.
- REST smoke artifact: `artifacts/perf/t057-region-hint-rest-smoke-20260528`.
- REST run: 320 case, 1,920 measurement, error 0.
- REST Q3 fuzzy c64 p95: 651.62ms → 520.43ms.

**결론**:
- 명시 region hint는 유지할 가치가 있다.
- Q3 fuzzy는 hint로 개선되지만 충분한 종결 조건은 아니다. wide no-hint 경로가 일부 더 낮게 나와 trgm 후보 폭 자체를 줄이는 구조가 필요하다.
- 후속은 T-061 `mv_geocode_text_search` 또는 동등한 slim text-search 후보 테이블로 분리한다.
- T-057 PR merge 뒤에는 사용자 지시에 따라 최근 PR 중 리뷰를 아직 확인하지 않은 항목을 모두 audit/fixup한 뒤 다음 task로 넘어간다.

## 2026-05-28 14:56 (T-047 backup archive 압축 측정)

**작업**: T-047 인덱스 운영 영향 측정에서 남겨 둔 `tar.zst` archive 단계를 실제 `zstd` CLI로 측정했다.

**측정**:
- `apt download zstd` 후 `/tmp/codex-zstd/usr/bin/zstd`를 사용했다.
- zstd: `v1.5.5`.
- 입력: `artifacts/perf/t047-operational-impact-20260528/pgdump-dir`.
- 출력: `artifacts/perf/t047-operational-impact-20260528/pgdump-dir.tar.zst`.
- 명령: `tar --use-compress-program=/tmp/codex-zstd/usr/bin/zstd\ -T0\ -3`.
- archive wall time: 33.31초.
- max RSS: 112,768KiB.
- dump directory bytes: 4,313,361,824.
- archive bytes: 4,308,457,630.
- SHA256: `94f404bdf9a4a3956009f961f966e7bca3b90f42eecfc083e83add7b1ea87883`.

**결론**:
- `pg_dump -Fd` directory 내부의 대형 table data는 이미 `.dat.gz`라 `zstd` 포장 단계에서 크기 감소는 거의 없었다.
- archive 단계 자체는 33.31초로 짧았다. 전국 DB 백업 envelope는 `pg_dump -Fd` 2분 21.60초 + archive 33.31초 + checksum 단계로 보면 된다.
- T-047 자체 잔여였던 backup archive 측정은 완료했다. Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 후속으로 넘긴다.

## 2026-05-28 14:35 (T-047 REST admission candidate 반복 측정)

**작업**: REST worker/pool/admission exploratory grid에서 후보로 남긴 `w2/p8/a8`, `w4/p4/a4`를 기본 profile과 함께 `iterations=3`으로 반복 측정했다.

**측정**:
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- 각 run은 REST case 1,000건, measurement 16,000건, `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, error 0이었다.
- artifacts:
  - `artifacts/perf/t047-rest-repeat-default-20260528`
  - `artifacts/perf/t047-rest-repeat-w2-p8-a8-20260528`
  - `artifacts/perf/t047-rest-repeat-w4-p4-a4-20260528`

**결론**:
- `w2/p8/a8`은 Q1 road/Q4 search의 c64 p95와 Q1~Q4 p99가 더 안정적이었다. Q4 search p95는 default 873.12ms에서 596.35ms로 줄었다.
- `w4/p4/a4`는 Q7 zipcode, Q8 no-result, Q11 SPPN에서 가장 안정적이었다. Q8 no-result p95는 default 703.92ms에서 542.88ms로 줄었다.
- Q3 fuzzy는 p95 기준 default가 654.86ms로 가장 낮았고, p99 기준으로만 `w2/p8/a8`이 가장 낮았다. worker/pool/admission 조합만으로 Q3를 해결했다고 보지 않는다.

**후속**:
- T-047 안에서 pool 기본값을 더 바꾸지 않고, Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 실험으로 넘긴다.
- 남은 T-047 자체 작업은 `zstd` 준비 후 backup `tar.zst` archive 측정 정도다.

## 2026-05-28 14:06 (T-047 REST worker/pool/admission grid)

**작업**: REST API c64 tail을 줄이기 위해 `/v1/address/*` 전용 optional admission control을 추가하고, worker/pool/admission 조합을 exploratory benchmark로 비교했다.

**반영 상세**:
- `KRADDR_GEO_API_MAX_CONCURRENCY`가 설정된 경우에만 주소 API 요청을 process-local semaphore로 제한한다. 기본값은 unset이라 기존 동작은 유지된다.
- `KRADDR_GEO_API_ADMISSION_TIMEOUT_MS`는 semaphore 대기 timeout이다. timeout 시 HTTP 429 + `E0200`을 반환한다.
- health/admin/metrics 경로는 admission control 대상에서 제외했다.

**측정**:
- 기준 corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- 각 run은 REST case 1,000건, measurement 8,000건, `iterations=1`, `warmup=1`, concurrency `1/4/16/64`, error 0이었다.
- artifacts:
  - `artifacts/perf/t047-rest-grid-w1-p16-a16-20260528`
  - `artifacts/perf/t047-rest-grid-w2-p8-a8-20260528`
  - `artifacts/perf/t047-rest-grid-w4-p4-a4-20260528`

**결론**:
- `w4/p4/a4`는 Q4 search c64 p95를 753.25ms에서 435.63ms로, Q3 fuzzy를 810.53ms에서 550.35ms로 낮췄다. Q1/Q2/Q7도 개선됐다.
- `w2/p8/a8`은 Q6 reverse radius, Q8 no-result, Q11 SPPN reverse에서 더 안정적이었다.
- Q5 reverse nearest와 일부 p99는 아직 악화 구간이 있어 운영 권장값으로 확정하지 않는다.

**후속**:
- `w4/p4/a4`와 `w2/p8/a8`을 `iterations=3` 이상으로 재측정한다.
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 이어간다.

## 2026-05-28 13:19 (T-047 REST API pool64 비교)

**작업**: REST API e2e latency에서 DB pool만 64로 키웠을 때 c64 tail이 개선되는지 확인했다.

**측정**:
- artifact: `artifacts/perf/t047-rest-e2e-pool64-20260528`.
- 비교 기준: `artifacts/perf/t047-rest-e2e-standard-20260528-r2`.
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- uvicorn 단일 process, `KRADDR_GEO_PG_POOL_SIZE=64`, `KRADDR_GEO_PG_MAX_OVERFLOW=0`.
- REST case 1,000건, measurement 8,000건, error 0.

**결론**:
- Q3 fuzzy c64 p95는 810.53ms에서 557.25ms로 개선됐고, Q6 reverse radius p95는 773.89ms에서 757.39ms로 소폭 개선됐다.
- Q1/Q2/Q4/Q5/Q7/Q8은 대부분 악화됐다. 예를 들어 Q4 search c64 p95는 753.25ms에서 864.84ms로, Q1 도로명 geocode c64 p95는 581.42ms에서 850.38ms로 커졌다.
- REST 단일 process에서는 pool64가 checkout 대기만 줄이는 해법이 아니라 DB 동시 실행과 Python/HTTP scheduling 경합을 키울 수 있다. 운영 기본 pool을 64로 단순 상향하지 않고, 다음 실험은 worker 수, pool size, admission control 조합 grid로 진행한다.

**후속**:
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 SQL/REST 전후를 비교한다.
- API worker/pool/admission control grid를 같은 REST corpus로 측정한다.

## 2026-05-28 12:57 (T-047 REST API e2e latency)

**작업**: SQL benchmark corpus를 실제 `/v1/address/*` HTTP 요청으로 변환하는 REST API benchmark harness를 추가하고, 표준 corpus e2e latency를 측정했다.

**반영 상세**:
- `scripts/benchmark_api_latency.py`를 추가했다. 저장 corpus를 geocode/reverse/search/zipcode 요청으로 변환하고 `benchmark.json`, `summary.md`, `api-cases.json`, `environment.json`을 남긴다.
- SQL-only invalid reverse case `(0, 0)`은 public REST DTO에서 한국 밖 좌표로 거절되는 것이 맞으므로 REST latency corpus에서 제외했다.
- 내부 `pydantic.ValidationError`가 FastAPI exception handler를 지나 HTTP 500이 되던 문제를 보정했다. 한국 밖 reverse 좌표는 이제 HTTP 400 + `E0102`로 응답한다.

**측정**:
- artifact: `artifacts/perf/t047-rest-e2e-standard-20260528-r2`.
- corpus SHA: `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`.
- REST case 1,000건, measurement 8,000건, error 0.
- c1 p95는 6.95~16.18ms, c16 p95는 43.79~97.13ms였다.
- c64 p95는 Q3 fuzzy 810.53ms, Q6 reverse radius 773.89ms, Q4 search 753.25ms, Q7 zipcode point 734.30ms 순이었다.

**후속**:
- API worker 수, DB pool size, admission control 조합을 e2e로 비교한다.
- Q3 fuzzy는 REST tail도 가장 크므로 T-057 region hint 또는 `mv_geocode_text_search` 후보 실험을 유지한다.

## 2026-05-28 12:26 (T-047 stress corpus benchmark)

**작업**: PR #51/#52 후속 액션 중 `stress` 10,000건 이상 corpus 조건을 실제 T-027 Docker DB에서 측정했다.

**측정**:
- corpus: `artifacts/perf/t047-stress-20260528/corpus.json`, SHA `2123e09e41f96760b4a8451d98518a87aee6289cc8b238b8a8b2896b51665f23`, 11,000건.
- run: 기본 pool `size=10`, `max_overflow=5`, `iterations=1`, `warmup=1`, concurrency `1/4/16/64`.
- measurement 88,000건, error 0, `pg_stat_statements=true`.
- c16까지는 모든 query군 p95가 34ms 이하로 들어왔다.
- c64 tail은 대부분 checkout 대기였다. Q3 fuzzy p95 335.01ms 중 checkout p95 304.91ms, execute p95 32.07ms였고, Q4 search p95 302.21ms 중 checkout p95 280.41ms, execute p95 27.77ms였다.
- `pg_stat_statements` delta top은 Q3 fuzzy 계열 40,910.80ms/8,000 calls, Q1 road exact 21,453.97ms/8,000 calls, Q4 search 18,161.25ms/8,000 calls 순이었다.

**후속**:
- 다음 T-047 측정은 REST API e2e latency에서 HTTP overhead와 DB checkout/execute split을 대조한다.
- Q3 fuzzy 총 execution time이 가장 크므로 T-057 region hint 또는 `mv_geocode_text_search` 후보 실험은 유지한다.

## 2026-05-28 12:06 (T-047 인덱스 운영 영향 측정)

**작업**: T-047 exact btree index 3개(`idx_mv_jibun_name_exact`, `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`)가 MV refresh/swap, 디스크, 백업 단계에 주는 운영 영향을 실측했다.

**측정**:
- DB: Docker PostGIS `localhost:15432`, `mv_geocode_target=6,416,637`.
- 첫 shadow `swap`은 기본 statement timeout 5초에 걸려 실패했다. `mv_geocode_target_next`/`mv_geocode_target_old` 잔여 객체는 없었고 live MV row count는 유지됐다.
- `KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000`으로 재실행한 결과, `CONCURRENTLY` refresh는 133.28초, shadow `swap`은 352.85초였다.
- T-035 기준선 대비 `CONCURRENTLY`는 +21.64초, shadow `swap`은 +215.70초다.
- shadow `swap` 중 exact index 3개 build phase 합계는 180.35초였다. live rename/drop/index rename 구간은 0.03초 수준으로 lock window는 여전히 짧았다.
- DB 전체는 31.90GiB, `mv_geocode_target` total은 4.78GiB, MV index total은 2.93GiB, exact index 3개 합계는 1.43GiB였다.
- `pg_dump -Fd --jobs=4` dump directory 생성은 2분 21.60초, 4.02GiB, max RSS 32,200KiB였다.

**산출물**:
- `artifacts/perf/t047-operational-impact-20260528/mv-concurrent.json`
- `artifacts/perf/t047-operational-impact-20260528/mv-swap.json`
- `artifacts/perf/t047-operational-impact-20260528/pgdump.time`

**후속**:
- 현재 WSL 환경에는 `zstd` CLI가 없어 최종 `tar.zst` archive 측정은 수행하지 못했다. 다음 backup archive 측정 전 `zstd` 설치 또는 backup helper fallback 압축 경로를 검증한다.
- T-047 다음 순서는 `stress` 10,000건 이상 corpus, REST API e2e latency, Q3 fuzzy 후보 축소다.

## 2026-05-28 11:20 (T-047 active observability run)

**작업**: T-047 관측성 보강이 머지된 뒤, 실제 Docker DB에 `pg_stat_statements`를 활성화하고 저장 corpus로 반복 benchmark를 수행했다.

**DB 조치**:
- `kraddr-geo-t027-db-1` 컨테이너를 `shared_preload_libraries=pg_stat_statements` 설정으로 재생성했다. bind mount `/home/digitie/kraddr-geo-data/pgdata`는 유지했다.
- 기존 DB는 Alembic version table이 없어 `alembic upgrade head`가 0001부터 시작했고, 33자 revision ID `0005_t039_roadaddr_entrance_table`가 기본 `varchar(32)`에 걸리는 문제가 드러났다.
- revision ID를 `0005_t039_roadaddr_entrc`로 줄이고, 모든 revision/down_revision 길이 32자 이하 테스트를 추가했다.
- 이 실측 DB는 이미 스키마 객체가 존재하는 수동 full-load DB라 `pg_stat_statements` extension을 직접 만든 뒤 `alembic stamp head`로 현재 상태를 기록했다.

**측정**:
- corpus: `artifacts/perf/t047-search-exact-split-20260528/corpus.json`, SHA `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f`, 1,100건.
- 기본 pool run: `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, measurement 17,600건, error 0, `pg_stat_statements=true`.
- pool64 run: 같은 corpus, `pool_size=64`, `max_overflow=0`, concurrency 64, measurement 4,400건, error 0.
- 기본 pool c64는 Q4 search p95 330.80ms 중 checkout p95 307.88ms, execute p95 28.09ms로 대부분 connection checkout 대기였다.
- pool64 c64는 Q4 search p95 162.50ms, checkout p95 28.12ms, execute p95 128.11ms로 pool 대기는 줄었지만 DB 실행 시간이 커졌다. Q3 fuzzy는 pool64 c64 p95 167.87ms, execute p95 128.72ms로 다음 후보 축소 대상이다.

**산출물**:
- `artifacts/perf/t047-active-observability-20260528`
- `artifacts/perf/t047-active-observability-pool64-20260528`

**후속**:
- T-047 인덱스 3개의 운영 영향(MV refresh/swap, backup archive, 디스크 envelope)을 측정한다.
- Q3 fuzzy 후보 축소는 T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 비교한다.

## 2026-05-28 10:35 (T-047 관측성 benchmark 보강)

**작업**: PR #51/#52 후속 액션 중 `pg_stat_statements`와 pool wait/DB execution 분리를 benchmark harness에 반영했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`의 artifact schema를 2로 올리고, measurement에 `checkout_ms`와 `execute_ms`를 추가했다.
- summary에는 `p95_checkout_ms`와 `p95_execute_ms`를 추가해 동시성 tail에서 connection pool 대기와 SQL 실행 시간을 분리해 볼 수 있게 했다.
- `pg-stat-statements-before.json`, `pg-stat-statements-after.json`, `pg-stat-statements-delta.json` artifact를 추가하고, `--reset-pg-stat-statements`, `--pg-stat-limit` 옵션을 넣었다.
- `docker-compose.yml`, fresh schema SQL, Alembic `0011_t047_pg_stat_statements`에 `pg_stat_statements` preload/extension 경로를 추가했다.

**검증**:
- T-027 클린 DB(`localhost:15432`, `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204`)에서 `cases_per_group=1`, `iterations=1`, `warmup=0`, `concurrency=1` smoke benchmark를 실행했다.
- smoke 11개 query군은 모두 error 0이었다. 현재 기존 DB는 `pg_stat_statements` extension 미설치 상태라 snapshot artifact는 `available=false`, `error=pg_stat_statements extension is not installed`를 기록했다.

**후속**:
- Docker DB를 restart/upgrade한 뒤 `--reset-pg-stat-statements`와 저장 corpus로 `standard --iterations 3`를 다시 실행한다.
- T-047 인덱스 3개(`idx_mv_jibun_name_exact`, `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`)의 MV refresh/swap, backup archive, 디스크 envelope 영향을 별도 PR에서 측정한다.

## 2026-05-28 09:45 (PR #51/#52 post-merge 리뷰 반영)

**작업**: 사용자 지시에 따라 PR #51과 PR #52의 post-merge 리뷰 코멘트를 다시 확인하고, 후속 액션을 진행 가능한 문서 상태로 정리했다.

**확인 결과**:
- PR #51: conversation comment 1건, review 0건, review thread 0건.
- PR #52: conversation comment 1건, review 0건, review thread 0건.
- 두 PR 모두 unresolved inline thread는 없었다.

**반영 상세**:
- `docs/postmerge-review-fixups-pr51-pr52.md`를 추가해 리뷰 항목별 처리 상태를 정리했다.
- `docs/t047-query-performance-tuning.md`에 corpus 생성 알고리즘, 후보 확정 run profile, PR #51/#52 후속 액션 표를 보강했다.
- `docs/tasks.md`에서 T-060을 완료로 옮기고, 남은 T-047 후속을 `pg_stat_statements`, `standard --iterations 3`, stress corpus, pool wait/DB execution 분리, T-047 index 운영 영향, Q3 fuzzy/T-057 region hint로 명확히 정리했다.
- `docs/resume.md`와 `CHANGELOG.md`를 동기화했다.

**후속**:
- 다음 T-047 측정 PR은 관측성/운영 영향 묶음으로 시작하는 것이 자연스럽다. 단, 운영 안전성 우선순위를 더 엄격히 적용하면 T-056부터 진행한다.

## 2026-05-28 08:55 (T-047 Q4 search exact preflight 튜닝)

**작업**: Q4 통합 search의 broad trigram 병목을 줄이기 위해 exact preflight 경로와 전용 btree index를 추가했다.

**반영 상세**:
- `src/kraddr/geo/infra/search_repo.py`: search repository가 공백 제거 query로 `rn_nrm`/`buld_nm_nrm` exact preflight를 먼저 실행하고, exact 결과가 있으면 그 결과 집합만 반환한다. exact 결과가 없을 때만 기존 broad trigram search로 fallback한다.
- `src/kraddr/geo/infra/sql.py`, `alembic/versions/0010_t047_search_exact_indexes.py`: `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`를 추가했다.
- `scripts/benchmark_query_performance.py`: Q4 search benchmark가 raw `_SEARCH_SQL`만 직접 실행하지 않고 운영 repository와 같은 exact preflight를 재현하도록 수정했다.
- `tests/unit/test_infra_repo_sql.py`, `tests/unit/test_query_performance_benchmark.py`: SQL/index 계약과 benchmark search preflight 파라미터를 고정했다.

**측정**:
- 실제 T-027 클린 DB에서 index build time/size: `idx_mv_rn_nrm_exact` 120.45초/389MiB, `idx_mv_buld_nm_nrm_exact` 51.90초/316MiB.
- standard corpus Q4 100건은 모두 exact preflight로 처리됐다(`min_exact_total=13`, `max_exact_total=1,562`).
- `Q4-search-038`(`퇴계로88나길`) plan execution은 broad trigram 42.39ms → exact preflight 0.56ms로 감소했다.
- Q4 p95: default pool c1/c4/c16은 62.12/70.62/116.06ms → 12.23/22.39/52.27ms, pool64 c64는 481.22ms → 295.85ms. default pool c64는 pool 대기와 다른 query군 경합이 섞여 421.36ms → 622.38ms로 악화되어 SQL 효과 판단값으로 쓰지 않는다.

**후속**:
- 사용자 지시에 따라 현재 PR 머지 후 PR #51/#52 리뷰 코멘트를 다시 확인하고, actionable 항목 또는 후속 액션을 문서화한다.
- T-047 남은 항목은 `pg_stat_statements`, REST API e2e latency, stress 10,000건 corpus, Q3 fuzzy 후보 축소, T-057 region hint 비교다.

## 2026-05-28 00:45 (T-047 standard corpus와 pool 비교)

**작업**: PR #51 머지 후 최신 `origin/main`에서 T-047 benchmark harness를 사용해 1,100건 standard corpus와 동시성 64 pool 비교를 수행했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`에 `--pool-size`, `--max-overflow` 옵션을 추가했다. `environment.json`과 `summary.md`에는 실제 pool 설정을 기록한다.
- 같은 corpus로 기본 pool(`pool_size=10`, `max_overflow=5`)과 pool 64(`pool_size=64`, `max_overflow=0`) 동시성 64를 비교했다.
- `docs/t047-query-performance-tuning.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`에 결과와 후속 후보를 기록했다.

**측정**:
- `t047-standard-20260528`: 1,100 cases, concurrency 1/4/16/64, warmup 1, measured iteration 1, error 0.
- 기본 pool에서 동시성 16까지는 모든 query군 p95가 ADR-031 1차 목표 안에 들어왔다. 동시성 64에서는 Q1/Q2/Q3/Q4/Q5/Q7/Q8 tail이 크게 증가했다.
- `t047-standard-pool64-20260528`: 같은 corpus, concurrency 64, pool 64, error 0. Q2 지번 exact p95는 339.66ms → 156.76ms, Q8 no-result road p95는 222.18ms → 122.75ms로 개선됐다. 반면 Q3 fuzzy p95는 353.92ms → 417.46ms, Q4 search p95는 421.36ms → 481.22ms로 악화됐다.

**검증**:
- `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py` 통과.
- `mypy scripts/benchmark_query_performance.py` 통과.
- `pytest tests/unit/test_query_performance_benchmark.py -q` 6건 통과.

**후속**:
- Q3/Q4는 pool 확대가 답이 아니므로 query split, `UNION ALL`, text-search slim MV 후보를 별도 trial로 검증한다.
- `pg_stat_statements` 활성화 또는 DB execution aggregate 대체 방식을 마련해 pool wait와 DB 실행 시간을 더 명확히 나눈다.
- REST API e2e latency와 T-057 region hint 비교를 이어간다.

## 2026-05-27 23:45 (T-047 1차 query benchmark harness + 지번 exact 튜닝)

**작업**: T-047 중단 지점을 최신 `main`(#50) 위로 복구하고, query benchmark harness와 첫 번째 실제 튜닝을 완료했다.

**반영 상세**:
- `scripts/benchmark_query_performance.py`를 추가했다. `mv_geocode_target`/`tl_sppn_makarea`에서 deterministic corpus를 만들고, geocode/reverse/search/zipcode raw SQL을 실행해 `corpus.json`, `benchmark.json`, `environment.json`, `summary.md`, slow sample `EXPLAIN` JSON을 `artifacts/perf/<run-id>/`에 저장한다.
- `tests/unit/test_query_performance_benchmark.py`를 추가해 percentile, warmup 제외 summary, parser 기본값, corpus JSON round-trip을 검증했다.
- T-027 최종 클린 DB(`mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204`)에서 smoke benchmark를 실행했다.
- Q2 지번 exact가 기존 `idx_mv_jibun(bjd_cd, ...)` 경로에서 느린 것을 확인하고, `idx_mv_jibun_name_exact(si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno, emd_nm, li_nm, pt_source, bd_mgt_sn)`를 추가했다. 기존 DB용 Alembic `0009_t047_jibun_name_exact_index`와 fresh MV SQL을 함께 갱신했다.
- CodeGraph MCP 설정(`.codex/config.toml`)과 관련 문서 보강을 최신 `main` 위에 보존했다.

**측정**:
- index build: 56.03초, 761MiB.
- 같은 corpus smoke 전후: Q2 지번 exact client latency 2830.59ms → 5.58ms, plan execution 333.417ms → 0.100ms.
- post-index small concurrency run: `cases_per_group=5`, `iterations=3`, `warmup=1`, 동시성 1/4/16. 단일 동시성의 모든 query군 p95가 ADR-031 1차 목표 안에 들어왔고, 동시성 16에서는 Q1/Q3/Q4 tail이 90~110ms 구간으로 증가했다.

**검증**:
- `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py` 통과.
- `pytest tests/unit/test_query_performance_benchmark.py -q` 6건 통과.
- 실제 DB smoke benchmark와 post-index concurrency benchmark 실행 완료. artifact는 ignore 대상인 `artifacts/perf/`에 보관했다.

**후속**:
- `standard`/`stress` corpus, 동시성 64, REST API end-to-end latency, `pg_stat_statements`, T-057 region hint 비교를 다음 T-047 후속 PR에서 진행한다.

## 2026-05-27 (사용자 RFC 반영 — T-052~T-059 백로그 + ADR-035~ADR-038)

**작업**: 사용자 RFC(restore hot-swap, vworld/kakao/naver multi-provider + v1/v2 API + AI-friendly 문서, Web UI 통계/유지보수/관리/튜닝 + C1~C10 분석 UI/CSV, CLI 동시 실행 보호, 한국 IP만 허용, N150/Odroid 환경 검토, `python-kraddr-base` Address 부분 병합 + 외부 라이브러리 삭제, 행정구역 hint 검색 가속)를 task 8건과 ADR 4건으로 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- `docs/tasks.md`에 T-052~T-059 신규 항목 추가 + 우선순위 재정렬. 운영 안전성(T-056, T-058, T-059, T-054)을 먼저, 기능 보강(T-057, T-053, T-052) 다음, 운영 환경 비교(T-055)는 하드웨어 도착 후.
- `docs/decisions.md`에 ADR-035(`python-kraddr-base` Address 흡수 + 외부 라이브러리 삭제), ADR-036(restore hot-swap `ALTER DATABASE RENAME` 기반), ADR-037(외부 IP 한국만 허용), ADR-038(API v1/v2 분리 + 외부 provider 흡수 + AI-friendly 문서)을 추가했다.
- 각 task별 design doc 8건 신규: `docs/t052-api-providers-v1-v2.md`, `docs/t053-admin-ui-ops-statistics.md`, `docs/t054-korea-only-geoip.md`, `docs/t055-deployment-n150-odroid.md`, `docs/t056-kraddr-base-address-merge.md`, `docs/t057-region-hint-search.md`, `docs/t058-restore-hot-swap.md`, `docs/t059-concurrent-job-protection.md`.
- 각 design doc은 "상태/목적/현황/결정/구현 sketch/검증/남은 위험/관련 ADR-Task" 구조로 작성해 사람과 AI agent 모두가 cold start로 진입할 수 있게 했다.
- `CHANGELOG.md`/`docs/resume.md`에 같은 내용을 동기화했다.

**현황 확인 결과 (사용자가 "반영되어 있으면 스킵" 조건을 건 항목)**:
- restore hot-swap: 현 시점 `docs/t046-db-backup-restore.md`/ADR-030은 "기본 새 빈 DB + `replace_current` 위험 경로"만 명문화. hot-swap 절차 자체는 미반영 → **스킵하지 않고 T-058로 등록**.
- CLI 중복 실행 보호: in-process semaphore + `load_jobs` advisory lock + `TL_SPBD_BULD` staging lock + `ops.serving_releases` active partial unique는 이미 있음. cross-process 표준화는 일부만 적용 → **T-059로 인벤토리 + 표준화 등록**.

**다음 작업**: 우선순위에 따라 T-056부터 또는 T-027 베이스라인 활용 가능한 T-057/T-059부터 구현 PR을 만든다. 본 PR은 문서/계획만 포함하므로 코드/DDL은 후속 PR에서 처리한다.

**검증**:
- `git diff --check` 통과 예정(문서 전용).
- `pytest -q`, `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`는 본 PR이 코드 변경이 없으므로 회귀 차원에서 baseline만 통과 확인.

## 2026-05-27 (T-047 중단 기록 — CodeGraph MCP 설정과 벤치마크 harness 초안)

**작업**: 사용자 지시에 따라 T-047 진행 중 Codex Desktop 재시작을 위해 작업을 중단하고 현재 상태를 기록했다. 이 시점에는 PR/commit/push를 하지 않았다.

**현재 branch/worktree**:
- worktree: `~/dev/geo-codex`
- branch: `agent/codex-t047-query-performance`
- 기준: `origin/main`

**반영된 미커밋 변경**:
- `.codex/config.toml`: CodeGraph MCP stdio 서버 설정 추가. `codegraph install --print-config codex`가 제안한 `command = "codegraph"`, `args = ["serve", "--mcp"]` 방식을 사용했다. WSL에서 `npx -y @colbymchenry/codegraph mcp`는 Windows npm shim/UNC 경로 경고가 발생할 수 있어 기본값으로 쓰지 않았다.
- `README.md`, `AGENTS.md`, `SKILL.md`, `docs/dev-environment.md`, `docs/agent-guide.md`, `docs/decisions.md`: CodeGraph `init -i`/`status`, MCP 재시작 필요성, 컴포넌트 수정 전 `codegraph_explore` 영향도 확인 규칙을 보강했다.
- `scripts/benchmark_query_performance.py`: T-047 query benchmark harness 초안 추가. `mv_geocode_target`, `tl_sppn_makarea`, zipcode/search/reverse/geocode SQL을 대상으로 corpus 생성, 반복 측정, summary/JSON/plan artifact 저장 구조를 작성했다.
- `tests/unit/test_query_performance_benchmark.py`: percentile, summary aggregation, corpus JSON round-trip 단위 테스트 추가.

**검증된 것**:
- `codegraph sync && codegraph status` 실행 결과 `Index is up to date`를 확인했다. sync 당시에는 새 Python 파일 2개가 인덱스에 반영됐다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=... /home/digitie/dev/python-kraddr-geo/.venv/bin/python -m pytest tests/unit/test_query_performance_benchmark.py -q` 실행 결과 6건 통과.
- `ps` 확인 시 benchmark/pytest/ruff/gh/docker compose 장기 실행 프로세스는 없었다.

**아직 끝나지 않은 것**:
- `scripts/benchmark_query_performance.py`와 테스트는 ruff를 한 차례 보정했지만, 마지막 상태에서 전체 `ruff`, `mypy`, 실제 Docker DB smoke benchmark를 아직 다시 실행하지 않았다.
- 실제 DB 스모크 benchmark, `EXPLAIN` plan artifact 생성, `docs/t047-query-performance-tuning.md` 구현 결과 보강, `docs/resume.md` 최종 완료 토글, `CHANGELOG.md` 갱신, commit/push/PR 생성은 남아 있다.
- Codex Desktop 재시작 전이므로 현재 세션에는 CodeGraph MCP 도구가 아직 노출되지 않는다. 재시작 후 `codegraph_explore` 도구가 보이면 UI 컴포넌트 작업 때 먼저 사용한다.

**재개 순서**:
1. Codex Desktop 재시작 후 `~/dev/geo-codex`에서 `git status --short --branch` 확인.
2. `codegraph sync && codegraph status` 실행.
3. `ruff check scripts/benchmark_query_performance.py tests/unit/test_query_performance_benchmark.py`를 venv Python으로 재실행.
4. 같은 단위 테스트를 다시 실행.
5. Docker DB `localhost:15432` 상태를 확인한 뒤 작은 T-047 smoke benchmark를 실행한다.

## 2026-05-27 (T-051 — 에이전트별 worktree와 CodeGraph 운용 문서화)

**작업**: 사용자 요청에 따라 ChatGPT Codex, Claude Code, Google Antigravity 2.0이 같은 checkout을 공유하지 않고 에이전트별 고정 Git worktree를 유지하는 정책을 문서화했다.

**반영 상세**:
- ADR-034를 추가해 `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree와 `agent/<agent>-*` branch prefix를 확정했다.
- `docs/dev-environment.md`에는 최초 `git worktree add` 절차, 새 작업 branch 생성 절차, CodeGraph `init -i`/`sync`/`status` 운용 절차를 상세히 적었다.
- `AGENTS.md`, `SKILL.md`, `README.md`, `docs/agent-guide.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`에 핵심 규칙을 동기화했다.
- `.codegraph/`를 `.gitignore`에 추가해 로컬 SQLite 인덱스가 PR diff에 섞이지 않게 했다.

**검증**:
- CodeGraph 원문 문서에서 `codegraph init -i`가 `.codegraph/` 생성과 즉시 인덱싱을 수행하고, 기존 인덱스는 `codegraph sync`로 증분 갱신한다는 점을 확인했다.
- 최초 확인 시 로컬 WSL PATH에는 Windows npm shim(`/mnt/c/Users/digit/AppData/Roaming/npm/codegraph`)이 먼저 잡히며 `node: not found`로 실패했다. CodeGraph Linux installer로 `v0.9.6`을 `~/.codegraph`/`~/.local/bin`에 설치한 뒤 `codegraph --version`이 정상 동작함을 확인했다.
- `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree를 생성했다. 각 worktree에서 `codegraph init -i && codegraph status`를 실행했고, 201 files, 2,796 nodes, 6,251 edges, DB size 5.58 MB, `node:sqlite`/WAL, `Index is up to date` 상태를 확인했다.
- `git diff --check`, `.venv/bin/ruff check .`, `.venv/bin/mypy src/kraddr/geo`, `.venv/bin/lint-imports`, `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`를 실행했다. 결과는 `191 passed, 6 skipped`다.

**후속**:
- 이후 모든 새 작업은 해당 에이전트 고정 worktree에서 branch만 새로 따고, branch 전환 뒤 `codegraph sync`로 인덱스를 맞춘다.

## 2026-05-27 (PR #34~#47 리뷰 코멘트 audit/fixup)

**작업**: 사용자 지시에 따라 PR #34부터 #47까지 GitHub conversation comment, formal review body, inline review thread, GraphQL `reviewThreads`를 다시 확인했다. PR #34~#43에는 post-merge 리뷰 코멘트가 있었고, PR #44는 Windows Playwright 확인 메모, PR #45~#47은 확인 시점 기준 신규 코멘트가 없었다. unresolved current review thread는 0개였다.

**반영 상세**:
- `docs/postmerge-review-fixups-pr34-latest.md`를 추가해 PR별 코멘트, 이번 반영, 후속 이관 항목, 재사용할 GraphQL query template을 기록했다.
- PR #35 M3 반영: `LoadJobStatus.source_set`, `ConsistencyReport.source_set`, 내부 row protocol, `run_all_cases(source_set=...)` 타입을 `dict[str, Any]`로 넓혀 `SourceSetPlan`의 nested JSON을 보존한다. `openapi.json`, `kraddr-geo-ui/types/api.gen.ts`, `kraddr-geo-ui/lib/api.ts`도 함께 갱신했다.
- PR #43 M5 반영: `ops.audit_events.job_id` FK를 `ON DELETE SET NULL`에서 `ON DELETE NO ACTION`으로 변경했다. fresh DDL과 Alembic `0008_pr34_review_followups`를 추가해 감사 이벤트와 job 연결이 조용히 끊기지 않게 했다.
- PR #38/PR #42 후속 반영: `maplibre-vworld-js` upstream `main` 최신 SHA `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`를 확인해 `kraddr-geo-ui` dependency/lockfile과 문서를 갱신하고, Windows `npm` 오사용을 막는 `scripts/frontend_check.sh`를 추가했다.

**검증 계획**:
- 백엔드: `pytest`, `ruff`, `mypy`, `lint-imports`, OpenAPI drift check.
- 프론트엔드: WSL Linux Node/npm으로 `scripts/frontend_check.sh` 실행. Playwright는 사용자 지시에 따라 Windows Node/브라우저에서만 수행한다.

**후속**:
- T-050 운영 hardening을 백로그에 추가했다. upload set cleanup TTL/lock, callback HMAC/retry, backup/restore sub-progress, snapshot/release 자동 생성 hook, table stats cron, destructive confirmation flow, 실제 PostgreSQL constraint integration test를 묶어 처리한다.

## 2026-05-27 (T-027 — 최종 실 데이터 클린 적재와 same-month direct 출입구 gate)

**작업**: PR #46 머지 후 최신 main에서 Docker PostGIS DB를 비우고 실제 `data/juso` 원천을 처음부터 적재했다. `scripts/fullload_test.sh`를 T-038/T-039/T-042 이후 원천까지 포함하도록 보강하고, 전체 실행 로그·시스템 상태·row count·정합성 결과·data-quality export를 `artifacts/fullload/20260527_135155/`에 남겼다.

**반영 상세**:
- full-load script는 `tl_juso_parcel_link`, `tl_roadaddr_entrc`, `tl_sppn_makarea`를 함께 적재하고, source별 기준월(`JUSO=202603`, `LOCSUM/NAVI/SHP=202604`, `ROADADDR/SPPN=202605`)을 PLAN_ONLY와 로그에 명시한다.
- 실제 적재는 총 3,934초가 걸렸다. 주요 단계는 텍스트 825초, SHP 1,525초, direct 출입구 216초, SPPN 의무지역 33초, geometry link 140초, MV swap 159초였다.
- 최종 row count는 `tl_juso_text=6,416,637`, `tl_juso_parcel_link=1,769,370`, `tl_roadaddr_entrc=6,404,697`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,416,637`이다.
- direct 출입구를 기존 T-039 설계대로 1순위 serving 좌표로 쓰면 기준월 차이 때문에 C4/C6/C7이 악화됐다. `roadaddr` 우선 결과는 C4 12,225건(`over_500m=91`), C6 3,593건, C7 9,827건이었다.
- `tl_locsum_entrc`만 임시 비교하면 기존 기준선인 C4 3,415건(`over_500m=16`), C6 803건, C7 6,817건으로 돌아왔다. 이에 MV와 C3/C4/C6/C7/C8 serving CTE를 `locsum` 우선 + same-month `roadaddr` fallback으로 보정했다.
- C10은 `load_manifest`만 보던 한계를 수정해 row-level `source_yyyymm` 집계를 우선하고 manifest를 fallback으로 쓰게 했다. 현재 로컬 혼합 세트는 `distinct_months=3`, `severity=WARN`으로 기록된다.

**검증**:
- Targeted unit tests: `tests/unit/test_consistency_sql.py`, `tests/unit/test_infra_engine_pnu_sql.py` 통과.
- 보강 후 MV swap refresh 성공. `pt_source` 분포는 `centroid=3,496,182`, `entrance=2,906,372`, `NULL=14,083`이다.
- 보강 후 전체 C1~C10 재검증은 611.71초, 최대 RSS 82,424KB로 완료했다. `severity_max=ERROR`는 기존 C2/C4/C6/C7 원천 품질 이슈 때문이다.
- smoke test는 geocode/reverse/search/zipcode 모두 `OK`.
- data-quality export는 C2/C4/C6/C7 CSV 8개를 86.18초, 최대 RSS 82,292KB로 생성했다. C4 bucket은 `0-50=2,887,827`, `50-100=2,847`, `100-500=552`, `500+=16`이다.

**후속**:
- T-027 보강 PR을 열고 리뷰 대기 후 main에 머지한다.
- T-047은 이 클린 DB를 기준으로 query latency baseline과 튜닝 전후 차이를 기록한다.
- Playwright가 필요한 UI 검증은 사용자 지시에 따라 Windows Node/브라우저에서 수행한다.

## 2026-05-27 (T-042 — `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 구현)

**작업**: ADR-027의 `TL_SPPN_MAKAREA` 설계를 실제 DDL, loader, CLI/API job, source set optional child, geocode/reverse 보조 조회로 구현했다.

**반영 상세**:
- `tl_sppn_makarea` DDL과 Alembic `0007_t042_sppn_makarea`를 추가했다. 원천 `Polygon`은 운영 `MultiPolygon 5179`로 정규화한다.
- `load_sppn_makarea()`를 추가했다. `구역의 도형` ZIP, 디렉터리, 추출된 SHP 입력을 탐지하고 GDAL Python binding으로 staging table에 적재한 뒤 `SIG_CD + MAKAREA_ID` 기준으로 upsert한다.
- `kraddr-geo load sppn-makarea`, API queue kind `sppn_makarea_load`, source set optional `sppn_makarea` child를 연결했다.
- `core.sppn`에 국가지점번호 parser와 EPSG:5179 좌표 formatter를 추가했다.
- geocode는 국가지점번호 문자열을 좌표로 변환한 뒤 `ST_Covers(tl_sppn_makarea.geom, point)`로 검증하고, `x_extension.national_point_number`와 `x_extension.sppn_makarea`를 반환한다.
- reverse geocode는 도로명/지번 후보가 없어도 polygon 포함 여부가 있으면 `status="OK"`와 `x_extension.sppn_makarea`를 반환한다.
- 실제 적재 중 `REPLACE(col, chr(0), '')`가 PostgreSQL에서 `null character not permitted`를 유발하는 문제를 발견해 `NULLIF(BTRIM(col::text), '')`로 수정했다.

**검증**:
- Targeted unit/contract pytest 48건을 통과했다.
- Docker PostGIS `kraddr_geo_t042_sppn`에 세종 `구역의 도형/구역의도형_전체분_세종특별자치시.zip`을 실제 적재했다. 결과는 146행, 146 distinct key, source_yyyymm `202605`, 전체 valid MultiPolygon이었다.
- timed load는 `elapsed_s=1.35`, `max_rss_kb=131092`였다.
- `금이산` polygon 내부 `ST_PointOnSurface()`를 formatter로 `다바 7363 4856`으로 변환했고, geocode/reverse 보조 조회가 모두 `makarea_id=29`, `makarea_nm=금이산`을 반환했다.
- optional integration test `test_real_postgres_can_load_sppn_makarea_and_lookup_when_dsn_is_set`를 실제 DB DSN으로 실행해 통과했다.

**후속**:
- T-027 최종 클린 로드에서 `sppn_makarea` optional source를 포함할지 결정하고, 포함 시 전국 row count와 시간을 기록한다.
- T-047 성능 벤치마크에 국가지점번호 geocode/reverse Q11을 포함한다.
- T-044에서 최신 `maplibre-vworld-js` wrapper 기반 `TL_SPPN_MAKAREA` polygon overlay를 추가한다.

## 2026-05-27 (T-046 — 적재 완료 DB 백업/복원 및 UI 구현)

**작업**: ADR-030의 적재 완료 DB 백업/복원 설계를 실제 DTO, 설정, 실행 로직, REST API, CLI, 관리 UI, 테스트, 대구광역시 부분 DB 검증으로 구현했다.

**반영 상세**:
- `db_backup`, `db_restore` job kind와 `BackupCreateRequest`, `RestoreCreateRequest`, `BackupArtifact` DTO를 추가했다.
- `KRADDR_GEO_BACKUP_ALLOWED_DIRS`, 임시 디렉터리, 병렬 jobs, 압축 level, TTL, callback allowlist, download token secret 설정을 추가했다.
- `infra.backup`에서 allowlist/symlink escape 검증, `pg_dump -Fd --jobs`, `.part` 기반 `tar.zst` archive, manifest/checksum, `pg_restore -Fd --jobs`, target DB empty/current DB guard, callback, HMAC download token을 구현했다.
- `pg_dump`/`pg_restore` password는 argv에 넣지 않고 `PGPASSWORD` 환경변수로 넘기도록 해 process argument와 log 노출을 줄였다.
- `ops.artifacts` helper를 확장해 `db_backup` artifact metadata를 저장하고, backup/restore 작업을 기존 영속 `load_jobs` 큐에 연결했다.
- `/v1/admin/backups`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events`, `kraddr-geo backup/restore`, `/admin/backups` UI를 추가했다.
- OpenAPI와 `kraddr-geo-ui` 생성 타입/schema를 갱신했다.

**검증**:
- Backend targeted pytest 32건, `ruff`, `mypy`를 통과했다.
- Frontend `eslint`, `tsc --noEmit`, `vitest`, `next build`를 통과했다.
- Playwright 검증은 사용자 지시에 따라 Windows Node에서 수행했다. `/admin/backups` 화면에서 백업 시작, 복원 시작, 다운로드 링크 노출을 API mock으로 확인했고 screenshot은 `C:\Users\digit\AppData\Local\Temp\t046-admin-backups-windows.png`에 저장했다.
- Docker PostGIS에서 대구광역시 부분 원천을 실제 적재한 뒤 `/tmp/kraddr-t046/backups/t046_daegu_backup.tar.zst` 백업과 새 DB 복원을 수행했다. 원본/복원 row count는 `tl_juso_text=228,875`, `tl_juso_parcel_link=26,594`, `tl_locsum_entrc=228,610`, `tl_navi_buld_centroid=291,281`, `mv_geocode_target=228,875`로 일치했고, `대구광역시 중구 공평로 88` geocode/reverse smoke test가 모두 `OK`였다.

**후속**:
- callback retry/backoff, restore 취소 시 target DB drop/quarantine 정책, 디스크 여유 공간 사전 추정, PostgreSQL/PostGIS major mismatch hard-fail은 hardening task로 남긴다.
- 전국 full-load 재실행과 전체 쿼리 성능 벤치마크는 T-027/T-047에서 진행한다.
- 다음 작업은 T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회 구현이다.

## 2026-05-27 (T-045 — source set 기준월 선택과 대용량 업로드/적재 UX 구현)

**작업**: ADR-029의 source set 설계를 실제 DTO, 탐지/계획 helper, upload set 저장소, REST, 라이브러리, CLI, `/admin/load` UI와 테스트로 구현했다.

**반영 상세**:
- `SourceCandidate`, `SourceSetDiscovery`, `SourceSetPlan`, `UploadSetStatus`, `UploadFileStatus` DTO를 추가했다.
- `infra.source_set`에서 원천 후보를 자동 탐지하고, source kind별 기준월과 명시 `children` batch payload를 만드는 helper를 추가했다.
- `infra.uploads`에서 upload set을 JSON manifest로 영속화하고, raw stream 파일 저장, `*.part` atomic rename, sha256, 기준월/source kind 추론, 크기 제한 실패 상태, 취소를 구현했다.
- `/v1/admin/uploads/*`와 `/v1/admin/load-sources/*`를 추가하고, `/v1/admin/loads kind=full_load_batch`가 명시 child job 목록을 받도록 UI/라이브러리/CLI를 연결했다.
- `kraddr-geo load full-set`은 자동 발견 후 기준월이 섞이면 정확한 확인 문구 없이는 plan을 만들지 않는다.
- `/admin/load`는 다중 파일 선택과 DND, XHR upload progress, upload set cancel, source set review, 기준월 mismatch modal, 적재 진행률과 root job cancel을 제공한다.

**검증**:
- `tests/unit/test_source_set_plan.py`에서 source 탐지, optional 제외, 같은 기준월 plan, 혼합 기준월 확인, upload 저장/취소, 크기 제한 실패를 검증했다.
- `kraddr-geo-ui/tests/unit/load-workflow.test.ts`에서 상태 전이, 확인 token 생성, 진행률 계산을 검증했다.
- 중간 검증으로 backend targeted pytest, backend ruff/mypy, frontend lint/type-check/load-workflow test를 통과했다. 최종 PR 검증에서는 전체 backend/frontend gate와 OpenAPI drift 검사를 다시 수행한다.

**후속**:
- C10 정합성 severity 조정은 `source_set.mixed_yyyymm_acknowledged`를 더 읽도록 별도 보강한다.
- `ops.dataset_snapshots`에 source set 확정 정보를 자동 연결하는 일은 T-027/T-047 full-load gate 보강 때 이어간다.
- 다음 작업은 T-046 백업/복원 구현이다.

## 2026-05-27 (T-049 — 운영 메타데이터·감사·릴리스 스키마 구현)

**작업**: ADR-033의 `ops` 운영 메타데이터 설계를 실제 DDL, Alembic migration, DTO/API/client, 관리 UI, 테스트로 구현했다.

**반영 상세**:
- `ops.audit_events`, `ops.dataset_snapshots`, `ops.serving_releases`, `ops.artifacts`, `ops.maintenance_windows`, `ops.table_stats_snapshots`를 `sql/ddl/001_schema.sql`과 `src/kraddr/geo/infra/sql.py`에 추가하고, 기존 DB upgrade용 Alembic `0006_t049_ops_metadata_schema.py`를 작성했다.
- `ops.audit_events`는 append-only trigger로 UPDATE/DELETE를 막고, `ops.serving_releases`는 `state='active'` partial unique index로 active release 한 건만 허용한다.
- `kraddr.geo.core.redaction`을 추가해 API key, DSN, password, token, callback secret, 주소 원문을 audit payload에 평문 저장하지 않도록 했다.
- `AdminRepository`, `AsyncAddressClient`, `/v1/admin/ops/*` API를 추가했다. audit event/snapshot/release/artifact/maintenance/table stats 조회, rollback plan, maintenance window 생성/종료, table stats snapshot capture를 제공한다.
- `kraddr-geo-ui`에 `/admin/ops` 화면을 추가했다. release, snapshot, artifact, audit event, maintenance window, table stats snapshot을 조회하고 maintenance window 생성과 stats capture를 실행할 수 있다.
- OpenAPI와 frontend generated type/schema 목록을 갱신했다.

**검증**:
- `.venv/bin/python -m pytest -q` → 155 passed, 5 skipped.
- `.venv/bin/python -m ruff check .` 통과.
- `.venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` 통과.
- `.venv/bin/lint-imports` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run lint` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run type-check` 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test` → 22 passed.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run build` 통과.

**남은 연결**:
- T-045/T-027에서 source set 확정과 full-load/daily completion을 `ops.dataset_snapshots`에 연결한다.
- T-046에서 backup/restore 산출물을 `ops.artifacts`에 등록한다.
- T-047에서 성능 리포트와 전후 table stats snapshot을 `ops.artifacts`/`ops.table_stats_snapshots`에 연결한다.
- MV swap 성공 시 `ops.serving_releases` active row 교체는 T-027/T-047 gate와 함께 보강한다.

## 2026-05-27 (T-043 — PR #23~#41 리뷰 코멘트 audit/fixup)

**작업**: 사용자 지시에 따라 PR #23부터 최신 PR #41까지 GitHub 리뷰 표면을 thread-aware로 다시 확인하고, 반영 가능한 항목을 코드/문서로 보강했다.

**반영 상세**:
- GraphQL `pullRequest.comments`, `reviews`, `reviewThreads`와 REST review comment API를 함께 조회했다. 대상 PR 전체에서 unresolved review thread는 0개였다.
- `kraddr-geo-ui/lib/vworld.ts`의 `redactVWorldTileUrl` alias 수명 주석과 redaction test의 API key 누설 방지 assert를 추가했다.
- `kraddr-geo-ui/README.md`에 WSL ext4에서는 Linux Node/npm을 사용하라는 검증 경고를 추가했다.
- `docs/t035-mv-refresh-benchmark.md`에 session/wait event metadata 해석 가이드를 보강했다.
- `docs/t028-daily-juso-delta.md`에 신규 `MVM_RES_CD` 대응 절차, dedup 정렬 전제, `No Data` sentinel, checksum, queue 직렬화, daily 후 MV refresh 정책을 추가했다.
- CLI의 `--limit-per-file` 옵션 사용 시 stderr 경고를 출력하도록 했다.
- `TL_SPBD_BULD` projection staging 경로에 advisory lock을 추가하고, staging row count 대비 insert row count 차이를 skip metric으로 출력하도록 했다.
- ADR-027에 `TL_SPPN_MAKAREA` 원천 `Polygon` → 운영 `MultiPolygon` 변환 원칙과 T-042 진입 전 남은 위험을 추가했다.
- 상세 audit 표와 후속 이관 항목은 `docs/postmerge-review-fixups-pr23-latest.md`에 남겼다.

**검증**:
- `git diff --check` 통과.
- `.venv/bin/python -m pytest -q` → 150 passed, 5 skipped.
- `.venv/bin/python -m ruff check .` 통과.
- `.venv/bin/python -m mypy src/kraddr/geo` 통과.
- `.venv/bin/lint-imports` 통과.
- 프론트엔드 로컬 검증은 Linux Node가 없고 Windows `npm`만 잡혀 UNC 경로 오류가 나므로 실행하지 않았다. GitHub Actions frontend job에서 확인한다.

## 2026-05-27 (문서 정합성 재검토와 task 순서 재정렬)

**작업**: 사용자 지시에 따라 `main` 최신 문서와 실제 CLI/최근 ADR 사이의 불일치를 전체적으로 재검토하고 문서에 반영했다. 코드는 작성하지 않았다.

**반영 상세**:
- README/SKILL의 현재 상태와 quick start를 갱신했다. `load all-sidos` 예시는 실제 CLI 옵션(`--juso`, `--jibun`, `--locsum`, `--navi`, `--shp-root`, `--yyyymm`) 기준으로 바꿨다.
- 현재형 문서의 브랜치 표현을 `master`에서 `main`으로 바로잡았다. 단, `master table` 같은 DB 도메인 용어와 과거 작업 일지의 역사적 표현은 유지했다.
- `SKILL.md`의 “백엔드만 다룬다” 설명을 같은 저장소 안의 별도 Node.js 패키지 `kraddr-geo-ui`를 함께 관리한다는 설명으로 정리했다.
- T-046 백업 artifact metadata는 신규 구현에서 `ops.artifacts`로 수렴한다는 ADR-033 방향을 `docs/architecture.md`, `docs/t046-db-backup-restore.md`, `docs/decisions.md`에 맞췄다.
- `docs/tasks.md`와 `docs/resume.md`의 후속 순서를 T-043 → T-049 → T-045 → T-046 → T-042 → T-027 → T-047 → T-044로 재정렬했다. 데이터·운영 gate를 먼저 안정화한 뒤 지도 UI 경계화를 진행하는 순서다.
- 점검표와 남겨 둔 범위는 `docs/doc-consistency-audit-20260527.md`에 기록했다.

**검증**:
- `git diff --check` 통과.
- 현재 환경에는 `python` alias, `pytest`, `ruff`, `uv`가 없어 `pytest`/`ruff` 게이트는 실행하지 못했다. 후속 구현 작업 전 가상환경 복구가 필요하다.

## 2026-05-27 (README 법적 고지 — AI 활용 학습 목적과 데이터 준수 표기)

**작업**: 사용자 지시에 따라 README의 법적 고지에 프로젝트 목적과 데이터 사용 준수 원칙을 명시했다.

**반영 상세**:
- 이 프로젝트가 한국 주소 지오코딩 도메인을 대상으로 AI 활용 방식과 개발 워크플로를 학습·검증하기 위한 기술 연구 프로젝트임을 추가했다.
- 외부 원천 데이터와 API는 제공 기관의 이용약관, 저작권, 재배포 조건, 호출 한도를 준수하는 것을 전제로 사용하며 원천 데이터 자체를 저장소에 포함하지 않는다고 명시했다.
- 사용자 가시 문서 변경이므로 `CHANGELOG.md`에도 같은 요지를 남겼다.

## 2026-05-27 (T-049 등록 — 운영 메타데이터·감사·릴리스 스키마)

**작업**: 사용자 지시에 따라 유지보수와 관리 관점에서 추가해야 할 운영 기능, 테이블, 스키마를 ADR과 Task로 정리했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-033을 추가했다. 운영 메타데이터 전용 `ops` 스키마를 두고, 감사 이벤트, 데이터셋 snapshot, serving release, artifact registry, maintenance window, table stats snapshot을 관리하도록 결정했다.
- `docs/t049-ops-metadata-schema.md`를 추가했다. 각 테이블의 목적, 핵심 컬럼, API/UI 범위, 구현 순서, 검증 기준을 상세히 정리했다.
- `docs/tasks.md`에 T-049를 추가했다. destructive restore, schema migration, full reset은 active maintenance window와 typed confirmation 없이는 실패해야 한다는 요구도 포함했다.
- `docs/data-model.md`, `docs/architecture.md`, `README.md`, `CHANGELOG.md`, `docs/resume.md`를 같은 방향으로 갱신했다.

**결정**:
- `public`은 주소 원천·serving 객체, `x_extension`은 PostGIS 보조 extension, `ops`는 운영 제어면으로 분리한다.
- T-046의 `db_backup_artifacts`는 신규 구현에서는 `ops.artifacts`의 `artifact_type='db_backup'`으로 수렴한다.
- 감사 테이블에는 API key, DSN password, token, callback secret, 주소 원문을 평문 저장하지 않는다.

## 2026-05-27 (T-048 — `maplibre-vworld-js` 최신 동기화와 책임 경계 재정의)

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 사용 시 항상 최신 버전을 확인하고, 이 라이브러리의 특화 기능은 upstream `vworld.js`가 아니라 `kraddr-geo-ui` 쪽에서 구현한다는 원칙을 문서와 dependency에 반영했다.

**반영 상세**:
- `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main`으로 upstream `main` 최신 commit `1a28b1099ab6c9c03e892e469974aee8c07deda1`을 확인했다.
- `kraddr-geo-ui/package.json`과 `package-lock.json`의 `maplibre-vworld` dependency를 최신 확인 SHA로 갱신했다. CI에서 SSH key 없이 설치되도록 dependency와 lockfile `resolved`는 `git+https` 형식을 유지한다.
- ADR-032를 추가했다. VWorld layer/style, marker/popup/cluster primitive, tile error redaction, package export/type/CSS처럼 범용 기능은 `digitie/maplibre-vworld-js`에서 보강하고, geocode/reverse 입력 연결, API 응답 overlay, 정합성/성능/적재 상태 표시, 이 프로젝트 fallback UX는 `kraddr-geo-ui` domain wrapper에서 구현한다.
- `README.md`, `docs/architecture.md`, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/tasks.md`, `docs/resume.md`, `docs/t036-maplibre-vworld-sync.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `maplibre-vworld` dependency를 건드리는 PR은 최신 `main` 또는 stable release 확인 결과를 남긴다.
- upstream에 보낼 것은 범용 VWorld/MapLibre 기능이며, 주소 지오코딩 디버그/관리 UI에만 의미가 있는 기능은 이 저장소에서 구현한다.
- SHA 갱신 후에는 `kraddr-geo-ui`에서 `npm ci`, lint, type-check, test, build를 재검증한다.

## 2026-05-26 (T-047 등록 — 전국 적재 후 쿼리 성능 벤치마크와 튜닝 설계)

**작업**: 사용자 지시에 따라 전국 전체 적재 이후 지오코딩/역지오코딩/검색 쿼리 속도를 다수 반복 측정하고, 병목이 있으면 보조 view/materialized view까지 적극 도입하는 성능 튜닝 계획을 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-031을 추가했다. T-047은 p50/p95/p99, timeout, buffer, plan, 동시성 결과를 운영 준비 gate로 둔다.
- `docs/t047-query-performance-tuning.md`를 추가했다. benchmark corpus, 측정 방법, 초기 latency 목표, 튜닝 루프, 최소 실험 수, 보조 view/MV 후보, 산출물 구조, 후속 PR 순서를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`, `README.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- 속도는 정합성 이후 별도 gate로 관리한다. 전국 DB에서 목표를 초과하는 query군은 반드시 후보 실험을 수행한다.
- 보조 view/MV는 source of truth가 아니라 master table 또는 `mv_geocode_target`에서 재생성 가능한 read-only serving accelerator로만 허용한다.
- 튜닝 PR은 변경 전/후 p95/p99, plan, buffer, full-load/MV refresh/backup 부작용을 함께 기록해야 한다.

## 2026-05-26 (T-046 등록 — 적재 완료 DB 백업/복원 설계)

**작업**: 사용자 지시에 따라 완전히 적재한 PostgreSQL/PostGIS DB를 압축 artifact로 백업하고 새 DB로 복원하는 운영 설계를 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-030을 추가했다. 대용량 운영 기본값은 plain SQL/DDL dump가 아니라 `pg_dump -Fd --jobs` directory dump와 `tar.zst` 압축 아카이브다.
- `docs/t046-db-backup-restore.md`를 추가했다. 백업 profile, manifest, checksum, callback, 진행률 phase, 복원 안전장치, `/admin/backups` UI, 취소/실패 처리, 보안 allowlist를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/agent-guide.md`, `README.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `db_backup`과 `db_restore`는 백그라운드 job으로 실행하고, 상태 조회·취소·SSE는 중립 `/v1/admin/jobs/*` 표면을 우선 사용한다.
- 백업 파일은 브라우저 로컬 경로가 아니라 서버 allowlist 하위 경로에 저장한다. UI 다운로드 링크는 완료 artifact를 로컬로 받기 위한 부가 경로다.
- 구현 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB `kraddr_geo_t046_daegu` → `kraddr_geo_t046_daegu_restore` backup/restore로 먼저 수행한다.

## 2026-05-26 (T-045 등록 — source set 기준월 선택과 업로드/적재 UX)

**작업**: 사용자 지시에 따라 원천 자료별 기준월이 다를 수 있음을 전제로 한 적재 UX와 API/CLI 함수 분리 설계를 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- ADR-029를 추가했다. 원천 묶음은 단일 `yyyymm`이 아니라 `source_set.yyyymm_by_kind`로 기록하고, 혼합 기준월은 사용자 확인을 거쳐야 한다.
- `docs/t045-source-set-load-ux.md`를 추가했다. CLI 대화형 확인, 비대화형 confirmation token, `discover_load_sources()`와 `build_full_load_source_set_plan()` 함수 분리, upload set API, UI 다중 파일/DND 업로드, 업로드/적재 진행률과 취소 UX를 상세히 정리했다.
- `docs/backend-package.md`, `docs/frontend-package.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- API/라이브러리는 사용자 prompt를 띄우지 않고 발견/계획/등록을 분리한다.
- CLI와 UI는 기준월 mismatch를 사용자에게 표로 보여 주고, 명시 확인 없이는 적재를 시작하지 않는다.
- 업로드는 DB 적재와 분리한다. 모든 파일 저장과 checksum/기준월 분석이 끝난 뒤에만 `full_load_batch`를 등록한다.

## 2026-05-26 (T-044 등록 — `maplibre-vworld-js` 완전 포팅)

**작업**: 사용자 지시에 따라 디버그 UI를 `maplibre-vworld-js`로 완전히 포팅하는 작업을 백로그와 ADR에 추가했다.

**반영 상세**:
- `docs/tasks.md`에 T-044를 추가했다. 범위는 `CoordinateMap.tsx`의 직접 MapLibre wiring을 upstream `VWorldMap` 또는 동등한 Hook/component로 대체하는 것이다.
- ADR-028을 추가했다. 부족한 click callback, marker 제어, `flyToOptions`, tile error hook/redaction, key 미설정 fallback, SSR-safe 사용법, 타입/패키징 문제는 `python-kraddr-geo`에서 우회하지 않고 `digitie/maplibre-vworld-js`를 직접 수정한다.
- `docs/frontend-package.md`, `docs/architecture.md`, `docs/t036-maplibre-vworld-sync.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- T-044는 두 저장소 작업으로 본다. 필요한 upstream 보강은 `maplibre-vworld-js` PR/commit으로 남기고, 그 검증된 SHA를 `kraddr-geo-ui` dependency로 소비한다.
- 완료 조건에는 upstream test/build와 `kraddr-geo-ui`의 `npm ci`, lint, type-check, test, build 검증을 포함한다.

## 2026-05-26 (T-043 등록 — PR #23~#33 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #23부터 최신 PR #33까지의 리뷰 코멘트를 다시 읽고 반영하는 후속 작업을 백로그에 추가했다.

**반영 상세**:
- `docs/tasks.md` 대기 목록 최상단에 T-043을 추가했다.
- 대상 범위는 PR #23~#33이다. PR #33은 먼저 main에 merge한 뒤 이 작업을 등록했다.
- 확인 표면은 `comments`, `reviews`, `latestReviews`, pull request review comments, GraphQL `reviewThreads`를 모두 포함한다.
- 완료 산출물은 `docs/postmerge-review-fixups-pr23-pr33.md`로 지정했다.
- `docs/resume.md`의 다음 작업을 T-043으로 갱신했다.

**다음 작업**: T-043을 실제로 수행할 때 PR별 코멘트/스레드 표를 만들고, 반영 가능한 변경은 후속 fixup PR로 올린다.

## 2026-05-26 (T-041 후속 — `TL_SPPN_MAKAREA` 문서 보강)

**작업**: 사용자 설명을 반영해 `TL_SPPN_MAKAREA`를 단순 overlay 후보가 아니라 국가지점번호 표기 의무지역 polygon으로 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- `docs/t041-detail-zone-shape-layers.md`에 `TL_SPPN_MAKAREA`의 네이밍(`SPPN`, `MAKAREA`), 업무 의미, 지점번호표기 의무지역 개념, geocode/reverse geocode 활용 방식을 상세히 추가했다.
- ADR-027을 추가했다. `TL_SPPN_MAKAREA`는 `mv_geocode_target`에 union하지 않고, 후속 `tl_sppn_makarea` 별도 테이블과 `x_extension.sppn_makarea` 또는 `type='sppn_area'` 후보로 노출한다.
- `docs/data-model.md`, `docs/backend-package.md`, `docs/t030-extra-shape-sources.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `TL_SPPN_MAKAREA`는 개별 국가지점번호판 point 목록이 아니라 표기 의무지역 polygon이다.
- geocode는 국가지점번호 문자열 parser/generator가 좌표를 계산한 뒤 해당 좌표가 의무지역에 속하는지 검증하는 enrichment로 사용한다.
- reverse geocode는 도로명/지번 주소 후보가 없거나 confidence가 낮은 비거주지역에서 `ST_Covers` 기반 보조 후보로 사용한다.
- 구현 후속 작업은 T-042로 등록했다.

**검증**:
- 문서 변경만 수행했다. `git diff --check`로 whitespace를 확인한다.

## 2026-05-26 (T-037 — SHP geometry 포함 대형 레이어 적재 튜닝)

**작업**: PR #31 merge 이후 `codex/t037-shp-geometry-tuning` 브랜치에서 `TL_SPBD_BULD` 직접 GDAL append 병목을 projection staging table 경로로 보강했다.

**반영 상세**:
- `src/kraddr/geo/loaders/shp/polygons_loader.py`에서 `TL_SPBD_BULD`만 `_kraddr_stage_spbd_buld_polygon` staging table로 분기한다.
- staging 생성은 `accessMode="overwrite"`, `PG_USE_COPY=YES`, `SHAPE_ENCODING=CP949`, 기존 `plan.sql_statement` projection을 함께 사용한다.
- 운영 테이블 insert는 `SET LOCAL search_path = public, x_extension` 후 `INSERT ... SELECT`로 수행하고, `ST_Multi(geom)::geometry(MultiPolygon, 5179)`와 문자열 trim/NULL 정규화, 건물번호 integer cast를 명시했다.
- staging table은 시작 전과 종료 `finally`에서 모두 drop한다.
- `docs/t037-shp-geometry-tuning.md`를 추가하고 `docs/backend-package.md`, `docs/t034-shp-append-tuning.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**실제 파일 검증**:
- 세종 단일 `TL_SPBD_BULD`: 기존 append 38.36초 → projection staging 18.59초, 55,819행, source 추적 컬럼 전량 채움, staging table 없음.
- 경기도 raw staging은 원본 DBF 전체 속성을 복사해 22분 58.46초 동안 끝나지 않아 `pg_terminate_backend()`로 중단했다. 중단 지점은 GDAL feature 617,214 부근이었다.
- 경기도 projection staging: 1,649,975행, 40분 17.15초, source 추적 컬럼 전량 채움, staging table 없음.
- 세종 public CLI `kraddr-geo load shp ... --mode full --yyyymm 202604`: 9개 레이어 적재 성공, 1분 19.54초, `tl_spbd_buld_polygon=55,819`, `tl_sprd_intrvl=100,009`, `tl_sprd_rw=7,429`.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q` → 17 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo/loaders/shp/polygons_loader.py` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없거나 반영이 끝나면 main에 merge하고 T-027 최종 실 데이터 클린 적재 검증으로 진행한다.

## 2026-05-26 (T-041 — 상세주소 동 도형/구역 추가 레이어 검토)

**작업**: PR #30 merge 이후 `codex/t041-extra-shape-layer-review` 브랜치에서 `건물군 내 상세주소 동 도형`과 `구역의 도형`을 실제 세종/경남 파일로 전자지도와 비교했다.

**반영 상세**:
- `src/kraddr/geo/loaders/shape_dbf.py`를 추가해 DBF/SHP layer summary와 key set overlap helper를 공용화했다.
- T-040 `building_shape_bundle.py`는 공용 helper를 사용하도록 정리했다.
- `src/kraddr/geo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`를 추가했다.
- ADR-026을 추가했다. 상세주소 동 도형과 구역 추가 레이어는 기본 `full_load_batch`/`mv_geocode_target`에 섞지 않고, 필요 시 별도 overlay/분석 테이블로 둔다.

**실제 파일 검증**:
- 세종 상세주소 동 polygon은 40,478행이고 전자지도 `TL_SPBD_BULD` 55,819행의 부분집합이었다. `BD_MGT_SN + EQB_MAN_SN` 교집합은 40,478, detail only 0, 전자지도 only 15,341이다.
- 경남 상세주소 동 polygon은 923,702행이고 전자지도 `TL_SPBD_BULD` 1,269,029행의 부분집합이었다. 교집합은 923,702, detail only 0, 전자지도 only 345,327이다.
- 세종 `구역의 도형` 중 `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`는 전자지도와 key 기준 완전 중복이었다. 경남도 같은 결과다.
- `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key 교집합이 0건이고, `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key였다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_building_shape_bundle.py tests/unit/test_extra_shape_layers.py tests/integration/test_real_extra_shape_sources.py -q` → 11 passed, 2 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp KRADDR_GEO_SLOW_REAL_DATA=1 .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q` → 1 passed in 16.74s.
- `scripts/compare_extra_shape_layers.py`로 세종 실제 파일 JSON 출력을 확인했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 148 passed, 5 skipped.
- `ruff check .`, `mypy src/kraddr/geo scripts/compare_extra_shape_layers.py scripts/compare_building_shape_bundle.py`, `lint-imports`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없으면 main에 merge하고 T-037 geometry 포함 SHP 대형 레이어 적재 튜닝으로 진행한다.

## 2026-05-26 (T-040 — `도로명주소 건물 도형` bundle 비교)

**작업**: PR #29 merge 이후 `codex/t040-building-shape-bundle` 브랜치에서 `도로명주소 건물 도형` bundle과 기존 전자지도 건물/출입구 레이어의 natural key overlap을 실제 파일로 비교했다.

**반영 상세**:
- `src/kraddr/geo/loaders/building_shape_bundle.py`를 추가했다. ZIP 내부 `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC`와 전자지도 `TL_SPBD_BULD`, `TL_SPBD_ENTRC`의 DBF key set을 순수 Python으로 비교한다.
- `scripts/compare_building_shape_bundle.py`를 추가해 세종/경남 비교 결과를 JSON으로 재현할 수 있게 했다.
- ADR-025를 추가했다. `도로명주소 건물 도형`은 단순 중복이 아니지만 현행 `tl_spbd_buld_polygon`/serving MV에는 섞지 않고, 후속 loader가 필요하면 `tl_roadaddr_buld_polygon`, `tl_roadaddr_buld_entrc`, `tl_roadaddr_spot_cntc` 같은 별도 테이블로 둔다.
- 세종 실제 비교는 기본 integration test로 넣고, 경남 full key scan은 `KRADDR_GEO_SLOW_REAL_DATA=1` 선택 테스트로 분리했다.

**실제 파일 검증**:
- 세종 address polygon key: bundle 27,792 distinct, 전자지도 `TL_SPBD_BULD` 55,819 distinct, 교집합 15,339, bundle only 12,453, 전자지도 only 40,480.
- 경남 address polygon key: bundle 656,230 distinct, 전자지도 `TL_SPBD_BULD` 1,269,029 distinct, 교집합 345,290, bundle only 310,940, 전자지도 only 923,739.
- 세종 출입구 key: bundle 28,111, 전자지도 27,787, 교집합 27,766, bundle only 345, 전자지도 only 21.
- 경남 출입구 key: bundle 661,416, 전자지도 656,133, 교집합 656,114, bundle only 5,302, 전자지도 only 19.

**검증**:
- `python -m pytest tests/unit/test_building_shape_bundle.py tests/integration/test_real_extra_shape_sources.py -q` → 7 passed, 1 skipped.
- `KRADDR_GEO_SLOW_REAL_DATA=1 python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_building_shape_bundle_gyeongnam_key_overlap_slow -q` → 1 passed in 18.48s.
- `python -m pytest -q` → 144 passed, 4 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `git diff --check` → 통과.

## 2026-05-26 (T-039 — PR 전 검증 보강)

**작업**: T-039 PR 생성 전 전체 검증을 돌리며 문서/DDL/테스트 계약을 보강했다.

**반영 상세**:
- 기본 DDL 문자열(`sql/ddl/001_schema.sql`, `infra/sql.py`)에서 `tl_roadaddr_entrc.ent_man_no`를 Alembic 0005와 동일하게 nullable로 맞췄다. 반대로 기존 `tl_locsum_entrc.ent_man_no`는 `sig_cd + ent_man_no` PK이므로 `NOT NULL`을 유지한다.
- `tests/unit/test_consistency_sql.py`는 T-039의 `serving_entrc` CTE와 `source_kind` sample을 검증하도록 갱신했다.
- `docs/backend-package.md`, `docs/t039-roadaddr-entrance-loader.md`, `README.md`에 T-039 이전 MV가 있는 DB에서는 direct 출입구 적재 뒤 `kraddr-geo refresh mv --swap`을 권장한다고 명시했다.

**검증**:
- `python -m pytest -q` → 141 passed, 3 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check --output openapi.json`, `git diff --check` → 통과.
- Docker PostGIS `localhost:15432`의 새 `kraddr_geo_t039` DB에서 `tests/integration/test_optional_real_postgres_load.py` → 1 passed in 2.86s.
- `kraddr-geo-ui`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

## 2026-05-26 (T-039 — `도로명주소 출입구 정보` direct entrance loader)

**작업**: PR #28 merge 이후 `codex/t039-direct-entrance-loader` 브랜치에서 `RNENTDATA_2605_*.txt` direct entrance 원천을 적재하는 T-039를 구현했다.

**반영 상세**:
- `tl_roadaddr_entrc` 테이블과 Alembic `0005_t039_roadaddr_entrance_table`을 추가했다. 실제 파일에서 `ent_man_no`가 비는 행이 있어 PK는 `bd_mgt_sn` 단독으로 두고, `ent_man_no`는 nullable 원천 보존 필드로 둔다.
- `src/kraddr/geo/loaders/text/roadaddr_entrance_loader.py`를 추가했다. 디렉터리 입력 시 17개 ZIP 내부의 `RNENTDATA_*.txt` member를 직접 발견하고, 좌표 결측/`0/0` sentinel row는 skip한다.
- CLI `kraddr-geo load roadaddr-entrances`와 API job kind `roadaddr_entrance_load`를 추가했다.
- `mv_geocode_target` 대표 좌표 선택 순서를 `tl_roadaddr_entrc` → `tl_locsum_entrc` → `tl_navi_buld_centroid`로 바꿨다. 응답 호환성을 위해 direct entrance도 기존 `pt_source='entrance'`로 둔다.
- C3/C4/C6/C7/C8 정합성 SQL은 `tl_roadaddr_entrc`와 `tl_locsum_entrc`를 합친 대표 출입구 CTE를 사용하게 했고, C10 기준월 비교에 `tl_roadaddr_entrc`를 포함했다.

**실제 파일/DB 검증**:
- 전국 17개 ZIP을 직접 읽어 총 6,418,169행, 모든 행 19컬럼, `ent_source_cd='RM'`, `ent_detail_cd='01'`을 확인했다.
- 세종 ZIP은 원천 27,868행, distinct `bd_mgt_sn` 27,868, 빈 `ent_man_no` 9건, 유효 좌표 적재 대상 27,779행이었다.
- 경남 ZIP은 원천 657,845행, distinct `bd_mgt_sn` 657,845, 빈 `ent_man_no` 100건이었다.
- Docker PostGIS `localhost:15432`에 `kraddr_geo_t039` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.74s`이며 세종 RNENTDATA 3행이 `tl_roadaddr_entrc`와 `load_manifest`에 반영됐고, MV의 `pt_5179`가 direct entrance 좌표를 사용함을 확인했다.
- 대상 테스트 `tests/unit/test_roadaddr_entrance_loader.py`, `tests/integration/test_real_roadaddr_entrance_files.py`, schema/batch/CLI 계약 테스트 → 29 passed.
- 대상 `ruff check`와 `mypy src/kraddr/geo` → 통과.

**다음 작업**: 전체 검증과 frontend/OpenAPI drift 확인 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-038 — `tl_juso_parcel_link` DDL/로더 구현)

**작업**: PR #27 merge 이후 `codex/t038-parcel-link-loader` 브랜치에서 ADR-022의 보조 지번 1:N 테이블을 실제 구현했다.

**반영 상세**:
- `tl_juso_parcel_link` 테이블, 인덱스 3종, Alembic `0004_t038_parcel_link_table`을 추가했다. `bd_mgt_sn`은 `tl_juso_text` FK + `ON DELETE CASCADE`, PK는 `(bd_mgt_sn, pnu)`다.
- `src/kraddr/geo/loaders/text/parcel_link_loader.py`를 추가했다. `jibun_rnaddrkor_*` full snapshot은 기본 `TRUNCATE` 후 UPSERT하고, daily `LNBR`은 `MVM_RES_CD` mapping에 따라 UPSERT/DELETE한다.
- CLI `kraddr-geo load parcel-links`, `kraddr-geo load daily-parcel-links`를 추가했다.
- API job kind `juso_parcel_link_load`, `juso_parcel_link_delta`를 추가했고, `full_load_batch` 기본 child 순서에 `juso_text_load` 직후 `juso_parcel_link_load`를 넣었다.
- `kraddr-geo-ui` `/admin/load` 기본 payload에도 `juso_parcel_link_load`를 추가했다.
- `daily_juso_delta`는 MST 전용으로 유지하고, 같은 ZIP의 LNBR은 `juso_parcel_link_delta`로 별도 적용한다.

**실제 파일/DB 검증**:
- 실제 `jibun_rnaddrkor_seoul.txt`를 새 iterator로 파싱해 PNU `1111012000101500000`, `1114010300100680000`을 확인했다.
- 실제 `20260401_dailyjusukrdata.zip`의 LNBR 204행을 새 iterator로 파싱하고 첫 행 PNU `4148025326100310007`, `mvmn_de=20260402`, `MVM_RES_CD=31`을 확인했다.
- Docker PostGIS `localhost:15432`에 `kraddr_geo_t038` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.81s`이며 snapshot 2행, daily LNBR 5행이 `tl_juso_parcel_link`와 `load_manifest`에 반영됐다.
- 전체 `pytest -q` → 133 passed / 3 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
- frontend `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기한다. 리뷰 코멘트가 있으면 최대한 반영하고, 없으면 main에 merge한 뒤 T-039로 진행한다.

## 2026-05-26 (T-030 — 별도 도형/출입구 자료 검토)

**작업**: PR #26 merge 이후 `codex/t030-extra-shape-sources` 브랜치에서 별도 도형/출입구 ZIP 4종을 실제 세종특별자치시 파일로 확인했다.

**실제 파일 확인**:
- `건물군내동도형_전체분_세종특별자치시.zip`: `TL_SGCO_RNADR_DONG` Polygon 40,478행, `TL_SPBD_ENTRC_DONG` Point 4,098행.
- `구역의도형_전체분_세종특별자치시.zip`: 기존 전자지도와 중복되는 `TL_SCCO_*`, `TL_KODIS_BAS` 외에 `TL_SCCO_GEMD` 24행, `TL_SPPN_MAKAREA` 146행이 있다.
- `건물도형_전체분_세종특별자치시.zip`: `TL_SGCO_RNADR_MST` Polygon 27,792행, `TL_SPBD_ENTRC` Point 28,111행, `TL_SPOT_CNTC` PolyLine 27,776행.
- `도로명주소출입구_전체분_세종특별자치시.zip`: `RNENTDATA_2605_36110.txt` 19컬럼 텍스트이며 direct `bd_mgt_sn`, 도로명주소 키, 출입구 관리번호, EPSG:5179 X/Y를 제공한다.

**결정**:
- 네 자료를 현재 full-load 기본 source child에는 즉시 추가하지 않는다.
- `도로명주소 출입구 정보`는 direct `bd_mgt_sn + 5179 point`라 T-039 후보로 둔다.
- `도로명주소 건물 도형`은 전자지도 `TL_SPBD_BULD` 단순 중복이 아니므로 T-040에서 bundle 비교를 진행한다.
- 상세주소 동 도형과 구역 추가 레이어는 T-041에서 디버그 UI/상세주소/품질 분석 용도를 따로 검토한다.
- ADR-023과 `docs/t030-extra-shape-sources.md`에 근거와 후속 순서를 기록했다.

**검증 진행**:
- `pytest tests/integration/test_real_extra_shape_sources.py -q` → 4 passed.
- `pytest -q` → 128 passed / 3 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-029 — `jibun_rnaddrkor_*` 활용 결정)

**작업**: PR #25 merge 이후 `codex/t029-jibun-rnaddrkor-decision` 브랜치에서 `jibun_rnaddrkor_*`와 daily `TH_SGCO_RNADR_LNBR.TXT`의 실제 구조와 cardinality를 확인했다.

**실제 파일 확인**:
- `jibun_rnaddrkor_seoul.txt` 첫 행은 14컬럼이며, daily `LNBR`도 같은 14컬럼 구조를 쓰되 마지막 컬럼에 `MVM_RES_CD`가 들어간다.
- 전국 `jibun_rnaddrkor_*`: 1,769,370행, distinct `bd_mgt_sn` 986,309, 2개 이상 보조 지번을 가진 건물 334,789건, 한 건물 최대 545행.
- 서울 `jibun_rnaddrkor_seoul.txt`: 89,290행, distinct `bd_mgt_sn` 52,280, 2개 이상 보조 지번을 가진 건물 13,318건.
- 서울 `jibun_rnaddrkor` PNU와 `rnaddrkor` 대표 PNU 비교: 89,290행 중 89,289행이 대표 PNU와 다르고, `rnaddrkor`에서 찾지 못한 `bd_mgt_sn`은 0건이었다.
- daily `20260401` LNBR: 204행, distinct `bd_mgt_sn` 72, 2개 이상 변경 지번을 가진 건물 31건, 코드 분포 `31=74`, `63=130`.

**결정**:
- `jibun_rnaddrkor_*`와 daily `LNBR`는 `tl_juso_text.pnu`에 덮어쓰지 않는다.
- 후속 T-038에서 `tl_juso_parcel_link` 별도 1:N 테이블을 도입한다.
- `mv_geocode_target`은 계속 `bd_mgt_sn` unique를 유지하고, 보조 지번은 지번 검색 후보 확장/디버그 표시/정합성 검증에 단계적으로 연결한다.
- ADR-022와 `docs/t029-jibun-rnaddrkor-decision.md`에 근거와 테이블 초안을 기록했다.

**검증 진행**:
- `pytest tests/integration/test_real_jibun_rnaddrkor_files.py -q` → 2 passed.
- 전체 `pytest -q` → 124 passed / 3 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-028 — 도로명주소 일변동 ZIP 로더)

**작업**: PR #24 merge 이후 `codex/t028-daily-delta-loader` 브랜치에서 `data/juso/daily/*.zip` 일변동 ZIP 로더를 구현했다.

**반영 상세**:
- `src/kraddr/geo/loaders/text/daily_juso_loader.py`를 추가했다. `AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT`를 읽어 `tl_juso_text`에 UPSERT/DELETE로 반영한다.
- `MVM_RES_CD`는 `Settings.mvm_res_code_actions`를 사용한다. 기본값은 `31/33=insert`, `34/35/36=update`, `63/64=delete`이며, 알 수 없는 코드는 `LoaderError`로 중단한다.
- 한 batch 안의 동일 `bd_mgt_sn`은 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 master에 반영한다.
- `TH_SGCO_RNADR_LNBR.TXT`는 현재 master table에 쓰지 않고 `unsupported_lnbr_rows`로 집계해 `load_manifest.source_set`에 남긴다. T-029에서 `jibun_rnaddrkor_*`와 함께 1:N 지번 관계 테이블 여부를 결정한다.
- member 내용이 `No Data`인 경우 컬럼 수 오류로 보지 않고 skip하며 `skipped_no_data_sources`에 기록한다.
- CLI `kraddr-geo load daily-juso`와 API job kind `daily_juso_delta`를 추가했고, `openapi.json` 및 `kraddr-geo-ui/types/api.gen.ts`를 갱신했다.
- ADR-021과 `docs/t028-daily-juso-delta.md`를 추가해 MST/LNBR 분리, manifest watermark, 실제 파일 검증 수치를 문서화했다.

**실제 파일 확인**:
- `/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip`의 MST member는 422행이며 코드 분포는 `31=185`, `34=57`, `63=180`이었다.
- 같은 ZIP의 LNBR member는 204행이며 이번 구현에서는 manifest에 미지원 행 수로만 기록한다.
- `/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260404_dailyjusukrdata.zip`은 MST/LNBR 모두 `No Data`였다.

**검증 진행**:
- `pytest tests/unit/test_daily_juso_loader.py tests/integration/test_real_juso_text_loaders.py::test_actual_daily_juso_zip_loads_mst_rows_and_skips_no_data_members tests/unit/test_cli_contract.py -q` → 11 passed.
- `pytest tests/integration/test_real_juso_text_loaders.py -q` → 실제 NTFS `data/juso` fallback으로 5 passed.
- Docker PostGIS `localhost:15432`에 전용 DB `kraddr_geo_t028`을 생성하고 `KRADDR_GEO_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t028 pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 이 검증은 daily sample 3행 적용 뒤 `load_manifest.last_mvmn_de=20260402`, `row_count=3`, `unsupported_lnbr_rows=204`까지 확인한다.
- 대상 `ruff check`와 대상 `mypy` → 통과.
- `scripts/export_openapi.py`와 frontend `npm run gen:types` 실행.
- 전체 `pytest -q` → 122 passed / 3 skipped.
- `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
- frontend `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

**다음 작업**: 전체 검증과 실제 PostgreSQL sample daily load를 실행한 뒤 PR을 열어 리뷰 대기한다.

## 2026-05-26 (PR #20~#22 post-merge 리뷰 반영)

**작업**: T-036 PR #23이 main에 merge된 뒤, 사용자 지시 순서대로 PR #22 → PR #21 → PR #20 리뷰 코멘트를 thread-aware 방식으로 확인했다. 세 PR 모두 merged 상태였고 conversation comment 1개씩만 있었으며 formal review와 inline review thread는 없었다.

**PR #22 반영**:
- `postload.rename_mv_next_indexes_for_conn(conn)` public helper를 추가해 benchmark script가 `_rename_mv_next_indexes` private helper를 직접 import하지 않게 했다.
- `scripts/benchmark_mv_refresh.py`에 `schema_version=2`, `metadata`(`trial_index`, `cache_warm_hint`, `notes`, active session 수, wait event snapshot)를 추가했다.
- `_optional_int()`는 `ProgrammingError`만 잡고 rollback한 뒤 `None`을 반환한다.
- benchmark와 production `shadow_swap_mv()`의 `ANALYZE` transaction에도 `SET LOCAL lock_timeout = '2s'`를 적용했다.
- `docs/data-model.md` shadow swap 예시는 실제 `idx_mv_next_*` → `idx_mv_*` index rename 단계를 보여주도록 보강했다.

**PR #21 반영**:
- `TL_SPRD_INTRVL` COPY row를 `RoadIntervalRow` dataclass로 묶고, `ROAD_INTERVAL_COPY_COLUMNS`와 tuple shape를 같은 코드 표면에 둔다.
- CP949 decode 실패와 truncated record 오류 메시지에 파일, record, field, byte size 문맥을 포함한다.
- psycopg COPY connection은 `autocommit=False`를 명시하고 explicit commit 의도를 주석으로 남겼다.
- deleted record skip, CP949 decode error, truncated record error 단위 테스트를 추가했다.

**PR #20 반영**:
- `scripts/fullload_test.sh`에 DDL, juso, locsum, navi, SHP, link, MV, total timer를 추가했다.
- `docs/t033-full-load-revalidation.md`에 SHP 시간 출처, 단발 측정 한계, C10 `OK 0` 의미, `tl_navi_entrc` 원천 cross-check 필요성을 명시했다.
- `TL_SPBD_BULD` 등 geometry 포함 대형 SHP 튜닝을 T-037 후보로 등록했다.

**검증 진행**:
- `pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py -q` → 8 passed.
- `pytest tests/unit/test_shp_loader_gdal.py -q` → 16 passed.
- 대상 `ruff check` → 통과.
- 전체 `pytest -q` → 113 passed / 7 skipped.
- `ruff check .`, `mypy src/kraddr/geo scripts/benchmark_mv_refresh.py`, `lint-imports`, `bash -n scripts/fullload_test.sh`, `git diff --check` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후, 코멘트가 있으면 반영하고 없으면 main에 merge한다.

## 2026-05-26 (T-036 — `maplibre-vworld-js` main 동기화)

**작업**: PR #22 merge 이후 `codex/t036-maplibre-vworld-sync` 브랜치에서 `kraddr-geo-ui`의 `maplibre-vworld` dependency를 `digitie/maplibre-vworld-js` 최신 main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신했다.

**반영 상세**:
- `kraddr-geo-ui/package.json`과 lockfile의 `maplibre-vworld` GitHub SHA를 `11321fe8b8f4da849ee5c24ba18a27206a55e26e`에서 `c91c9f304669ce3f5fc4915f21186b23731d5816`로 올렸다. CI에서 SSH key 없이 설치되어야 하므로 dependency와 `resolved`는 모두 `git+https`를 유지한다.
- 최신 upstream은 `redactVWorldTileUrl()`가 아니라 `redactVWorldUrl()`를 export하고, redaction 표기는 `[redacted]` 대신 `***`를 사용한다.
- `kraddr-geo-ui/lib/vworld.ts`는 `redactVWorldUrl as redactVWorldTileUrl` alias를 둬 기존 `CoordinateMap` import 계약을 유지한다.
- VWorld helper 테스트는 최신 upstream redaction 표기 `***`를 검증하도록 갱신했다.
- `docs/t036-maplibre-vworld-sync.md`에 upstream 확인 SHA, API 변경, WSL Linux Node 검증 명령, 남은 작업 순서를 기록했다.

**검증**:
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm ci --ignore-scripts` → 통과. 기존 moderate advisory 7건은 유지.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run lint` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run type-check` → 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run build` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 사용자 지시대로 PR #22, PR #21, PR #20 순서로 신규 리뷰 코멘트를 확인하고 반영 가능한 항목을 처리한다.

## 2026-05-26 (T-035 — MV refresh/swap 벤치마크)

**작업**: PR #21 merge 이후 `codex/t035-mv-refresh-benchmark` 브랜치에서 `mv_geocode_target` 갱신 전략을 실제 전국 DB `kraddr_geo_t033`에서 비교했다. 재현 가능한 계측을 위해 `scripts/benchmark_mv_refresh.py`를 추가하고, `CONCURRENTLY`와 shadow swap의 phase별 시간, temp file/byte 증가, index 크기를 JSON으로 남겼다.

**실행 환경**:
- Docker PostGIS: `kraddr-geo-t027-db-1`, `localhost:15432`, DB `kraddr_geo_t033`.
- 데이터 상태: T-033 전국 full-load 결과, `mv_geocode_target=6,416,637`, DB size 약 26GB.
- 시스템: WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, 16 logical cores, RAM 29GiB, 실행 시 available 약 27GiB.
- artifact: `artifacts/t035-mv-refresh-20260526_045339/` (git ignore).

**측정 결과**:
- `CONCURRENTLY`: `/usr/bin/time` wall clock 1분 49.64초. phase는 `refresh_concurrently=106.68초`, `analyze=4.96초`. temp는 +91 files, +12,309,605,099 bytes. 실행 중 `BufFileWrite` I/O wait가 관측됐다.
- `swap`: `/usr/bin/time` wall clock 2분 16.28초. `rebuild.create_next=68.79초`, index build 합계 약 63.29초, `swap.analyze_live=4.89초`. temp는 +44 files, +9,150,995,144 bytes.
- swap의 rename/index rename 구간(`drop_old_pre`, `rename_live_to_old`, `rename_next_to_live`, `drop_old_post`, `rename_indexes`) 합계는 약 0.016초였다.

**반영 상세**:
- `scripts/benchmark_mv_refresh.py`는 `--strategy concurrent|swap`와 `--output`을 받아 phase별 JSON을 출력한다.
- `postload.build_mv_next_sql()`을 공개 helper로 분리해 실제 swap SQL과 benchmark script가 같은 SQL 생성 경로를 공유한다.
- 기존 `shadow_swap_mv()`가 rename/drop 이후 `ANALYZE`까지 같은 transaction에서 실행하던 점을 확인하고, rename transaction과 `ANALYZE` transaction을 분리했다. 이로써 swap lock-sensitive 구간에 약 4.9초짜리 통계 갱신을 포함하지 않는다.
- 최종 검증에서 `mv_geocode_target_next`, `mv_geocode_target_old`는 남지 않았고, 운영 index 이름은 `idx_mv_*`로 정상 정규화됐다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py -q` → 8 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check scripts/benchmark_mv_refresh.py tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py src/kraddr/geo/loaders/postload.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy scripts/benchmark_mv_refresh.py src/kraddr/geo/loaders/postload.py` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-036에서 `maplibre-vworld-js` upstream main과 UI dependency를 동기화한다.

## 2026-05-26 (T-034 — SHP append 병목 튜닝)

**작업**: PR #20 merge 이후 `codex/t034-shp-append-tuning` 브랜치에서 T-033의 최우선 병목이었던 `TL_SPRD_INTRVL` 적재 경로를 보강했다. geometry가 없는 DBF 속성 레이어는 GDAL `VectorTranslate` append를 우회해 직접 DBF scan + `psycopg COPY`로 적재하도록 분기했다.

**실행 환경**:
- Docker PostGIS: `kraddr-geo-t027-db-1`, `localhost:15432`.
- 데이터: ext4 mirror `/home/digitie/kraddr-geo-data/juso/도로명주소 전자지도`.
- 시스템: WSL2 Linux `6.6.87.2-microsoft-standard-WSL2`, 16 logical cores, RAM 29GiB, 실행 시 available 약 27GiB.
- 디스크: ext4 `/dev/sdd` 1007G 중 758G available, NTFS `/mnt/f` 932G 중 267G available.

**반영 상세**:
- `polygons_loader._load_plans_sync()`에서 `TL_SPRD_INTRVL`만 `_copy_road_interval_dbf()`로 라우팅한다.
- DBF parser는 `SIG_CD`, `RDS_MAN_NO`, `BSI_INT_SN`, `ODD_BSI_MN`, `EVE_BSI_MN`만 추출하고, 기존 추적 컬럼 `source_file`, `source_yyyymm`을 유지한다.
- 도형 레이어(`TL_SPBD_BULD`, `TL_SPRD_RW`, 행정경계 등)는 기존 GDAL 경로를 그대로 사용한다.
- synthetic DBF unit test를 추가해 필드 순서, 숫자 필드 공백 trim, 빈 값 `None` 처리, COPY row projection을 고정했다.

**측정 결과**:
- 세종 `TL_SPRD_INTRVL` 100,009행 단일 레이어: 기존 GDAL 경로 36.12초 → 새 COPY 경로 1.59초.
- 경기도 `TL_SPRD_INTRVL` 2,677,715행 단일 레이어: 새 COPY 경로 15.88초. T-033 관찰상 기존 경기도 레이어는 약 24분 이상이었다.
- 세종 9개 SHP 레이어 전체 CLI 적재: 31.69초, `tl_sprd_intrvl=100,009`, `tl_spbd_buld_polygon=55,819`, `tl_sprd_rw=7,429`.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q` → 12 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- 실제 Docker DB `kraddr_geo_t034_before`, `kraddr_geo_t034_after`, `kraddr_geo_t034_sejong`에서 기준선/개선 후/9개 레이어 전체 적재를 확인했다.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-035에서 MV refresh/swap benchmark를 진행한다. `TL_SPBD_BULD` GDAL append 병목은 도형 포함 대형 레이어라 이번 PR에서는 유지하고, 별도 튜닝 후보로 남긴다.

## 2026-05-26 (T-033 — 전국 full-load 성능 재검증)

**작업**: PR #19 merge 이후 `codex/t033-full-load-revalidation` 브랜치에서 빈 Docker DB `kraddr_geo_t033`를 만들고 실제 전국 `data/juso` full-load를 다시 실행했다. 사용자 지시에 따라 로그와 시스템 상태를 상세히 남기고, T-034/T-035 튜닝 전 기준선으로 문서화했다.

**실행 환경**:
- Docker PostGIS: `kraddr-geo-t027-db-1`, `localhost:15432`, DB `kraddr_geo_t033`.
- 데이터: ext4 mirror `/home/digitie/kraddr-geo-data`, 원본 `/mnt/f/dev/python-kraddr-geo/data/juso`.
- 로그: `artifacts/t033-full-load-20260525_224643/` (git ignore).

**결과**:
- full-load 전체 wall clock 4시간 8분 2초, 최대 RSS 187,964KB, exit status 0.
- 텍스트 3종은 1,098초에 완료했다. `tl_juso_text=6,416,637`, `tl_locsum_entrc=6,405,091`, `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`.
- SHP 17개 시도 × 9개 레이어 총 153 layers를 완료했다. `tl_sprd_intrvl=16,993,167`, `tl_sprd_rw=1,482,679`, `tl_spbd_buld_polygon=10,687,732`.
- `resolve_text_geometry_links()`는 약 2분 32초, `refresh mv --swap`은 약 2분 28초에 완료했다. `mv_geocode_target=6,416,637`.
- Smoke test는 geocode/reverse/search/zipcode 모두 `OK`.
- C1~C10 정합성은 `severity_max=ERROR`로 완료했다. 기존 실제 데이터 품질 이슈인 C2 34,699건, C4 over_500m 16건, C6 803건, C7 6,817건이 재현됐다.
- C2/C4/C6/C7 data-quality CSV 8개를 1분 20.41초에 export했다.

**관찰**:
- `TL_SPRD_INTRVL`은 geometry 없는 interval 테이블인데도 GDAL `VectorTranslate` 경로에서 `INSERT INTO "tl_sprd_intrvl" ... VALUES ...`로 관측됐다. 경기도 interval 단일 레이어가 약 24분 이상 걸려 T-034의 최우선 튜닝 대상이다.
- `TL_SPBD_BULD`도 batch INSERT 형태로 관측됐다. geometry 포함 대형 레이어라 비용은 예상되지만 COPY 적용 여부 확인이 필요하다.
- SHP 적재 중 DB CPU는 대체로 30~50%, 메모리는 4~9GiB 수준이었다. C4/C5 정합성 검증에서는 메모리가 약 14GiB까지 올라갔다.
- `TL_SPRD_RW`, `TL_SPBD_BULD`, 일부 행정경계 SHP에서 winding order 자동 보정 경고가 반복됐지만 적재는 계속 진행됐다.

**다음 작업**: PR #20으로 T-033 문서 PR을 열고 20분 리뷰 대기 후, 코멘트 반영 또는 무코멘트면 main에 merge한다. 이후 T-034에서 `TL_SPRD_INTRVL` 전용 COPY 로더 또는 GDAL 옵션 분리 튜닝을 진행한다.

## 2026-05-25 (PR #19 리뷰 반영 — T-032 머지 전 보강)

**작업**: PR #19 formal review를 확인하고 머지 권장 조건(M1, M3+L1, L9)과 즉시 처리 가능한 Low 항목을 반영했다.

**반영 상세**:
- `export_data_quality_samples()`는 prepare temp table 생성과 export query를 명시적 `async with conn.begin()` 안에서 실행한다. DB transaction 뒤에 CSV를 쓰도록 해 `ON COMMIT DROP` temp table 계약과 lock 시간을 분리했다.
- `data_quality`의 로컬 SQL splitter를 제거하고 `infra.sql.iter_sql_statements()`로 통합했다. 공용 splitter는 string literal, quoted identifier, comment, dollar quote 안의 세미콜론을 보존한다.
- `resolve_text_geometry_links()`는 기본 30분 transaction-local timeout 의도를 docstring으로 설명하고, `statement_timeout_ms=None`이면 caller/session timeout을 유지하도록 열어뒀다.
- `load_shp_polygons(analyze=...)` docstring을 추가하고, `_analyze_target_tables()`는 테이블마다 별도 transaction으로 `ANALYZE`를 실행한다. 대상 테이블 dedup은 `_unique_target_tables()` helper로 의도를 고정했다.
- `docs/tasks.md`에 T-033(전국 full-load 재검증), T-034(SHP GDAL append 병목 튜닝), T-035(MV refresh/swap 벤치마크)를 추가했다.
- Alembic `0003_t032_performance_indexes.py`에는 대용량 운영 DB에서 일반 `CREATE INDEX`를 점검 창에 적용해야 한다는 주석을 남겼다.

**검증**: 리뷰 반영 뒤 대상 단위 테스트 41개 통과, 전체 `pytest -q` 104 passed / 7 skipped, `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 세종·경남 축소 검증 1회)

**작업**: 사용자 지시에 따라 반복 횟수를 1회로 낮추고, 세종특별시·경상남도 축소 데이터만 실제 Docker DB(`kraddr_geo_t032`)에 적재했다. 전국 full test와 반복 trial은 수행하지 않았다.

**결과**:
- `load all-sidos --no-refresh --allow-consistency-error`는 SHP 18개 layer 적재까지 완료했으나 `resolve_text_geometry_links()` 첫 UPDATE가 기본 5초 `statement_timeout`에 걸려 실패했다. 경과 2시간 1분 13초, 최대 RSS 163,672KB.
- 실패를 반영해 `resolve_text_geometry_links()`에 transaction-local 30분 timeout을 추가했다.
- 같은 DB에서 후처리만 재실행해 28.53초, 최대 RSS 77,156KB로 성공했다.
- C4/C6/C7 data-quality export는 11.25초, 최대 RSS 79,884KB로 CSV 6개를 생성했다.
- C4/C6/C7 정합성은 14.88초, 최대 RSS 80,204KB로 완료했다. `severity_max=ERROR`이며 C4 213건(`over_500m=2`), C6 77건, C7 851건이다.

**관찰**: 두 시도 축소 검증에서도 `TL_SPRD_INTRVL` 1,960,217행, `TL_SPBD_BULD` 1,324,177행 append가 전체 시간을 지배했다. GDAL `PG_USE_COPY=YES` 설정에도 `pg_stat_activity`에서는 일부 구간이 INSERT 형태로 관측되어, 후속 PR에서 GDAL COPY 강제 여부와 `TL_SPRD_INTRVL` 전용 loader를 다시 검토한다.

**검증**: 대상 단위 테스트 38개, 전체 `pytest -q` 101 passed / 7 skipped, `ruff check .`, `mypy src/kraddr/geo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 성능 튜닝 범위 축소)

**작업**: PR #18 merge 이후 T-032를 시작했다. 사용자 지시에 따라 성능 튜닝 반복 기준은 기존 "10회 이상"에서 "세종특별시·경상남도 축소 데이터 1회 검증"으로 낮췄다. 전체 전국 full test와 반복 trial은 후속 안정화 단계로 미룬다.

**구현 방향**:
- C4 data-quality export는 nearest polygon 거리 계산을 `_kraddr_dq_c4_distances` 임시 테이블로 한 번 만들고, sample CSV와 bucket CSV가 같은 결과를 재사용하도록 바꾼다.
- C6/C7 data-quality export는 polygon mismatch 결과를 case별 임시 violation 테이블로 한 번 만들고, sample CSV와 region summary CSV가 같은 결과를 재사용하도록 바꾼다.
- C4/C6/C7 정합성 SQL은 PostgreSQL planner가 고비용 CTE를 중복 평가하지 않도록 `MATERIALIZED` CTE를 명시한다.
- `load shp-all` 및 `load all-sidos --shp-root`는 여러 시도 SHP를 연속 적재할 때 각 시도마다 통계를 갱신하지 않고 마지막 시도 뒤 1회만 `ANALYZE`한다.

**검증 계획**: `kraddr_geo_t032` Docker DB에서 세종특별자치시·경상남도 데이터 1회만 적재/검증한다. 현재 실행 중이며, 완료 결과와 경과 시간은 이 항목 또는 후속 항목에 이어 적는다.

## 2026-05-25 (PR #18 rebase — VWorld debug helper sync)

**작업**: 사용자 지시에 따라 T-032 성능 튜닝 전에 PR #18을 먼저 처리했다. PR #17이 main에 merge되어 `CHANGELOG.md`, `docs/journal.md`, `docs/resume.md`에서 충돌이 발생했으며, PR #17 데이터 품질 기록과 PR #18 VWorld sync 기록을 모두 보존하는 방식으로 rebase했다.

**검증**:
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과. high 기준 취약점 없음, moderate 7건은 기존 Next/PostCSS 및 Vitest/Vite 경로 잔여.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `git diff --check` → 통과.

**다음 작업**: PR #18을 푸시하고 PR 본문/코멘트를 갱신한다. PR #18 안정화 후 별도 T-032 성능 튜닝 PR을 시작한다.

## 2026-05-25 (PR #17/T-031 — 데이터 품질 export와 실제 DB 검증)

**작업**: PR #16 merge 확인 후 PR #17을 최신 `main` 위로 rebase했다. 충돌은 `docs/journal.md`, `docs/resume.md`에서만 발생했고, T-031 기록과 PR #15/VWorld 기록을 모두 보존하는 방식으로 해결했다.

**구현 상세**:
- `src/kraddr/geo/loaders/data_quality.py`를 추가했다. C2/C4/C6/C7 후속 분석용 CSV 8종(`c2_samples`, `c2_missing_key_summary`, `c4_distance_samples`, `c4_distance_buckets`, `c6/c7 samples`, `c6/c7 region_summary`)을 같은 SQL로 재현할 수 있다.
- `kraddr-geo validate data-quality-samples` CLI를 추가했다. `--cases C2,C4,C6,C7`, `--limit`, `--output-dir`로 산출 범위를 제어한다.
- SHP 보조 로더가 GDAL `SQLStatement` projection에 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`을 넣도록 보강했다. 기존 T-027 DB는 재적재 전이라 polygon `source_file`이 NULL이지만, 이후 재적재분부터 원천 파일 역추적이 가능하다.
- C4 sample CSV에는 출입구 좌표, 가장 가까운 polygon 대표점 좌표, `delta_lon`, `delta_lat`를 함께 넣어 500m+ 이상치의 좌표계/원천 오류 패턴을 빠르게 볼 수 있게 했다.

**실제 검증**:
- Docker DB: `kraddr-geo-t027-db-1`, `localhost:15432`.
- `kraddr-geo validate data-quality-samples --cases C2,C4,C6,C7 --limit 5` → CSV 8개 생성, 2분 52.45초, 최대 RSS 79,956KB.
- `kraddr-geo validate data-quality-samples --cases C4 --limit 20` → C4 CSV 2개 생성, 2분 22.90초, 최대 RSS 80,008KB.
- `delta_lon`/`delta_lat` 컬럼 추가 후 `kraddr-geo validate data-quality-samples --cases C4 --limit 3` → 2분 18.48초, 최대 RSS 80,124KB. 상위 3건의 `delta_lon`은 각각 약 `1.9998~1.9999`도였다.
- C2 `missing_resolve_key` 581건은 모두 `rds_sig_cd` 결측으로 확인했다. 기존 DB는 PR #17 이전 적재분이라 SHP `source_file`도 NULL이다.
- C4 bucket은 `0~50=2,887,827`, `50~100=2,847`, `100~500=552`, `500+=16`이었다. 500m+ 상위 7건은 출입구 경도만 polygon보다 약 `+2.0`도 동쪽으로 튄 패턴이라, 다음 지도 overlay와 원천 row 확인 대상으로 분리한다.
- C6 상위 region은 `54002=49`, `48700=23`, `54004=15`; C7 상위 region은 `48121103=216`, `28260101=167`, `41273104=165`였다.

**검증 명령**:
- `pytest tests/unit/test_data_quality_exports.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 21 passed.
- `ruff check` 대상 파일 묶음 → 통과.

**다음 작업**: PR #17에 푸시하고 리뷰 요청한다. 안정화 후 별도 T-032 PR에서 C4/C6/C7 export 중복 스캔 제거와 full-load/postload/MV swap 속도 튜닝을 10회 이상 trial and error로 기록한다.

## 2026-05-25 (T-031 데이터 품질 후속 PR 분리)

**작업**: PR #14가 close 예정이므로, 추가 TODO를 PR #14에 계속 쌓지 않고 별도 후속 PR에서 다룰 수 있도록 T-031 문서를 추가했다.

**반영 상세**:
- `docs/t027-data-quality-followup.md`를 추가해 C2/C4/C6/C7 잔여 `ERROR`의 현재 수치, 분석 원칙, sample 산출물, 지도 확인, 원천 파일 역추적 순서를 정의했다.
- `docs/tasks.md`에 T-031을 추가하고, `docs/resume.md`의 다음 작업을 후속 PR 기준으로 바꿨다.
- `CHANGELOG.md`에 후속 분석 문서 추가를 기록했다.

**다음 작업**: T-031 PR에서는 sample 추출 SQL, 지도 확인 경로, `source_file` 추적성 보강 전략을 구현하고 실제 산출물 요약을 PR 본문에 첨부한다.

## 2026-05-25 (후속 PR — VWorld debug 동작 upstream sync)

**작업**: `maplibre-vworld-js` PR #9를 먼저 열어 `VWorldMap`의 click/error/flyTo hook과 VWorld tile error/redaction helper를 추가했다. 이어 `kraddr-geo-ui` 후속 브랜치에서 upstream commit `11321fe`로 dependency를 동기화하고, 디버그 UI의 tile error 분류와 URL redaction을 upstream helper로 교체했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#11321fe`로 갱신했다. lockfile의 `resolved`도 SSH가 아니라 HTTPS를 유지한다.
- `kraddr-geo-ui/lib/vworld.ts`에서 `isVWorldTileError()`와 `redactVWorldTileUrl()`를 재수출한다.
- `components/vworld/CoordinateMap.tsx`는 로컬 `isTransientTileError()`/`redactVWorldTileUrl()` 중복 구현을 제거하고 upstream helper를 사용한다. key 미설정 fallback, overlay 임계치, marker 즉시 이동, SSR dynamic wrapper는 기존 UI 계약대로 유지한다.
- VWorld helper 단위 테스트에 tile error 분류와 key redaction 검증을 추가했다.

**검증**:
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리베이스 — maplibre-vworld package 소비)

**작업**: PR #14가 main에 merge된 뒤 `codex/maplibre-vworld-ui`를 최신 `main` 위로 rebase했다. 이후 upstream `digitie/maplibre-vworld-js` main commit `a5b3c65`를 확인하고, `kraddr-geo-ui`가 VWorld helper/CSS를 실제 `maplibre-vworld` package에서 소비하도록 갱신했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#a5b3c65`로 고정했다. CI에서 SSH key 없이 설치되어야 하므로 package-lock의 `resolved`도 `git+https`로 유지했다.
- `kraddr-geo-ui/lib/vworld.ts`는 로컬 구현을 제거하고 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `VWorldLayerType`를 upstream package에서 재수출한다.
- 전역 CSS는 `maplibre-vworld/style.css`를 import한다. 이 package export가 MapLibre GL 기본 CSS와 package CSS를 함께 제공한다.
- upstream style source id가 `vworld-${layerType}`이고 `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 쓰므로, tile error source 판별을 `vworld` prefix 기준으로 바꿨다.
- Vitest/jsdom에서 upstream bundle이 `maplibre-gl` worker URL과 React `require()` 경로를 건드리는 문제를 테스트 setup shim으로 보정했다. 이 현상은 후속 `maplibre-vworld-js` 정합화 PR에서 upstream 테스트/번들 개선 후보로 추적한다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, README, changelog, `docs/resume.md`를 최신 package 소비 상태로 갱신했다.
- `VWorldMap` 컴포넌트 전체 대체는 이번 PR에 넣지 않고 후속 PR로 분리했다. 후속 PR은 click callback, marker 제어, tile error hook/redaction, key 미설정 fallback, SSR-safe wrapper를 `kraddr-geo-ui`와 `maplibre-vworld-js` 사이에서 맞추는 작업이다.

**검증**:
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 20 tests 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kraddr-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리뷰 보강 — VWorld MapLibre 안정화)

**작업**: PR #15 리뷰의 merge condition을 반영했다. 디버그 UI는 VWorld WMTS + MapLibre GL JS 방향을 유지하되, upstream package가 안정화되기 전까지 `maplibre-vworld` GitHub 의존성을 UI 패키지 graph에 올리지 않는 정책으로 정리했다.

**구현 상세**:
- `maplibre-vworld` 미사용 GitHub 의존성을 `kraddr-geo-ui/package.json`과 lockfile에서 제거했다. upstream 보강은 별도 PR로 진행하고, 안정 태그 또는 SHA에서 install/build가 검증된 뒤 다시 도입한다.
- `components/vworld/LazyCoordinateMap.tsx`를 추가해 `CoordinateMap`을 `next/dynamic(..., { ssr: false })`로 지연 로딩한다. `/debug/geocode`, `/debug/reverse`는 이 wrapper만 import한다.
- `CoordinateMap.tsx`에서 VWorld tile fetch 오류를 transient로 분리했다. tile URL은 key가 드러나지 않도록 redaction한 뒤 경고 로그만 남기고, 누적 임계치 이상이거나 tile 외 오류일 때만 overlay를 표시한다.
- `lib/vworld.ts`에 레이어별 `maxZoom`을 추가했다. `Base`/`gray`/`midnight`는 z19, `Hybrid`/`Satellite`는 z18로 제한한다. attribution 표기도 `공간정보 오픈플랫폼 브이월드`로 보정했다.
- marker 위치 갱신 시 `flyTo({ animate: false, duration: 0 })`를 사용해 지도 클릭 후 불필요한 애니메이션 되튐을 줄였다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/resume.md`, changelog에 dependency 미선언 정책, dynamic import, tile error 처리, zoom 한계, CSP/key 제한 주의사항을 명시했다.
- PR 리뷰를 놓치지 않도록 `docs/resume.md`의 알려진 함정에 conversation comment와 formal review를 모두 확인하는 루틴을 추가했다.

**검증**:
- `cd kraddr-geo-ui && npm run lint` → 통과.
- `cd kraddr-geo-ui && npm run type-check` → 통과.
- `cd kraddr-geo-ui && npm run test` → 7 files / 18 tests 통과. `CoordinateMap` fallback과 dynamic loading skeleton 테스트를 포함한다.
- `cd kraddr-geo-ui && npm ci --ignore-scripts` → 통과. `maplibre-vworld` GitHub dependency 없이 cold install을 확인했다.
- `cd kraddr-geo-ui && npm run build` → 통과. `/debug/geocode`, `/debug/reverse`가 static route로 생성되고 지도 bundle은 dynamic import 경로로 분리된다.
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여다.
- `cd kraddr-geo-ui && npm run dev -- --hostname 127.0.0.1 --port 3001` 후 `HEAD /debug/reverse` → 200 OK. 서버 렌더 단계에서는 skeleton이 표시되고 지도 bundle은 클라이언트 chunk로 분리됨을 HTML에서 확인했다.

## 2026-05-25 (디버그 UI 지도 VWorld/MapLibre 전환)

**작업**: 사용자 지시에 따라 `kraddr-geo-ui`의 디버그 지도 방향을 Kakao Maps SDK에서 VWorld WMTS + MapLibre GL JS로 전환했다. 실제 VWorld API key는 저장소에 기록하지 않고, `.env.local`의 `NEXT_PUBLIC_VWORLD_API_KEY`로만 주입하는 정책을 유지했다.

**구현 상세**:
- `react-kakao-maps-sdk` 의존성을 제거하고, 직접 사용하는 `maplibre-gl`을 명시 의존성으로 추가했다.
- `components/kakao/CoordinateMap.tsx`를 `components/vworld/CoordinateMap.tsx`로 교체했다. 지도 click은 기존과 동일하게 `(lon, lat)` 순서로 callback을 호출하고, marker도 EPSG:4326 좌표를 그대로 사용한다.
- `lib/vworld.ts`에 VWorld WMTS tile URL과 MapLibre raster style helper를 추가했다. `Base`/`gray`/`midnight`/`Hybrid`는 `png`, `Satellite`는 `jpeg` 타일을 사용한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 지도 로딩에 실패하면 기존처럼 같은 크기의 좌표 fallback preview를 보여 준다.

**문서화**:
- ADR-020을 추가했다. 디버그 UI 지도는 VWorld WMTS + MapLibre를 기준으로 하고, `digitie/maplibre-vworld-js`의 패키징·타입·Next.js 호환 문제가 나오면 해당 저장소도 적극 수정 대상에 포함한다고 명시했다.
- `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, `README.md`, `docs/resume.md` 등에 VWorld 지도 환경변수와 upstream 보강 원칙을 반영했다.

**검증**:
- `cd kraddr-geo-ui && npm run lint` → 통과.
- `cd kraddr-geo-ui && npm run type-check` → 통과.
- `cd kraddr-geo-ui && npm run test` → 6 files / 15 tests 통과. VWorld WMTS helper 단위 테스트를 포함한다.
- `cd kraddr-geo-ui && npm ci --ignore-scripts && npm run build` → 통과. HTTPS Git dependency lockfile 재현성을 확인했다.
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여.
- `NEXT_PUBLIC_VWORLD_API_KEY=<local only> npm run dev -- --hostname 127.0.0.1 --port 3001` 후 `HEAD /debug/reverse` → 200 OK.

## 2026-05-25 (PR #14 추가 리뷰 반영 — L1~L6, C2/C4/C6/C7 재검토)

**작업**: PR #14의 최종 리뷰 body와 thread-aware review fetch 결과를 다시 확인했다. unresolved inline thread는 없었고, 추가 반영 대상은 N1/N2와 가능하면 L1~L6, C2/C4/C6/C7 재검토였다.

**반영 상세**:
- N1: `0002_t027_shp_schema_fixups`가 기존 `tl_sprd_rw`의 `MULTILINESTRING` row 때문에 `MULTIPOLYGON` cast에서 실패하지 않도록, non-polygon row가 있으면 `tl_sprd_rw`를 먼저 `TRUNCATE`하고 타입을 변경한다. recovery/fullload 문서에도 이 destructive-but-required 동작과 이후 SHP full reset 필요성을 명시했다.
- N2/L1: MV shadow swap 인덱스 rename은 `MV_NEXT_INDEX_RENAMES` 고정 목록이 아니라 `pg_index`/`pg_class` live catalog에서 `idx_mv_next_%`를 조회해 target name을 유도한다. stale 운영 인덱스가 있어 새 next index를 drop하는 경우에는 `logging.warning`과 `warnings.warn`을 모두 남긴다.
- L2: `copy_locsum_rows()` staging 중복 제거의 tie-breaker를 `ctid`에서 temp `staging_seq BIGSERIAL`로 바꿨다. 같은 staging batch 안에서 마지막으로 copy된 row가 명시적으로 선택된다.
- L3: navi build/entrance loader가 빈 좌표뿐 아니라 `0`/`0.0` sentinel 좌표도 skip한다. EPSG:5179에서 원점 좌표는 한국 주소 데이터로 볼 수 없으므로 실제 적재 오염을 막는다.
- L5/L6: `shp-all --mode full`의 첫 시도 full, 이후 append 시퀀스를 helper와 테스트로 분리했다. GDAL PostgreSQL conninfo에는 기본 `connect_timeout=10`을 추가하고 URL query의 `connect_timeout`을 존중한다.
- C2/C4/C6/C7: C2 metric에 `missing_resolve_key`와 `missing_text`를 분리해 남은 `ERROR`의 성격을 후속 분석할 수 있게 했다. C4 metric은 `error_count=over_500m`를 명시한다. C6/C7은 경계 위 point를 false positive로 보지 않도록 `ST_Contains`에서 `ST_Covers`로 바꿨다.

**검증**:
- 대상 단위 테스트 20개 → 통과.
- `pytest -q` → 84 passed, 7 skipped.
- `ruff check .` → 통과.
- `mypy src/kraddr/geo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- 실제 T-027 Docker DB(`localhost:15432`)에서 C2/C4/C6/C7만 선택 재검증했다. 경과 3분 53.82초, 최대 RSS 80,076KB, `severity_max=ERROR`.
  - C2: 34,699건 유지. 새 metric은 `missing_text=34,118`, `missing_resolve_key=581`.
  - C4: 3,415건 유지. `over_500m=16`, `error_count=16`, `p95=3.82m`, `p99=15.50m`.
  - C6: 803건 유지. `ST_Covers` 전환 후에도 `outside_polygon=803`.
  - C7: 6,817건 유지. `ST_Covers` 전환 후에도 `outside_polygon=6,817`.

**다음 작업**: PR #14는 close 예정이므로 C2/C4/C6/C7의 원천 데이터 품질 분석, sample별 지도 확인, source_file 추적성 보강은 후속 PR에서 진행한다.

## 2026-05-25 (PR #14 리뷰 반영 — schema migration, SHP natural key, 리뷰 확인 프로토콜)

**작업**: PR #14의 정식 review body(`# PR #14 리뷰 — T-027 actual full-load execution fixes`)와 마지막 Optional conversation comment를 모두 확인하고 반영했다.

**반영 상세**:
- H1: `alembic/versions/0002_t027_shp_schema_fixups.py`를 추가했다. 기존 DB에 `tl_spbd_buld_polygon` natural key 컬럼, `tl_sprd_manage.geom`, `tl_sprd_rw.geom` `MULTIPOLYGON` 타입 변경을 적용한다.
- H2: `tl_spbd_buld_polygon.bjd_cd` generated column은 `LI_CD=''`를 `00`으로 보정하고, `rncode_full`은 빈 문자열을 NULL로 취급하도록 `SCHEMA_SQL`과 `sql/ddl/001_schema.sql`을 수정했다.
- M1: stale 운영 MV index가 남아 있어 새 `idx_mv_next_*`를 drop하는 복구 경로에서 `warnings.warn`을 남기도록 했다.
- M2: SHP full reset은 `TRUNCATE` 직전 대상 테이블별 approximate row count snapshot을 출력한다. 문서에는 full mode 중단 시 9개 SHP 테이블이 비거나 일부만 적재된 상태일 수 있음을 명시했다.
- M3/L7: 내비 loader의 `limit`은 좌표 결측 skip 이후 yield row 기준임을 docstring으로 명시하고, C4 SQL에는 `resolve_text_geometry_links()` 선행 의존성을 주석으로 남겼다.
- Optional: Docker 포트 환경변수를 저장소 prefix 규칙에 맞춰 `KRADDR_DB_PORT`에서 `KRADDR_GEO_DB_PORT`로 변경했다.
- 반복 방지: `docs/agent-guide.md`에 PR 리뷰 확인 프로토콜을 추가했다. 앞으로 PR 리뷰 반영 시 conversation comments뿐 아니라 `reviews[].body`와 `review_threads[]`를 반드시 확인한다.

**검증**:
- `pytest tests/unit/test_alembic_migrations.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_shp_loader_gdal.py tests/unit/test_postload_mv.py tests/unit/test_navi_loader.py tests/unit/test_consistency_sql.py -q` → 17 passed.
- `ruff check .` → 통과.
- `mypy src/kraddr/geo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- `PATH="$PWD/.venv/bin:$PATH" DATA_DIR=/home/digitie/kraddr-geo-data KRADDR_GEO_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` → 통과. 출력 DSN은 `localhost:15432`.
- `pytest -q` → 80 passed, 7 skipped.
- 임시 DB `kraddr_geo_pr14_review`에서 `alembic upgrade head` → 0001, 0002 적용 성공. `LI_CD=''` 샘플 insert 시 generated `bjd_cd=1111010100`, `rncode_full=111103100012` 확인.
- 실제 T-027 DB 영향 조회: `empty_li=0`, `empty_rn=0`, `empty_rds_sig=0`, `bjd_8=0`, `bjd_10=10,687,732`.

## 2026-05-25 (PR #14/T-027 — 실제 전국 SHP 재적재와 정합성 재검증)

**작업**: `data/juso/도로명주소 전자지도` 실제 전국 SHP 17개 시도 × 9개 레이어를 새 natural-key 스키마로 Docker PostGIS에 재적재하고, C1~C10 정합성 검증을 실제 DB에서 재실행했다.

**실행 로그**:
- 상세 로그: `artifacts/fullload/20260524_173115/execution-log.md` (git ignore 산출물)
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Python 3.12.3, GDAL 3.8.4
- DB: `kraddr-geo-t027-db-1`, `localhost:15432`, `kraddr_geo`
- SHP 재적재 경과: 3시간 10분 4초, exit status 0, 최대 RSS 187,100KB
- 종료 직후 DB 크기: 24GB
- 디스크 여유: ext4 약 796GB, C: 약 682GB, F: 약 264GB

**확정 row count**:
- `tl_scco_ctprvn`: 17
- `tl_scco_sig`: 255
- `tl_scco_emd`: 5,067
- `tl_scco_li`: 15,161
- `tl_kodis_bas`: 34,516
- `tl_sprd_manage`: 875,221
- `tl_sprd_rw`: 1,482,679
- `tl_sprd_intrvl`: 16,993,167
- `tl_spbd_buld_polygon`: 10,687,732

**발견한 문제**:
- `TL_SPBD_BULD` natural key(`rncode_full`, `bjd_cd`, 건물구분, 본번, 부번)는 중복 polygon을 많이 가진다. 같은 natural key에 polygon이 여러 개인 경우 C4/C5가 모든 후보와 다대다 거리값을 만들며 180km급 이상치를 대량 보고했다.
- `rds_sig_cd`/`rncode_full`이 NULL인 SHP 건물 polygon이 581건 있었다. 나머지 natural-key 컬럼과 geometry는 전 건 채워졌다.
- `source_file` 컬럼은 현재 GDAL append 경로에서 전 건 NULL이다. 적재 추적성 보강 후보로 남긴다.
- 대부분 시도 `TL_SPRD_RW.shp`, 일부 `TL_SPBD_BULD.shp`/행정구역 polygon에서 GDAL ring winding order 자동 보정 경고가 반복됐다. 적재는 실패 없이 완료됐다.
- 실제 smoke test에서 `geocode` SQL의 `:si IS NULL` 선택 필터가 psycopg `AmbiguousParameter`를 일으켰다. PostgreSQL은 `IS NULL`에 먼저 등장한 바인딩 파라미터의 타입을 추론하지 못할 수 있다.

**보강 상세**:
- C4는 같은 natural key SHP polygon 후보 중 `e.geom <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 `JOIN LATERAL ... LIMIT 1`로 수정했다.
- C5는 같은 natural key SHP polygon 후보 중 `n.centroid_5179 <-> p.geom` 기준 가장 가까운 polygon 1개만 평가하도록 수정했다.
- 단위 테스트는 C4/C5가 LATERAL nearest 후보를 사용함을 확인하도록 보강했다.
- `geocode`, `zipcode`, `pobox` raw SQL의 optional filter는 `CAST(:param AS text/integer/boolean)`로 명시해 psycopg 타입 추론 실패를 막았다.

**정합성 결과**:
- 1차 재검증: 4분 59.41초, `severity_max=ERROR`
  - C4: 257,783건, `over_500m=11,649`
  - C5: 3,277,327건
- C4/C5 nearest 보강 후 2차 재검증: 6분 27.54초, `severity_max=ERROR`
  - C1 WARN: 32,531건
  - C2 ERROR: 34,699건
  - C3 WARN: 3,510,265건
  - C4 ERROR: 3,415건, `over_500m=16`, `p95=3.82m`, `p99=15.50m`
  - C5 WARN: 202건
  - C6 ERROR: 803건
  - C7 ERROR: 6,817건
  - C8 WARN: 24,471건
  - C9 OK: 0건
  - C10 OK: 0건

**검증**:
- `ruff check src/kraddr/geo/loaders/consistency.py tests/unit/test_consistency_sql.py` 통과.
- `pytest tests/unit/test_consistency_sql.py -q`는 pytest capture 임시파일 `FileNotFoundError`로 테스트 실행 전 실패.
- `pytest -s tests/unit/test_consistency_sql.py -q` → 2 passed.
- SHP 9개 테이블 `ANALYZE` → 4.14초, 성공.
- `ruff check src/kraddr/geo/infra/geocode_repo.py src/kraddr/geo/infra/zip_repo.py src/kraddr/geo/infra/pobox_repo.py tests/unit/test_infra_repo_sql.py` 통과.
- `pytest -s tests/unit/test_infra_repo_sql.py tests/unit/test_consistency_sql.py -q` → 12 passed.
- smoke test: `서울특별시 종로구 필운대로 93` geocode OK, reverse OK(10건), search 3건, zipcode OK(3건).

**다음 작업**: C4/C5 nearest 보강을 커밋·푸시하고 PR #14에 실제 전수 적재/정합성 결과를 코멘트한다. 이어서 MV/클라이언트 smoke와 전체 테스트를 가능한 범위까지 수행하고, 남은 C2/C4/C6/C7 원천 데이터 품질 항목은 후속 분석 후보로 분리한다.

## 2026-05-24 (PR #14/T-027 — 실제 SHP 적재 중 GDAL/PostGIS 스키마 보강)

**작업**: 실제 `data/juso/도로명주소 전자지도`를 Docker PostGIS에 적재하는 과정에서 SHP 로더의 GDAL 옵션, geometry 타입, full-load overwrite 전략 문제를 확인하고 보강했다.

**발견한 문제**:
- GDAL 3.8 Python binding은 `VectorTranslateOptions(openOptions=...)`를 받지 않아 SHP 적재가 `TypeError`로 중단되었다.
- `openOptions` 제거 후에는 `accessMode="overwrite"`가 운영 테이블을 원천 DBF 스키마로 재생성하면서 `tl_scco_ctprvn.geom`이 `Polygon`으로 바뀌었고, 실제 `MultiPolygon` 삽입에서 실패했다.
- `shp-all --mode full`은 17개 시도 디렉터리를 순회하는데, 각 시도마다 overwrite/full을 그대로 적용하면 앞 시도 데이터가 뒤 시도 적재 때 사라질 수 있다.
- 실제 2026년 전자지도 17개 시도 파일을 확인한 결과 `TL_SPRD_RW.shp`는 모두 `Polygon` 레이어다. 기존 `tl_sprd_rw.geom geometry(MultiLineString, 5179)` 정의와 맞지 않았다.
- 실패 후 복구를 위해 `init-db`를 다시 실행하자, 이미 대량 텍스트 데이터가 들어간 상태에서는 MV 생성이 5초 statement timeout에 걸렸고 같은 트랜잭션의 앞선 DDL까지 롤백될 수 있음을 확인했다.

**보강 상세**:
- SHP 로더는 CP949를 `gdal.config_options({"SHAPE_ENCODING": "CP949"})`로 지정한다.
- full 모드는 대상 9개 테이블을 명시적으로 `TRUNCATE`한 뒤 GDAL은 항상 기존 PostgreSQL 테이블에 `append`한다. 원천 DBF 전체 컬럼으로 운영 테이블을 재생성하지 않는다.
- `SQLStatement`는 JOIN 키와 필요한 속성 컬럼만 alias한다. OGR SQL 결과가 geometry를 유지하므로 `GEOMETRY AS geom` 같은 가짜 문자열 필드를 만들지 않는다.
- `shp-all --mode full`과 `load all-sidos --shp-root`는 첫 시도만 full, 이후 시도는 append로 바꿔 전국 적재가 누적되도록 했다.
- `tl_sprd_rw.geom`은 실제 SHP 헤더에 맞춰 `MULTIPOLYGON 5179`로 조정하고 문서도 도로면 polygon 기준으로 갱신했다.
- `init-db`는 schema/index/MV statement를 별도 트랜잭션으로 실행해 MV 경고가 schema DDL을 롤백하지 않게 했다. 경고가 있으면 개수를 출력한다.
- `refresh mv --swap`은 복구 중 기존 `mv_geocode_target`이 없어도 `mv_geocode_target_next`를 바로 운영 이름으로 승격한다. swap 후 `ANALYZE mv_geocode_target`도 수행한다.
- `scripts/fullload_test.sh`는 기본 `KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS`를 30분으로 높인다. 대량 링크 해소와 shadow MV 빌드가 운영 기본값 5초에 막히지 않도록 하기 위함이다.
- 실제 MV 빌드 후 `pt_source='centroid'`가 0건인 것을 확인했다. 원인은 내비게이션용DB의 `bd_mgt_sn`이 25자리이고 정본 `tl_juso_text.bd_mgt_sn`은 26자리라 직접 조인이 불가능한 점이었다. 또한 내비 `bjd_cd`는 리 코드가 `00`인 경우가 많아 10자리 법정동 완전 일치도 부적합했다. MV fallback을 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 대표 centroid 조인으로 변경했다.
- 두 번째 MV swap에서 `idx_mv_next_geocode_target_next_pk`가 이미 존재한다는 충돌을 확인했다. 첫 swap 때 shadow MV 인덱스명이 운영 MV에 그대로 남았기 때문이다. swap 전후에 `idx_mv_next_*` 이름을 운영명 `idx_mv_*`로 정규화하도록 보강했다. 이어 실제 재시도에서 old MV의 운영명 인덱스가 아직 있는 상태로 next 인덱스를 rename하려 하면 next 인덱스가 drop되는 것을 확인해, old MV를 먼저 drop한 뒤 next 인덱스를 rename하도록 순서를 조정했다.
- 실제 C1~C10 정합성 검증에서 C1/C2가 전량 불일치했다. `TL_SPBD_BULD.BD_MGT_SN`도 25자리이고 정본은 26자리라 건물 polygon도 직접 `bd_mgt_sn` 조인이 불가능했다. `tl_spbd_buld_polygon`에 `RDS_SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `SIG_CD`, `EMD_CD`, `LI_CD`를 함께 적재하고 C1/C2/C4/C5를 natural key 기준으로 바꿨다. C8은 `TL_SPRD_RW`에 `rds_man_no`가 없어 전량 WARN이 나므로, `TL_SPRD_MANAGE` LineString geometry를 적재해 도로 인접성 검증에 사용하도록 바꿨다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 6 passed.
- `.venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py src/kraddr/geo/cli/main.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py` → 통과.
- 실패로 오염된 SHP 보조 테이블 9개만 drop 후 `KRADDR_GEO_PG_DSN=...15432 .venv/bin/kraddr-geo init-db` 재실행. MV 생성은 timeout 경고가 났지만 SHP 테이블 스키마는 `MULTIPOLYGON 5179`로 복구됨을 확인했다.
- `세종특별자치시` 실제 SHP 9개 레이어 적재 성공: 59.09초, 최대 RSS 약 128MiB, `tl_spbd_buld_polygon` 55,819행, `tl_sprd_intrvl` 100,009행 등 9개 테이블 row count 확인.
- 전국 SHP 153개 레이어 적재 성공: 3시간 1분 34초, 최대 RSS 약 181MiB. 정확한 row count는 `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행 등으로 확인했다.

**다음 작업**: 변경분을 PR #14에 푸시하고, 같은 Docker DB에서 전국 `shp-all --mode full`을 재실행한다. 이후 pobox/bulk optional 단계, 링크 해소, MV swap, C1~C10 정합성, smoke test를 순서대로 계속 진행한다.

## 2026-05-24 (PR #14/T-027 — 실제 데이터로드 실행 중 포트 충돌 방지)

**작업**: PR #13이 main에 머지된 뒤 `codex/t027-fullload-execution` 브랜치에서 실제 데이터로드를 시작했다. WSL ext4 클론(`~/dev/python-kraddr-geo`)에서 Python/GDAL 환경을 만들고, `F:\dev\python-kraddr-geo\data` 원본을 `~/kraddr-geo-data` 작업 사본으로 복사했다.

**실행 로그**:
- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 기록한다.
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Docker Compose v5.1.4, Python 3.12.3, GDAL 3.8.4.
- `--copy-data` 시작 `2026-05-24T17:31:15+09:00`, 종료 `2026-05-24T18:35:47+09:00`, 경과 약 1시간 4분 32초.
- 복사 결과: `~/kraddr-geo-data/juso` 약 25GB, 파일 683개. `epost`는 현재 원본 파일이 없어 빈 디렉터리다.

**발견한 문제**:
- 로컬 5432 포트가 기존 `airflow-postgres-1` 컨테이너에서 이미 사용 중이었다.
- T-027 기본 compose/스크립트가 `localhost:5432`를 그대로 사용하면 기존 DB에 DDL/적재를 실행할 위험이 있다.

**보강 상세**:
- `docker-compose.yml`의 외부 포트를 `${KRADDR_GEO_DB_PORT:-5432}:5432`로 파라미터화했다.
- `scripts/fullload_test.sh`는 `KRADDR_GEO_PG_DSN`이 없을 때 `KRADDR_GEO_DB_PORT`를 반영한 DSN을 만든다.
- `docs/t027-fullload-plan.md`, `docs/dev-environment-recovery.md`, `CLAUDE.md`에 `KRADDR_GEO_DB_PORT=15432` 사용 예와 포트 충돌 주의사항을 추가했다.

**검증**:
- `bash -n scripts/fullload_test.sh` 통과.
- `DATA_DIR=/home/digitie/kraddr-geo-data KRADDR_GEO_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` 통과. 출력 DSN이 `localhost:15432`로 바뀌는 것을 확인했다.
- `git diff --check` 통과.

**다음 작업**: PR 생성 후 `KRADDR_GEO_DB_PORT=15432`로 Docker PostGIS를 기동하고 실제 적재를 계속 진행한다. 이후 발견되는 문제는 같은 PR에 누적한다.

## 2026-05-24 (PR #13/T-027 — Windows 재설치·Codex 세션 복구 문서화)

**작업**: Windows 재설치 후 `git pull`로 PR #13 작업을 문제없이 이어갈 수 있도록 복구 절차를 문서화했다. 실제 Docker 전체 적재와 `PLAN_ONLY=1` 실행은 하지 않았다.

**보강 상세**:
- `docs/windows-reinstall-recovery.md`를 추가했다. Git branch/PR을 영속 상태의 기준으로 두고, `data/`·`.env`·API 키·WSL distro·Docker volume의 백업 여부를 구분했다.
- 재설치 후 WSL/GDAL/Python 환경 복구, PR #13 브랜치 checkout, `docs/t027-fullload-plan.md` 확인, `PLAN_ONLY=1 bash scripts/fullload_test.sh` preflight 순서를 명시했다.
- Codex 레벨 복구는 repo에 넣을 내용과 로컬 세션 편의 기능을 분리했다. 문서에는 일반적인 `codex resume`, `codex fork`, `codex doctor`, `codex cloud` 확인 명령과 `CODEX_HOME`/`.codex` 백업 주의사항만 남겼다.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/dev-environment.md`, `docs/dev-environment-recovery.md`, `docs/resume.md`에서 새 복구 문서를 참조하도록 연결하고, 실제 적재는 사용자 명시 전 실행하지 않는 금지선을 맞췄다.

**다음 작업**: PR #13 리뷰 후에도 실제 전체 적재는 바로 실행하지 않는다. 먼저 문서와 스크립트 syntax 확인을 거친 뒤, 사용자가 허용하면 `PLAN_ONLY=1` preflight 결과를 PR에 공유한다.

## 2026-05-24 (PR #13/T-027 — Docker full-load 계획 보강)

**작업**: 사용자 지시에 따라 실제 Docker 전체 적재 실행은 중단하고, `F:\dev\python-kraddr-geo\data\juso` 전체를 대상으로 한 계획/문서/스크립트 preflight 보강만 진행했다. 로컬 파일 시스템은 목록과 용량만 확인했고 DB 적재·Docker 실행은 하지 않았다.

**확인한 데이터 인벤토리**:
- `data/juso` 전체는 약 28GB다.
- 현재 full-load에 바로 쓸 수 있는 자료는 `202603_도로명주소 한글_전체분`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분`, `도로명주소 전자지도`다.
- `daily/*.zip`, `jibun_rnaddrkor_*`, `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`는 현재 로더의 직접 적재 대상이 아니므로 후속 태스크로 분리했다.

**보강 상세**:
- `docs/t027-fullload-plan.md`를 실행 전 리뷰 가능한 계획서로 재작성했다. 실행 금지선, Docker project/volume 안전장치, 기준월 분리, phase별 중단·재개, 산출물 경로, 미지원 자료 후속 태스크를 명시했다.
- `scripts/fullload_test.sh`는 실행 산출물로 남기되 `PLAN_ONLY=1` preflight를 추가했다. 단일 `YYYYMM` 대신 `JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`을 분리하고, CLI 호출은 `kraddr-geo` console script로 맞췄다.
- 초안 스크립트의 DDL inline SQL 실행을 `alembic upgrade head`로 바꾸고, 별도 적재 명령 뒤 누락될 수 있는 `resolve_text_geometry_links()`를 명시적으로 수행하도록 정리했다. MV 갱신은 full-load에 맞게 `refresh mv --swap`을 기본으로 둔다.
- smoke test는 실제 DTO 구조(`GeocodeResponse.result.point`, `ReverseResponse.result`, `SearchResponse.result`, `ZipcodeResponse.result`)에 맞게 보정했다.

**검증**:
- `bash -n scripts/fullload_test.sh` → 통과. 실제 DB/Docker 적재 실행은 하지 않았다.

**다음 작업**: PR #13 리뷰 후 `PLAN_ONLY=1 bash scripts/fullload_test.sh`만 먼저 실행한다. 전체 적재는 Docker 볼륨/로그 경로/중단 기준을 확인한 뒤 별도 지시가 있을 때 진행한다.

## 2026-05-24 (PR #12 리뷰 보강 — 보안·CI·에러 처리)

**작업**: PR #12 top-level 리뷰 코멘트를 확인했다. inline review thread는 없었고, GitHub 기준 mergeable 상태라 Git 충돌은 없었다. 다만 backend CI가 `scripts.export_openapi` import 실패로 깨졌고, 리뷰의 C/H/M 항목과 추가 코멘트의 프록시 스트리밍 항목을 모두 코드로 반영했다.

**구현 상세**:
- C1/C2: `/v1/admin/upload/sido-zip`에서 `sido`와 `filename`을 path token으로 정규화하고, resolved path가 `loader_data_dir/uploads` 밖으로 나가면 `InvalidInputError(E0100)`로 거절한다. `api_max_upload_bytes`(기본 2GiB)를 추가해 초과 업로드는 partial file 삭제 후 실패시킨다.
- H1/L1: Next.js 프록시는 `new URL()` 정규화 이후 `/v1/` 하위 경로만 허용하고, 전달 헤더를 `accept`/`content-type`/`user-agent`로 제한한다.
- 추가 코멘트: Next.js 프록시는 더 이상 `request.arrayBuffer()`로 업로드 본문 전체를 메모리에 올리지 않는다. GET/HEAD 외 요청은 `request.body` `ReadableStream`을 그대로 넘기고 Node.js fetch 요건에 맞춰 `duplex: "half"`를 설정한다.
- H2: `ApiError`를 추가해 HTTP status를 보존하고, React Query retry가 4xx를 재시도하지 않게 했다.
- H3: `/v1/admin/explain`은 실행 전 `set_config('statement_timeout', ..., true)`를 호출한다. 기본 timeout은 `api_explain_timeout_ms=3000`.
- M1~M3/L2/L3: `LoadConsole`, `ReverseDebugger`, `ConsistencyPanel` 에러 처리를 보강하고 빈 jobs 배열 finished 전이를 막았다.
- M4: Prometheus gauge 이름을 `kraddr_geo_cache_hits_total`에서 `kraddr_geo_cache_hits`로 변경했다.
- M5: `ExplainDebugger`가 `explainFormSchema`를 사용해 SELECT/WITH와 세미콜론 금지를 클라이언트에서도 검증한다.
- CI: `scripts/__init__.py`를 추가하고 pytest `pythonpath`에 repository root를 명시해 GitHub Actions의 pytest 수집 환경에서도 `scripts.export_openapi` import가 안정적으로 동작하게 했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 70 passed, 1 skipped
- 임시 DB `kraddr_geo_codex_pr12_review`에서 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed
- `cd kraddr-geo-ui && npm run lint && npm run type-check && npm run test && npm run build` → 통과, Vitest 12 passed
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과, moderate advisory만 잔여

**다음 작업**: PR #12 CI 재확인과 리뷰어 코멘트 답변.

## 2026-05-23 (PR #12 — T-021~T-026 프론트엔드·관측·CI 구현)

**작업**: PR #11을 main에 머지한 뒤, PR #11 후속 의견을 PR #12로 이관했다. PR #12 범위는 T-018~T-020이 main에 이미 포함된 상태에서 T-021~T-026을 실제 코드와 테스트로 마무리하는 것이다.

**구현 상세**:
- T-021: `kraddr-geo-ui` 패키지를 추가했다. Next.js 16(App Router), React 18, Tailwind, TanStack Query, `react-kakao-maps-sdk`, OpenAPI 타입 생성 스크립트(`npm run gen:types`)를 포함한다.
- T-022: `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 페이지를 구현했다. 모든 요청은 `/api/proxy/[...path]` Route Handler를 통해 백엔드 `/v1/*`로 전달한다. Kakao JS key가 없으면 지도는 좌표 프리뷰로 fallback한다.
- T-023: `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs` 페이지를 구현했다. full-load batch payload 등록, raw ZIP 업로드, MV refresh enqueue, 테이블 통계, 캐시 메트릭, `load_jobs.log_tail` 조회를 확인할 수 있다.
- T-024: 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가했다. backend lint/type/import/test와 frontend type generation drift/lint/type/test/build를 분리된 job으로 검증한다.
- T-025: `infra/metrics.py`와 `/metrics` endpoint를 추가했다. 외부 API 호출 결과, cache entries/hits/expired, load job kind/state 분포를 Prometheus 포맷으로 노출한다.
- T-026: `/admin/consistency` 페이지를 추가했다. C1~C10 report 목록, 상세 case grid, 원본 JSON, 재검증 enqueue를 제공한다.
- FastAPI admin 라우터와 `AsyncAddressClient`에 `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv` 표면을 연결했다.

**결정**:
- ADR-019를 추가했다. 신규 프론트엔드는 Next.js 14가 아니라 Next.js 16을 보안 하한선으로 둔다. `npm audit --omit=dev --audit-level=high`가 통과해야 한다.
- `/v1/admin/upload/sido-zip`은 `python-multipart` 의존을 피하기 위해 multipart가 아닌 raw request body stream + query `filename` 형태로 구현했다. Next.js 프록시는 body를 `arrayBuffer()`로 읽어 그대로 전달한다.
- `ruff format --check`는 기존 파일 포맷 churn이 커서 PR #12 CI 범위에서 제외했다. 이번 PR은 `ruff check`, `mypy`, `lint-imports`, `pytest`를 품질 게이트로 삼는다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`
- `KRADDR_GEO_TEST_PG_DSN=... .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` — 실제 `data/juso` 샘플 COPY와 MV 생성 검증
- `cd kraddr-geo-ui && npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build`
- `cd kraddr-geo-ui && npm audit --omit=dev --audit-level=high`

**다음 작업**: PR #12 리뷰 대기. 후속 후보는 `/admin/load` 업로드 진행률(XHR progress), `/admin/logs` streaming tail, `/debug/reverse` 지도 클릭 즉시 조회 UX다.

## 2026-05-23 (PR #11 follow-up — batch payload fail-fast 검증)

**작업**: PR #11 후속 확인 결과 GitHub review thread/comment는 없었지만, 원격 브랜치에 `AsyncAddressClient.submit_load("full_load_batch", ...)`를 `insert_load_batch`로 라우팅하는 보강 커밋이 추가되어 있었다. 해당 방향은 REST와 라이브러리 표면을 일치시키므로 타당하다고 판단했고, 그 위에 잘못된 batch payload가 `load_jobs`에 root + 빈 child를 먼저 남기는 문제를 추가로 막았다.

**구현 상세**:
- `infra.batch.batch_children()`에서 enqueue 전 payload 검증을 수행한다. 기본 `payloads` 경로는 ADR-017 source child 5종(`juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`) 모두에 `path` 또는 `source_path`가 있어야 한다.
- 명시 `children`/`child_jobs` 배열은 더 이상 잘못된 entry를 조용히 버리지 않는다. entry object, non-empty `kind`, object `payload`를 요구하고, 경로 기반 로더(`bulk_load` 포함)는 `path`/`source_path`가 없으면 `InvalidInputError(E0100)`를 던진다.
- `AsyncAddressClient.submit_load("full_load_batch", ...)`는 검증 실패 시 `AdminRepository.insert_load_batch`와 `insert_load_job` 어느 쪽도 호출하지 않으므로, 불완전한 batch root가 DB에 영속되지 않는다.
- `docs/backend-package.md`에 `full_load_batch` payload 예시와 검증 정책을 자세히 추가했다. REST와 라이브러리 표면이 같은 helper를 공유한다는 점을 명시했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_infra_batch.py tests/unit/test_client_submit_load_batch.py -q` → 14 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 65 passed, 1 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- 임시 DB `kraddr_geo_codex_pr11_followup`에서 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` 실행 → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed.

**다음 작업**: PR #11에 후속 의견과 검증 결과를 남긴 뒤, 리뷰어가 원하면 payload schema를 OpenAPI DTO 수준에서 더 좁히는 작업을 별도 PR로 분리한다.

## 2026-05-23 (PR #11 리뷰 fixup — 라이브러리 batch DAG 비대칭 해소)

**작업**: PR #11 리뷰에서 발견된 라이브러리/REST 비대칭 이슈를 해결했다. `AsyncAddressClient.submit_load("full_load_batch", ...)`가 `AdminRepository.insert_load_job`을 직접 호출하던 경로를 `insert_load_batch`로 라우팅하여, 라이브러리 사용자도 REST `/v1/admin/loads`와 동일하게 root + 5종 child + DAG가 즉시 적재되도록 한다.

**구현 상세**:
- `src/kraddr/geo/infra/batch.py` 신규 모듈에 `BATCH_SOURCE_KINDS`와 `batch_children()`을 이동했다. `api/_jobs.py`의 동명 private 헬퍼는 제거하고 새 모듈을 import한다.
- `AsyncAddressClient.submit_load`는 `kind == "full_load_batch"`일 때 `batch_children(payload)`로 child 구성을 결정해 `AdminRepository.insert_load_batch`를 호출한다. 비-batch kind는 종전대로 `insert_load_job`을 사용한다.
- `infra/batch.py`는 `core/dto` 의존 없는 순수 모듈이라 client / api / loaders 어느 레이어에서도 import 가능. import-linter "Layered architecture" 컨트랙트 유지.

**검증**:
- `tests/unit/test_infra_batch.py` 신규 — default kind 순서, `payloads` 매핑 키, 명시 `children` 우선, 잘못된 entry drop을 검증.
- `tests/unit/test_client_submit_load_batch.py` 신규 — `AsyncMock`으로 `insert_load_batch` / `insert_load_job` 호출 분기를 검증.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest tests/unit/ -q` → 51 passed.
- `python -m ruff check`, `mypy --strict src/kraddr/geo/api/_jobs.py src/kraddr/geo/infra/batch.py src/kraddr/geo/client.py`, `lint-imports` 모두 통과.
- `python scripts/export_openapi.py --check` → drift 없음 (DTO 변경 없음).

**다음 작업**: T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩.

## 2026-05-23 (codex, T-018~T-020 구현 + 신규 PR 준비)

**작업**: PR #10 리뷰 fixup 위에서 T-018~T-020을 추가 구현하고, 사용자 요청대로 P1/P2 리뷰 반영 사항과 T-005~T-020 완료 범위를 하나의 신규 PR로 등록할 준비를 진행했다.

**구현 상세**:
- T-018: CLI 운영 명령을 확장했다. `kraddr-geo load all-sidos`는 juso/locsum/navi 필수 경로와 선택 SHP/epost 보조 경로를 받아 직접 적재 → 링크 해소 → C1~C10 정합성 검증 → optional MV refresh까지 묶는다. `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`도 추가했다.
- T-019: `infra/external_api.py`를 추가했다. `AsyncAddressClient.geocode(..., fallback="api")`는 로컬 DB 결과가 `NOT_FOUND`일 때만 외부 폴백을 호출한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 API + 좌표 API다. 외부 응답은 기존 `GeocodeResponse`로 변환하며 공급자 출처는 `x_extension.source`에만 둔다.
- T-020: `scripts/export_openapi.py`를 추가해 `create_app().openapi()`를 `openapi.json`으로 내보낸다. `--check` 모드는 committed schema와 생성 결과가 다르면 실패한다. `.github/workflows/openapi.yml`은 PR마다 `.[api]` extra 설치 후 drift 검사를 실행한다.

**문서**:
- `docs/tasks.md`에서 T-018~T-020을 완료로 이동했다.
- `docs/resume.md`의 다음 작업을 T-021 프론트엔드 부트스트랩으로 갱신했다.
- `docs/backend-package.md`에 외부 API fallback 흐름과 OpenAPI export/CI drift 절차를 명시했다.
- `docs/external-apis.md`에 구현 위치, 호출 순서, 응답 매핑 정책을 보강했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 51 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN` 미설정 시 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_t020_verify' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kraddr_geo_codex_t020_verify` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → 통과

## 2026-05-23 (codex, PR #10 리뷰 코멘트 반영)

**작업**: PR #10 상위 리뷰 코멘트의 P1/P2 항목을 반영했다. P1은 ADR-017 batch DAG, C1~C10 정합성 검증, PNU NULL guard이고, P2는 reverse `both`, 텍스트 인코딩 fallback, `load_jobs` 진행률/log_tail, `x_extension` ADR 문서화를 중심으로 처리했다.

**주요 변경**:
- `load_jobs`에 `load_batch_id`, `parent_job_id`를 추가하고 `full_load_batch` root job 아래 source load child 5종 → `consistency_check` → `mv_refresh(strategy='swap')` 순서로 이어지는 batch DAG를 구현했다.
- `JobQueue` handler 시그니처를 `(payload, cancel_event, progress_cb)`로 확장했다. `progress_cb`는 `progress`, `current_stage`, `heartbeat_at`, `log_tail`을 DB에 갱신한다.
- FastAPI lifespan에서 기본 handler를 등록한다. `juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`, `consistency_check`, `mv_refresh`가 큐에서 실제 실행된다.
- `loaders/consistency.py`를 C1~C10 전체 케이스로 확장했다. 각 케이스는 `count`, `ratio`, `threshold`, `metric`, `sample`을 채운다. C4/C6/C7/C9는 `ERROR` 판정 근거가 명시되어 batch swap gate로 쓸 수 있다.
- `tl_juso_text.pnu` generated column에 `mntn_yn IS NULL` 가드를 추가했다. 실제 `rnaddrkor_seoul.txt` 524,678건은 `bd_mgt_sn` 길이가 모두 26자리였으므로, 체크 제약은 `BETWEEN 25 AND 26`으로 좁혔다.
- reverse `type="both"`가 도로명과 지번 결과를 모두 반환하도록 보정했다.
- 텍스트 인코딩 감지는 BOM → CP949 검증 → UTF-8 검증 순서로 바꿨다.
- ADR-017(batch DAG)과 ADR-018(`x_extension` 스키마 격리)을 `docs/decisions.md`에 추가했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 47 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_pr10_fix' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kraddr_geo_codex_pr10_fix` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept

**다음**: PR #10에 반영 요약과 검증 결과를 코멘트로 남긴다.

## 2026-05-23 (codex, T-005~T-017 일괄 구현 + 실제 파일/DB 검증)

**작업**: PR #7이 닫힌 뒤 최신 `origin/main`(`fa276dd`)에서 새 브랜치 `codex/t017-text-primary-load`를 만들고, ADR-012/ADR-016 기준으로 T-005부터 T-017까지 백엔드 1차 구현을 진행했다. 사용자의 추가 지시대로 `data/juso` 실제 파일을 반드시 열어 검증했고, 로컬 PostGIS에 별도 테스트 DB를 만들어 실제 샘플 COPY 적재와 MV 생성까지 확인했다.

**변경 파일(주요)**:
- 신규: `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_text_primary_postgis_schema.py`
- 신규: `src/kraddr/geo/infra/engine.py`, `infra/sql.py`, `infra/pnu.py`, `infra/geocode_repo.py`, `infra/reverse_repo.py`, `infra/search_repo.py`, `infra/zip_repo.py`, `infra/pobox_repo.py`, `infra/admin_repo.py`
- 신규: `src/kraddr/geo/core/protocols.py`, `core/normalize.py`, `core/geocoder.py`, `core/reverse_geocoder.py`, `core/searcher.py`, `core/zipcoder.py`, `core/poboxer.py`, `core/responses.py`
- 갱신: `src/kraddr/geo/client.py`, `src/kraddr/geo/__init__.py`, `src/kraddr/geo/dto/admin.py`, `src/kraddr/geo/cli/main.py`
- 신규: `src/kraddr/geo/api/app.py`, `api/_jobs.py`, `api/deps.py`, `api/responses.py`, `api/routers/*`
- 신규: `src/kraddr/geo/loaders/text/juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`, `loaders/shp/polygons_loader.py`, `shp/delta_loader.py`, `loaders/postload.py`, `loaders/consistency.py`, `loaders/pobox_loader.py`, `loaders/bulk_loader.py`, `loaders/manifest.py`
- 신규 테스트: `tests/unit/test_infra_engine_pnu_sql.py`, `test_core_geocoder.py`, `test_infra_repo_sql.py`, `test_api_app_contract.py`, `tests/integration/test_real_juso_text_loaders.py`, `test_optional_real_postgres_load.py`
- 갱신 문서: `docs/tasks.md`, `docs/resume.md`, `docs/data-model.md`, `docs/backend-package.md`, `CHANGELOG.md`

**구현 상세**:
- T-005: `make_async_engine()`은 `Settings.pg_dsn` 보정을 신뢰하고, statement timeout과 `search_path=public,x_extension`를 연결 옵션에 넣는다. PostGIS/pg_trgm/unaccent는 `x_extension` 스키마에 설치한다.
- T-006/T-007: DDL은 텍스트 4 + SHP polygon/폴리라인 9 + 우편번호 보조 2 + 메타 5 = 20개 테이블을 만든다. `mv_geocode_target`은 `pt_5179`, `pt_4326`, `pt_source`를 노출하고 `pt_5179 IS NOT NULL` partial GiST index를 둔다. `tl_juso_text.pnu`는 `COALESCE(lnbr_mnnm, 0)` 없이 필수 필드 결측 시 `NULL`을 반환한다.
- T-008~T-010: 주소 정규화(`parse_address`)와 geocode core/repo를 구현했다. 도로명 fuzzy는 트랜잭션 안에서만 `SET LOCAL pg_trgm.similarity_threshold`를 사용한다.
- T-011/T-016: `AsyncAddressClient`가 실제 raw SQL repo를 연결해 geocode/reverse/search/zipcode/pobox를 호출한다. load job과 consistency report 조회/등록/취소 표면도 추가했다.
- T-012/T-015: FastAPI 앱과 `/v1/address/*`, `/v1/admin/loads`, `/v1/admin/consistency/*` 라우터를 추가했다. `JobQueue`는 DB `load_jobs`를 기준으로 상태를 영속화하고 startup에서 잔존 `running`을 `failed` 처리한다. 실행 직전 `pg_try_advisory_xact_lock` + `FOR UPDATE SKIP LOCKED`로 다중 워커 중복 실행을 막는다.
- T-013a~c: 텍스트 로더는 실제 파일 기반 인덱스를 박아 `psycopg.copy()`로 적재한다. 위치정보요약DB 실제 ZIP은 `bd_mgt_sn`을 직접 제공하지 않으므로 natural key를 보관하고 후처리에서 `tl_juso_text`와 조인해 해소한다. 일부 위치정보요약DB 행은 X/Y가 비어 있어 `geom NOT NULL` 적재에서 제외한다.
- T-013d/T-014: SHP 보조 로더는 ADR-012 대상 9개 레이어만 load plan으로 만들며, GDAL Python binding은 실제 호출 시에만 import한다. delta merge는 `settings.mvm_res_code_actions` 또는 DB `load_codes`에서 온 action map을 받도록 설계했다.
- T-017: epost 보조 우편번호용 `postal_pobox`, `postal_bulk_delivery` COPY 로더를 추가했다.

**실제 파일 검증**:
- `data/juso/202603_도로명주소 한글_전체분/rnaddrkor_seoul.txt` 첫 25행을 실제 CP949로 읽어 `bd_mgt_sn`, `rncode_full`, 건물번호, 우편번호, PNU 매핑을 검증했다.
- `data/juso/202604_위치정보요약DB_전체분.zip`의 `entrc_seoul.txt` ZIP member를 직접 스트리밍해 `sig_cd`, `ent_man_no`, `rncode_full`, `ent_se_cd`, EPSG:5179 X/Y를 검증했다.
- `data/juso/202604_내비게이션용DB_전체분/match_build_seoul.txt`와 `match_rs_entrc.txt`를 읽어 centroid/진입점 좌표와 kind 매핑을 검증했다.
- `data/juso/도로명주소 전자지도/강원특별자치도`의 SHP/DBF 파일로 ADR-012 보조 9개 레이어 load plan을 검증했다.
- 로컬 PostgreSQL(PostGIS)에서 `kraddr_geo_codex_t017` 테스트 DB를 생성해 DDL 적용 → 실제 파일 샘플 COPY 적재 → `resolve_text_geometry_links()` → `mv_geocode_target` 생성까지 통과 확인 후 DB를 삭제했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 43 passed, 1 skipped. skipped 1건은 `KRADDR_GEO_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KRADDR_GEO_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kraddr_geo_codex_t017' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**:
- T-018 CLI를 운영 워크플로 수준으로 완성한다. 이번 작업에서 `load juso/locsum/navi`, `refresh mv`, `validate consistency`, `jobs` 기본 명령은 추가했지만 `load all-sidos`, `load shp-all`, `load epost`, 업로드 batch CLI는 후속이다.
- T-020 OpenAPI export 전에 FastAPI optional extra가 설치되지 않은 환경의 import 실패 정책을 정리한다.

---

## 2026-05-23 (claude, 텍스트 정본 + SHP polygon 하이브리드 전환)

**작업**: ADR-005를 부분 supersede하고 ADR-012(텍스트 정본 1차 + SHP polygon 보조 하이브리드), ADR-016(적재 진행도/정합성 API), ADR-007 복원·재정의를 묶어 사양 단계에서 전환. 사용자 지시: NTFS의 `data/juso` 텍스트 자료 3종(도로명주소 한글_전체분, 위치정보요약DB_전체분, 내비게이션용DB_전체분) 활용으로 완성도 ↑.

**변경 파일**:
- `docs/decisions.md` — ADR-005에 partial supersede 표시 / ADR-007 복원(위치정보요약DB ent_se_cd 기반) / ADR-012 신규 / ADR-016 신규
- `docs/data-model.md` — 마스터 14개 구조로 전면 재작성. 텍스트 1차 4종(`tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc`)과 SHP polygon 7종으로 분리. 텍스트 파일 포맷·컬럼 매핑 명시. MV 정의를 텍스트 정본 + 대표 출입구 + centroid fallback + `pt_source` 컬럼으로 재정의. 정합성 케이스 C1~C10 분류표와 `load_consistency_reports` 테이블 추가.
- `docs/backend-package.md` §9 — `loaders/text/`, `loaders/shp/`, `loaders/consistency.py` 분리. `juso_hangul_loader.py` 구현 예시(stdlib csv + `psycopg.copy()`, 인코딩 감지, 진행률 callback). `tl_spbd_buld_polygon` 분리 적재 전략. §9.8(진행도 API), §9.9(정합성 API), §9.10(로그/리포트 정책) 신규.
- `docs/backend-package.md` §10 CLI — `kraddr-geo load juso/locsum/navi/shp`, `kraddr-geo validate consistency`, `kraddr-geo jobs list/status/cancel` 추가.
- `docs/tasks.md` — T-006(18개 테이블), T-007(MV 재정의), T-011(`AsyncAddressClient` 진행도 API), T-013을 T-013a~d로 분할. T-026(정합성 검증) 신규.
- `docs/resume.md` — ADR 확인 목록 갱신 (~ADR-016).
- `CHANGELOG.md` — 정책 전환 기록.

**결정**:
- ADR-012: 적재는 행안부 텍스트 정본 1차 + SHP polygon 보조 하이브리드. GDAL은 polygon 적재에만 사용. ADR-005의 GDAL Python binding 결정은 partial supersede.
- ADR-007 재정의: 대표 출입구 선택은 위치정보요약DB의 `ent_se_cd='0'` 기반. 출입구가 0개인 건물은 내비게이션용DB centroid fallback (MV의 `pt_source` 컬럼으로 출처 노출).
- ADR-016: 적재 진행도(`load_status`/`list_load_jobs`/`submit_load`/`cancel_load`)와 정합성 리포트(`run_consistency_check`/`consistency_report`)를 라이브러리·REST·디버그 UI에 일급으로 노출. C1~C10 케이스를 `load_consistency_reports` JSONB로 영속화.
- MV `mv_geocode_target` 컬럼명: `ent_pt_5179` → `pt_5179`, `ent_pt_4326` → `pt_4326` + `pt_source ∈ {entrance, centroid}` 추가.
- PNU 매핑(`mntn_yn 0→1, 1→2`, ADR-010)을 `tl_juso_text.pnu` generated stored column으로 박음.

**검증**: 문서 전용 변경. T-013a~T-013d(텍스트/SHP 분리 로더), T-026(정합성) 구현 시 reference.

**다음**: T-005 (`infra/engine.py`). 이후 T-006(DDL)부터 ADR-012의 14개 테이블 구조로 진행.

---

## 2026-05-23 (claude, 사양 리뷰 종합 반영)

**작업**: 두 차례 리뷰 의견(v1 기반 5건 + master 기반 5건)에 사용자 보완을 더해 사양 단계에서 미리 묶어 반영.

**변경 파일**:
- `SKILL.md` — §4 DO NOT 11~13 추가: (11) 공간 술어 형변환 금지·반경은 5179 meter, (12) bulk param 한도, (13) 작업 큐 영속화.
- `docs/data-model.md` — MV에 `idx_mv_geom5179` 추가 / "MV 갱신 모드" 절 (평시 CONCURRENTLY vs 분기 shadow MV swap, lock_timeout/인덱스 이름/권한/prepared statement invalidation 주의) / "공간 쿼리 가이드" (5179 meter 기준 CTE 예시, ent_pt_4326 응답 전용) / 행정 polygon 4326 변환 view (`v_kodis_bas_4326`, `v_scco_emd_4326`) / "PNU 조립" (mntn_yn 0/1 → 1/2, infra/generated column 위치) / "MVM_RES_CD 한 배치당 PK 단일화 가정" + 깨질 시 dedup CTE.
- `docs/architecture.md` — "적재 ↔ 서빙 단일 스키마 + MV" 강조 절.
- `docs/backend-package.md` §7.1 — engine factory DSN 보정 제거, settings.pg_dsn 신뢰. §9.7 — `load_jobs` 영속 테이블, lifespan recovery, advisory lock + FOR UPDATE SKIP LOCKED 패턴.
- `docs/decisions.md` — ADR-010(PNU 매핑 + 조립 위치 infra), ADR-011(작업 큐 `load_jobs` 영속화 + 다중 워커 안전성).
- `docs/tasks.md` — T-006/T-007/T-015에 본 ADR 인용.
- `docs/resume.md` — ADR 확인 목록 갱신.
- `CHANGELOG.md` — 정책 변경 기록.

**결정**:
- ADR-010: PNU 11번째 자리 매핑은 `0→1, 1→2`. 조립은 `infra/`(또는 generated stored column). `core/`는 의미론적 `mntn_yn`만 보관.
- ADR-011: `load_jobs` 별도 테이블에 작업 상태 영속화. lifespan startup에서 잔존 running→failed, queued는 payload 존재 여부에 따라 재큐잉/failed. 다중 워커 안전성은 `pg_try_advisory_lock` + `FOR UPDATE SKIP LOCKED`.
- 공간 쿼리: 반경/nearest는 5179(meter) 기준, 4326은 응답 전용. 술어 안에 `ST_Transform(t.geom, ...)` 금지.
- MV 갱신: 평시 CONCURRENTLY, 분기 풀로드는 shadow MV + RENAME swap (lock_timeout, prepared plan invalidation 명시).

**참고**: 본 변경은 모두 문서/사양 보강이며 코드 변경 없음. T-006/T-007/T-013/T-015 진행 시 본 ADR과 가이드를 reference로 적용.

**다음**: T-005 (`infra/engine.py`). 사양상 settings.pg_dsn을 그대로 신뢰하므로 구현 비용이 줄어듦.

---

## 2026-05-23 (codex, T-004 + 실제 SHP/DBF 검사)

**작업**: T-004 DTO 6종 구현 및 `data/juso/도로명주소 전자지도` 실제 파일 읽기 테스트 추가

**변경 파일**:
- 신규: `src/kraddr/geo/dto/geocode.py`, `src/kraddr/geo/dto/reverse.py`, `src/kraddr/geo/dto/search.py`, `src/kraddr/geo/dto/zipcode.py`, `src/kraddr/geo/dto/pobox.py`, `src/kraddr/geo/dto/admin.py`
- 신규: `src/kraddr/geo/loaders/juso_map.py`
- 신규: `tests/unit/test_dto_geocode.py`, `tests/unit/test_dto_reverse.py`, `tests/unit/test_dto_search_zipcode_pobox_admin.py`
- 신규: `tests/integration/test_juso_map_files.py`
- 갱신: `src/kraddr/geo/dto/__init__.py`, `pyproject.toml`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`

**결정**:
- DTO는 `docs/backend-package.md` §4의 wire contract를 우선해 pydantic v2 frozen model로 작성했다.
- `type` 필드는 vworld/API wire field이므로 DTO 파일별로 `A003` ruff ignore를 한정 적용했다.
- pydantic runtime이 nested DTO 타입을 해석해야 하므로 `GeocodeResponse`, `ReverseResultItem`, `SearchResultItem`의 address DTO imports는 runtime import로 유지하고 해당 파일에만 `TC001` ignore를 한정 적용했다.
- GDAL 적재 구현은 T-013 범위로 남긴다. 다만 이번 작업에서 순수 Python으로 SHP/DBF 헤더를 직접 열어 `강원특별자치도/51000`의 11개 마스터 레이어와 `TL_SPBD_BULD` 필드(`BD_MGT_SN`, `BULD_MNNM`, `MVM_RES_CD`, `RN_CD`, `SIG_CD` 등)를 검증했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 28 passed. 실제 파일 경로 `data/juso/도로명주소 전자지도/강원특별자치도/51000/*.shp|*.dbf|*.shx`를 열어 검사함.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**: T-005 — `infra/engine.py` async engine factory + 통합 테스트 준비.

---

## 2026-05-23 (claude, epost 데이터셋 정책)

**작업**: 우편번호 외부 API 활용 정책을 ADR-009로 확정하고 관련 문서 보강.

**변경 파일**:
- `docs/decisions.md` — ADR-009 추가 (epost 15000302, `downloadKnd=1` 분기 1회 전체 적재. 실시간 lookup 15056971 미도입).
- `docs/external-apis.md` — epost 절 보강: 데이터셋 ID 15000302, `downloadKnd` 4종 표, 분기 1회 전체 적재 흐름, 미도입 API(15056971) 명시. 한눈에 표에도 데이터셋 ID + ADR 인용.
- `docs/data-model.md` — `postal_pobox`/`postal_bulk_delivery` 위에 epost 15000302 ZIP 적재 출처와 ADR-009 인용.
- `.env.example` — `KRADDR_GEO_EPOST_API_KEY` 위 주석에 데이터셋 ID + ADR-009 표기.
- `CHANGELOG.md` — `### Added`에 ADR-009 요약.

**결정**:
- ADR-009: 우편번호 매칭은 epost 데이터셋 15000302의 전체 ZIP(`downloadKnd=1`)을 **분기 1회** 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE → INSERT. 변경분 누적 미운영. 실시간 lookup API(데이터셋 15056971) 미도입.

**검증**:
- 본 실행 환경(원격 컨테이너)은 `openapi.epost.go.kr` 외부망이 차단되어 직접 호출은 못 했다. 데이터셋 ID와 `downloadKnd` 4종 정의는 공공데이터포털 검색 결과로 확정. 사용자 WSL 환경에서 키 재발급 후 `curl ... -G --data-urlencode "downloadKnd=1"`로 응답을 마지막 점검 권장.
- 사용자가 채팅에 노출한 서비스 키는 즉시 재발급(또는 활용중지) 권장. 본 PR/문서/`.env.example`에 평문 커밋 없음.

**다음**: T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 시 본 ADR을 reference로 적용. CLI에 `kraddr-geo load epost --kind=full` 같은 entry를 두고 운영은 systemd timer로 분기 트리거.

---

## 2026-05-23 (claude, GDAL 셋업 문서)

**작업**: PR #3 마무리 — GDAL 시스템 의존성을 문서로 못박는다.

**변경 파일**:
- 신규: `docs/dev-environment.md` (WSL ext4 기준 셋업, conda/Docker 대안)
- 갱신: `docs/geocoding-readiness.md` (체크리스트 0번 항목 — 시스템 GDAL 설치)
- 갱신: `docs/resume.md` ("알려진 함정"에 GDAL 버전 미스매치, `libgdal-dev` 누락)
- 갱신: `SKILL.md` §2 (빠른 시작에 `apt install libgdal-dev` + `gdal==$(gdal-config --version)` 핀 추가)
- 갱신: `pyproject.toml` (`loaders` extra 위 주석 — 시스템 의존성/Docker 권장)
- 갱신: `docs/decisions.md` (ADR-008 — 시스템 GDAL과 동일 버전 핀)

**결정**:
- ADR-008: `loaders` extra는 `pip install "gdal==$(gdal-config --version)"`로 시스템과 동일 버전 핀. 운영·CI는 `osgeo/gdal:*` Docker 베이스 표준화. ADR-005 보강.

**검증**: 문서 전용 변경이라 코드 테스트 영향 없음. T-013 진행 시 실제 GDAL 환경에서 `dev-environment.md` 절차로 재현 가능.

**다음**: T-004 (DTO 6종).

---

## 2026-05-23 (codex, 리뷰 3차 반영)

**작업**: PR 리뷰 반영 — 설정 싱글톤 helper 역할 분리

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `tests/unit/test_settings.py`, `docs/backend-package.md`

**결정**:
- `reset_settings()`는 인자 없이 싱글톤을 비우는 역할만 맡는다.
- 테스트나 명시 주입이 필요할 때는 `set_settings(settings)`를 사용한다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex, 리뷰 2차 반영)

**작업**: PR 리뷰 항목 5~10 반영 — DTO 필수성, validator 범위, CLI exit, ruff ignore, 예외명, namespace package 정리

**변경 파일**:
- 갱신: `src/kraddr/geo/dto/address.py`, `src/kraddr/geo/cli/main.py`, `src/kraddr/geo/exceptions.py`, `pyproject.toml`
- 갱신: `tests/unit/test_dto_address.py`, `tests/unit/test_exceptions.py`
- 갱신: `docs/backend-package.md`, `docs/decisions.md`
- 삭제: `src/kraddr/__init__.py`

**결정**:
- `RefinedAddress.structure`는 사양대로 필수 `AddressStructure`로 둔다.
- 빈 문자열 → `None` 변환 validator는 optional address fields에만 적용하고, `level0`은 빈 문자열을 명시적으로 거부한다.
- `typer.Exit`는 인스턴스(`raise typer.Exit()`)로 raise한다.
- `N815` ruff ignore는 vworld 호환 필드가 있는 `dto/address.py`에만 한정한다.
- base 예외명은 `KraddrGeoError`로 확정한다(ADR-014).
- `kraddr` parent는 PEP 420 implicit namespace package로 둔다(ADR-015).

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex)

**작업**: PR 리뷰 반영 — 설정 기본값을 사양과 맞추고 README에 법적·데이터 사용 한계 추가

**변경 파일**:
- 갱신: `src/kraddr/geo/settings.py`, `.env.example`, `tests/unit/test_settings.py`, `README.md`

**결정**:
- `epost_download_url` 기본값은 브라우저 다운로드 페이지가 아니라 공공데이터포털 OpenAPI endpoint(`http://openapi.epost.go.kr/postal/downloadAreaCodeService/downloadAreaCodeService/getAreaCodeInfo`)로 둔다.
- `pg_statement_timeout_ms` 기본값은 사양값 5초(`5000`)로 둔다. 별도 ADR 없이 사양에 맞춘다.
- `api_default_radius_m` 기본값은 역지오코딩 hit rate를 위해 사양값 `200`으로 둔다.
- `api_cors_origins` 기본값은 빈 tuple로 둔다. localhost 허용은 `.env` override에서만 명시한다.
- README에 MIT 라이선스가 코드/문서에만 적용되고 외부 데이터/API 응답은 각 제공처 약관을 따른다는 한계를 명시했다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-22 (codex)

**작업**: T-001~T-003 구현 — Python 패키지 스캐폴드, 설정, 공통/주소 DTO와 단위 테스트 추가

**변경 파일**:
- 신규: `pyproject.toml`, `.env.example`
- 신규: `src/kraddr/__init__.py`, `src/kraddr/geo/__init__.py`, `src/kraddr/geo/version.py`, `src/kraddr/geo/py.typed`
- 신규: `src/kraddr/geo/settings.py`, `src/kraddr/geo/exceptions.py`, `src/kraddr/geo/client.py`, `src/kraddr/geo/cli/main.py`
- 신규: `src/kraddr/geo/dto/common.py`, `src/kraddr/geo/dto/address.py`
- 신규: `tests/unit/test_settings.py`, `tests/unit/test_dto_common.py`, `tests/unit/test_dto_address.py`
- 갱신: `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`

**결정**:
- import-linter는 도구 제약상 `root_package = "kraddr"`와 `containers = ["kraddr.geo"]` 조합으로 설정한다. 이는 문서의 `kraddr.geo` 계층 계약과 같은 의미이며 실제 도구 실행이 통과하는 형태다.
- `AsyncAddressClient`와 CLI는 이번 범위에서 import/install 검증을 위한 자리표시자로만 둔다. 실제 지오코딩 기능은 T-010/T-011에서 구현한다.
- 사용자가 지정한 SHP 기준 경로 `data/juso/도로명주소 전자지도`를 확인했다. 강원도 샘플의 11개 DBF 필드는 문서의 마스터 레이어(`TL_SPBD_BULD`, `TL_SPBD_ENTRC`, `TL_SPRD_MANAGE` 등)와 맞는다.

**검증**:
- `pip install -e ".[dev]"` 통과
- `pip install -e ".[api,dev]"` 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 10 passed
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kraddr/geo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**참고**:
- 현재 작업 디렉토리가 `/mnt/f` NTFS 위라 문서의 WSL/NTFS 경고가 그대로 적용된다. 기본 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 시작 전 실패하므로 검증 시 Linux `/tmp`를 명시했다.
- `loaders` extra는 현재 환경에 `gdal-config`가 없어 설치 검증하지 않았다. T-013에서 GDAL Python binding 설치 환경과 함께 별도 검증한다.

**다음**: T-004 — 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`)와 단위 테스트 작성.

---

## 2026-05-22 (human, 추가 명시)

**작업**: 사용자 추가 지시 반영 — 프로젝트/패키지 식별자 정정, WSL/NTFS 개발 정책, 데이터 위치(NTFS의 `data/`) 명시

**변경 파일**:
- 갱신: `README.md`, `AGENTS.md`, `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/backend-package.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reflection-summary.md` 외 일괄 치환 대상 전부

**결정**:
- 식별자 통일: GitHub 저장소 = `python-kraddr-geo`, Python import = `kraddr.geo`, CLI = `kraddr-geo`, env prefix = `KRADDR_GEO_`, PostgreSQL DB = `kraddr_geo`, 프론트엔드 패키지 = `kraddr-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`, importlinter `root_package = "kraddr.geo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드)을 master 문서에 반영

**변경 파일**:
- 신규: `SKILL.md`, `CHANGELOG.md`
- 신규 (`docs/`): `architecture.md`, `decisions.md`, `data-model.md`, `tasks.md`, `resume.md`, `journal.md`, `backend-package.md`, `frontend-package.md`, `agent-guide.md`, `external-apis.md`
- 갱신: `AGENTS.md`, `README.md`, `docs/address-db-schema.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/spatialite-vworld-implementation.md`
- 신규: `docs/reflection-summary.md` (반영 내용 요약)

**결정**:
- ADR-001 ~ ADR-006, ADR-013을 `docs/decisions.md`에 초기 기록
- 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 (ADR-003)
- 라이브러리 API는 async-only (ADR-002)
- 로더는 GDAL Python binding 사용, `ogr2ogr` subprocess 폐기 (ADR-005)

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kraddr-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kraddr.geo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
