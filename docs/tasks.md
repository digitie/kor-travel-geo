# tasks.md — 백로그

열린 `[ ]`(진행 중/대기/보류) task만 두는 백로그. 완료·종료 이력은
[`docs/tasks-done.md`](tasks-done.md), 진척·"다음 한 작업"은 [`docs/resume.md`](resume.md)가
정본이다. 작성·유지 규약(역할 표·라우팅·ID 스킴·entry 형식)은
[`docs/tasks-rule.md`](tasks-rule.md), PR/리뷰 루프·병행 운영 같은 작업 진행 규칙은
[`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다. 현재 상태와 세션 연속성은
[`CLAUDE.md`](../CLAUDE.md)가 정본이다.

작업 항목은 `T-NNN` 형식의 ID로 관리한다(번호 배정은 tasks-rule.md §3). 새 작업은
"대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은
`tasks-done.md` 상단에 누적한다.

## 현재 세션 상태 (2026-10-13)

열린 항목 인덱스(상세는 아래 섹션; 완료된 T-297/T-299/T-300/T-303/T-304는 `tasks-done.md`로 갔다).

- [ ] **T-325a~c** — 데이터셋 `data_token`(서빙 내용 지문) + 응답 `dataset` 필드 (ADR-069 proposed,
  소유자 승인 대기) — 아래 "T-325" 섹션.
- [ ] **T-324** — 공유 Dagster plane geo 선행 작업 잔여(머지 후 `ktdctl ensure geo` 재빌드 확인) —
  아래 "T-324" 섹션.

## 진행 중

### T-290 — geo 독립 Dagster 오케스트레이션 이관 (epic)

결정 [ADR-066](adr/066-geo-independent-dagster-orchestration.md), 구현 정본
[architecture/dagster-boundary.md](architecture/dagster-boundary.md), 단계·분해·contract·e2e 게이트는
[dagster-migration-plan.md](dagster-migration-plan.md)가 정본. 통합 브랜치
`agent/claude-dagster-migration`(전 milestone 완료 후 main 머지). 두 에이전트 A(실행엔진/백엔드)·
B(배포/관측/e2e) 병렬. **기준: 최소수정 X, 미래지향(유지보수성·안정성·완성도·품질·최적구조).**

- [x] **T-290a** (A) — `kortravelgeo_dagster` 패키지 스캐폴드 + resources + `mv_refresh` @job (M1) — #419
- [x] **T-290b** (A) — Dagster 배포(Dockerfile/compose/메타DB/포트 12502) + n150 mv_refresh run SUCCESS (M1) — #421·#422, manager #47
- [x] **T-290c** (A) — `load_jobs` executor/lease + recovery split + reconciler + cancel 골격 (M1, 4단계 게이트) — #420, 리뷰 후속 #424
- [x] **T-290d** (B) — API GraphQL observe 라우터 (M2) — #417
- [x] **T-290e** (B) — admin `/admin/dagster` 관측 화면 (M2) — #418
- [x] **T-290f** (A) — scheduled backup @schedule 온램프 + @run_failure_sensor + 알림 (M2)
- [x] **T-290g** (A) — `db_backup` Dagster 실행 + verify/copy/restore_drill (M3) — #464 계열
- [x] **T-290h** (B) — run detail 로그·artifact 링크 + 실패/overdue 알림 UI (M3) — #471
- [x] **T-290i** (A) — `db_restore`(새 빈 DB) Dagster 실행, hot-swap 수동 유지, RetryPolicy off (M4) — #472
- [x] **T-290j** (A) — loader + `full_load_batch` Dagster 실행(`batch_dag` 미러 + GDAL 이미지) (M5) — #476/#477
- [x] **T-290k** (A) — in-process 큐/이벤트루프 우회 은퇴, ADR-006/011 superseded (M5) — #479·#480·#481·#482·#483(DDL 0026)
- [x] **T-290l** (B) — live e2e harness를 Dagster 관측까지 확장 + 최종 회귀 (M5) — 전국 full-load 스테이징 라이브 e2e 성공(mv=6,416,637), cutover 배포·검증

**✅ T-290 에픽 완료 (2026-07-12)** — 통합 브랜치 `agent/claude-dagster-migration`(HEAD `9bcb949`)에 병합·n150
cutover 배포·검증 완료. 실행이 프로덕션에서 **Dagster-only**(in-process drain 삭제). live UI e2e 게이트 #1~#4
전부 통과(관측+온램프·backup 실행·restore 새DB·full-load+큐은퇴+최종회귀). 상세는 `tasks-done.md`·`resume.md`.

**후속 완료**: `integration→main` 머지(#485, merge commit `658a54e`) 및 geo Dagster 공개
URL(`geo-dagster.digitie.mywire.org`)을 관리자 `/admin/dagster` 화면에 iframe으로 임베드
(`DagsterEmbed` + `resolveDagsterPublicUrl`, 서버측 `KTG_DAGSTER_PUBLIC_URL` 해석; Dagster UI가
frame-busting 헤더를 보내지 않아 CSP 변경 불필요). 남은 것은 UI 컨테이너 재배포로 라이브 반영하는 단계뿐.

### T-324 — 공유 Dagster plane(dagster-shared plan) geo 선행 작업

계획 정본: Manager 쪽 `dagster-shared-plan.md`(2026-09-29) §3·§5 stage 0/2/3. branch
`feat/dagster-shared-stage0`(PR은 아직 없음 — 머지·배포는 소유자 지시 후).

- [x] stage 0(0.4) — 이미지가 `kor-travel-geo-dagster/docker/constraints-dagster.txt`로 exact 설치
  (dagster 1.13.24 계열, dagster-postgres 0.29.24, pydantic/psycopg/grpcio/protobuf, sqlalchemy 2.1.1),
  두 `FROM`을 `python:3.12-slim@sha256:f77ac9e4…`(3.12.14)로 digest 핀. CI `dagster` job도 같은 `-c`.
- [x] 3.3 — `/v1/ops/dagster/summary`·`/runs/{id}`를 geo code location으로 한정(단일 tenant에서도 결과 동일).
- [x] 2.2(D4) — backup schedule·retention janitor·run-failure sensor `default_status=RUNNING`,
  restore drill은 `STOPPED`(n150 운영 상태 그대로).
- [x] 공유 plane 전제 — run-failure sensor의 `monitor_all_code_locations` 제거, entrypoint psycopg2 guard가
  `KOR_TRAVEL_DAGSTER_SHARED_PG_URL`도 검사.
- [ ] 머지 후 `ktdctl ensure geo`로 재빌드(stage 0 rollout 2번) — 세 컨테이너 site-packages 1.13.24 확인.
- [x] (계획 밖 발견) 공유 instance의 `run_monitoring.max_runtime_seconds`(21600) 기본값이 geo run에도
  걸린다(지금 geo instance엔 run_monitoring이 없어 무제한). 소유자 결정(2026-09-30): 6시간을 넘을 수 있는
  job만 `dagster/max_runtime=86400` — `full_load_batch`·`load_source`·`db_restore`·`backup_restore_drill`
  (`kortravelgeo_dagster/run_tags.py`). 나머지 8개는 공유 기본값. `test_definitions.py`가 12개 job 전부의
  기대값을 나열해 새 job은 선택을 강제당한다.

(그 외 진행 중 작업 없음. T-177A~T-177H·T-183 완료 — `tasks-done.md` 참조.)

## 대기

> 번호 배정 순서·ID 스킴(ADR-050)은 [`docs/tasks-rule.md`](tasks-rule.md) §3을,
> 두 에이전트 병행 권장 순서·병행 운영 원칙(PR/리뷰 루프)은
> [`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다.

T-178a~T-178f Claude Code 리뷰 후속과 T-177 파일 기반 full-load e2e 재검증은 모두 닫혔다.
T-177은 T-073 shell script에 맞추지 않고, opt-in pytest 통합/e2e가 실제 파일을 읽어 scratch
PostgreSQL DB를 구축하는 방향으로 완료했다. 상세 계획과 Task 분해는
[`docs/t177-file-driven-full-load-e2e-plan.md`](t177-file-driven-full-load-e2e-plan.md), 최종
성능 수용은 [`docs/t177h-benchmark-acceptance.md`](t177h-benchmark-acceptance.md)가
정본이다.

### T-325 — 데이터셋 `data_token`(서빙 내용 지문) + 응답 `dataset` 필드 (ADR-069 proposed, 미구현)

결정 [ADR-069](adr/069-dataset-data-token.md)(소유자 승인 대기 **4개** — 설계 §12 #1·#2·#18 + §4a #11 캐시 전체 삭제;
승인 시 ADR 상태를 `accepted`로, T-325a PR에서 한 줄; 그것이 T-325a 착수 조건), 배경 설계 요약
[t291-dataset-version-external-api.md §7](t291-dataset-version-external-api.md).
소비자 측 작업은 Map(ADR-109)·concierge(ADR-49) 각 저장소가 추적한다(코드 머지는 geo와 병렬 가능, 활성화 검증만 geo
배포 뒤). 의존: a → b → c. PR 묶음: **PR-1 = a+b**
(코드·마이그레이션·테스트 **+ DTO 변경에 따른 `openapi.json` 재export와 UI `gen:types` 산출물** — OpenAPI drift
워크플로 `.github/workflows/openapi.yml`과 `ci.yml:135-137` gen:types diff 검사가 모든 PR에 돌므로 뒤로 미룰 수
없다, ADR-069 컨텍스트 7 — **+ `CHANGELOG.md`·journal·resume**, 사용자 가시 변경이라 AGENTS.md 작업 후 체크리스트가
PR 단위로 요구한다), **PR-2 = c**(UI 화면·api-reference 문서·CHANGELOG의 UI 항목). 모두 `feature branch + CI green` 뒤 머지.

- [ ] **T-325a** — 데이터 지문·`data_token`·캐시 무효화·backfill CLI (규모 M)

  `ops.dataset_snapshots.data_fingerprint TEXT NULL`(Alembic `0029_t325a_dataset_data_fingerprint`, 직전 head
  `0028_t319_source_month_manifest`; `infra/sql.py` DDL + `sql/ddl/001_schema.sql` 사본) +
  `DATA_FINGERPRINT_TABLES`/`DATA_FINGERPRINT_SQL`(ADR-069 D2·D3 — surrogate key·적재 메타 제외) +
  `_insert_dataset_snapshot_and_release`가 `data_fingerprint` 인자 None이고 active면 지문 계산(`mv_hash`와 같은 규칙;
  **advisory lock 획득 전**, 같은 transaction, savepoint 안 10 min timeout, 끝나면 항상 `ROLLBACK TO SAVEPOINT`, fail-open
  → NULL + `notes` 접미 `data_fingerprint_failed: <code>`) + lock 뒤 원장 INSERT 자리에서 인자와 무관하게 active면
  `GeoCacheRepository.clear_on(conn)`(D4~D6) + `derive_data_token`(`core/dataset_version.py`) +
  `DatasetVersionEntry.data_token`·admin `ServingRelease.data_token` + `ktgctl serving fingerprint-active [--dry-run]`(D9 —
  `--dry-run`은 헬퍼와 같은 `DATA_FINGERPRINT_SQL`·같은 10 min timeout).
  - 수정 파일: `src/kortravelgeo/infra/sql.py`, `sql/ddl/001_schema.sql`, `alembic/versions/0029_t325a_dataset_data_fingerprint.py`(신규),
    `src/kortravelgeo/infra/admin_repo.py`, `src/kortravelgeo/infra/cache.py`, `src/kortravelgeo/core/dataset_version.py`,
    `src/kortravelgeo/dto/v2.py`, `src/kortravelgeo/dto/admin.py`, `src/kortravelgeo/cli/main.py`,
    `tests/unit/test_data_fingerprint_covers_serving_tables.py`(신규), 통합 테스트, **`openapi.json`**(재export),
    **`kor-travel-geo-ui/types/api.gen.ts`·`kor-travel-geo-ui/lib/schemas.gen.ts`**(`npm run gen:types` 산출물),
    `CHANGELOG.md`(`[Unreleased]` Added: `data_fingerprint`·`data_token`·`DatasetVersionEntry.data_token`·
    `ServingRelease.data_token`·`ktgctl serving fingerprint-active`; Changed: 활성 릴리스마다 `geo_cache` 삭제),
    `docs/journal.md`·`docs/resume.md`.
  - 수용 기준: (1) 지문 민감도 통합 테스트 — 같은 데이터 재활성화 → 같은 토큰; `postal_bulk_delivery` 같은 파일
    2회 적재(`bulk_id` 재부여) → 같은 토큰; `mv_geocode_target`은 원천 표 1행 변경 + `refresh_mv` 뒤 → 다름(MV는
    직접 UPDATE 불가); `tl_scco_sig` 명칭·`tl_kodis_bas`·`postal_bulk_delivery`·`tl_sppn_makarea` 1행 변경 → 다름;
    폴리곤 정점 1개 추가 → 다름; timeout 주입 → active + NULL + `notes` 접미 + 뒤이은 INSERT·DELETE가 경로의 기존
    timeout으로 돈다; restore 경로 릴리스도 토큰 비NULL(같은 백업 두 번 → 같은 토큰); 일변동 1건(MVM 63) 뒤
    `record_mv_refresh_release(load_batch_id=None, consistency report 없음, release_kind="daily_delta")` 호출 →
    `source_set_hash` 동일·`data_token` 상이 — **기준월 추론 분기(`admin_repo.py:758-759`)를 타게 구성**한다(batch를
    넘기면 해시가 달라져 케이스 무효); 캐시 무효화(두 경로) — reverse 1회로 캐시 1행 → `postal_bulk_delivery` 1행
    변경 → standalone `record_mv_refresh_release` → 같은 좌표 reverse가 새 우편번호·새 `dataset.data_token`; geocode 1회로
    캐시 1행 → `tl_sppn_makarea` 1행 변경 → standalone `record_mv_refresh_release` → 같은 질의 geocode가 새 후보·새
    `dataset.data_token`; 네 경로 모두 `geo_cache` 0행. 표 변경·캐시 삭제 케이스는 **일부러 빨갛게**(해당 표/삭제를
    빼고 실패 확인 — 캐시 두 케이스 모두) 기록. (2) `history` entry에 `data_token`, 지문 NULL 행은 필드 생략.
    (3) **prod 규모 지문 사전 실측 1회** — 소유자가 PR-1 브랜치 체크아웃의 `ktgctl serving fingerprint-active
    --dry-run`(읽기 전용, 저장·캐시 삭제 없음, 헬퍼와 같은 SQL 상수·같은 timeout)을 n150 prod DB에 **머지 전** 실행하고
    `/proc/pressure/io`를 동시 기록; 10 min timeout의 50% 안이면 통과, 넘으면 머지 전 설계 재검토(ADR-069 결과(부정)의
    지렛대 순서). (4) 머지·배포 뒤 backfill(`--dry-run` 없이) → prod `current.data_token` 비NULL·`geo_cache` 0행.
    (5) lint 초록 + lint를 **일부러 빨갛게**(repo에 가짜 `JOIN tl_new_table` 추가 → 실패; 허용 목록에 유도 집합에 없는
    표 이름 추가 → 실패; 일반 CTE 또는 `AS MATERIALIZED (` CTE만 추가 → 통과; 소문자 `from tl_x`는 lint가 못 보므로
    대문자 규약 메모) + `postal_pobox` v2 경로 여부 확인 결과를 PR 본문에. (6) `hotswap.py`·`partial_restore.py`·
    `postload.py` diff 0. (7) `python scripts/export_openapi.py --check`·UI `gen:types` diff 0 초록(PR-1 CI 게이트).
    (8) 지문 SELECT가 `pg_advisory_xact_lock` 앞에서 실행됨을 단언(지문 SQL 지연 주입 + 동시 두 번째 활성화 호출이
    지문 시간 동안 lock 대기 없이 진행 — 통합 테스트).
- [ ] **T-325b** — v2 응답 최상위 `dataset{version_token, data_token}` (규모 S, T-325a 뒤)

  `DatasetRef` DTO + 네 응답 클래스(`GeocodeV2Response`·`ReverseV2Response`·`SearchV2Response`·
  `RegionsWithinRadiusResponse`)에 `dataset: DatasetRef | None = None` + `api/dataset_ref.py` TTL 10 s 의존성 +
  `api/routers/v2.py` 네 핸들러 `model_copy(update={"dataset": ref})`(ADR-069 D7).
  - 수정 파일: `src/kortravelgeo/dto/v2.py`, `src/kortravelgeo/api/routers/v2.py`, `src/kortravelgeo/api/dataset_ref.py`(신규),
    tests, `openapi.json`(재export), `kor-travel-geo-ui/types/api.gen.ts`·`lib/schemas.gen.ts`(`gen:types` 산출물).
  - 수용 기준: (1) 4 endpoint 응답에 `dataset`, active 릴리스 없으면 생략; (2) TTL 만료 후 새 값(시간 주입);
    (3) reverse p50 회귀 < 5% — `scripts/benchmark_api_latency.py` reverse 케이스, PR 베이스 commit 대비 같은
    로컬 환경; (4) 외부 fallback(vworld·juso) 응답에도 로컬 토큰 + `candidates[].source≠local`; (5) 캐시 hit 응답에도 현재
    토큰; (6) `export_openapi.py --check`·`gen:types` diff 0 초록.
- [ ] **T-325c** — admin UI 화면·api-reference 문서·CHANGELOG (규모 S, T-325b 뒤)

  OpsPanel releases 표에 `data_token` 열("데이터 동일"·"지문 없음" 배지, `notes` 접미 툴팁, 연속 2회 지문 없음
  배너) + `DatasetVersionDetailDialog` live preview + 문서. (OpenAPI 재export·`gen:types`·API CHANGELOG 항목은 PR-1에서
  끝난다.)
  - 수정 파일: `kor-travel-geo-ui/components/admin/OpsPanel.tsx`,
    `kor-travel-geo-ui/components/admin/ops/DatasetVersionDetailDialog.tsx`, `CHANGELOG.md`(`[Unreleased]` — UI 화면 항목만),
    `docs/api-reference/v2/{dataset-version,geocode,reverse,search,regions-within-radius}.md`(응답 예시에 `dataset`,
    `dataset-version.md`의 "예정" 절을 현재 규약으로 승격), `docs/api-reference/llm-summary.md`(v2 dataset 행에
    `data_token`, 네 조회 행에 `dataset`), `docs/tasks-done.md`·`resume.md`·`journal.md`.
  - 수용 기준: (1) UI lint·type-check 초록; (2) 소비자 규약 문단이 "`data_token` 동등성, 없으면 판정 불가,
    `version_token`은 관측용"을 명시(ADR-069 D8 문구 그대로); (3) UI 표에 두 배지 + 툴팁; (4) 네 v2 문서와
    `llm-summary.md`에 `dataset`/`data_token`.
- (보류) phase 2 — 코드 단위 인벤토리 + `POST /v2/dataset/changes`(ADR-069 후속). 소유자 결정 뒤 번호 부여.

### T-308 공용 instance 이전 후속 (2026-09-28 사고 조사에서 나온 것)

근거와 증거는 `docs/journal.md` 2026-09-28·2026-09-29 항목. T-309~T-318은 2026-09-29에 완료
(`tasks-done.md`). 아래는 그 리뷰에서 나온 후속이다. 우선순위 순.


### 선행 리뷰 후속

2026-07-27 GitHub 열린 이슈 감사(15건 조사, `tasks-done.md` 참조) 결과 남은 미해결 리뷰 후속 6건
**전부 완료·종료** — 이슈 #298은 PR #491, #302는 PR #493, #299는 PR #495, #252는 PR #497, #307은
PR #499, #201은 PR #502(아래 tasks-done.md 참조). 근거는 각 이슈 본문·코멘트 참조.

### 선택 후속 (낮은 우선순위)

- **진행 중 작업 없음.** (T-219 잔여 L까지 완료 — `tasks-done.md` 참조.)

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
