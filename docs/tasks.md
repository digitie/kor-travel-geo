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

- [ ] **T-326a~c** — geo 스택 odroid(192.168.1.13) 이전 + 빈 호스트 풀로드 (ADR-070 proposed, Track 2;
  소유자 결정 대기) — 아래 "T-326" 섹션.
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

### T-326 — geo 스택 odroid(192.168.1.13) 이전 + 빈 호스트 풀로드 (ADR-070 proposed, 미구현, Track 2)

결정 [ADR-070](adr/070-odroid-host-and-empty-host-full-load.md)(D1~D9; 소유자 결정 대기 — **accepted 게이트 3건**: 설계
§14-8 소스 ZIP 재확보·serving DB 직접 풀로드·dump 복원 지름길, §14-12 geo 플립 여유 값(0.2 → anon ≤ 0.95 GiB) 또는 n150
잔류, §14-21 키 정책 (가)/(나) — 닫히면 ADR 상태 `accepted`, T-326b PR에서 한 줄; 추천안 수용이면 변경 0인 것: §14-19
Track 1 전량 재계획 수용, §14-4 odroid plane 공개 host, §14-7 geo 백업 off, §14-6 빌드 경로 + Dagster base digest 처리 —
달리 결정되면 amendment). 호스트 쪽 작업(odroid 초기화·PG 인스턴스·Manager `hosts:`·플립 PR·메모리/memswap
정책·소스 bind 상시화)은 **Manager 저장소(ADR-58, T-MGR-01a~05·T-OPS-01~03)가 추적**한다 — 여기서는 geo 몫만.
의존(설계 §11.2 순서 그대로): T-326a(실측)는 지금 가능; T-326b는 Manager odroid 초기화(`prod-deployment.md` §9.1 = 설계
§11.1)·`ensure dagster`(odroid PG)·소스 bind 상시화 머지 **그리고 geo 플립 PR(§11.2 8a) 머지 → n150 geo cs stop → odroid 재설치**
뒤(= 8b; 효과 검사는 런북 순서 0); T-326c는 §11.2 9단계(소비자 URL 전환) 뒤. **분기**: §14-12가 n150 잔류(또는 D6 anon 미달)로
닫히면 ADR 상태 `rejected`(D1·D2만 남김), T-326b/c 닫음. **§14-8 지름길(dump 복원)을 고르면** Dagster `db_restore`는 odroid
NOCREATEDB 롤에서 E0410이라(`infra/db_capabilities.py:3-11`) 수동 `pg_restore`(`shared_admin`) 또는 ADR-58 롤 amendment가 답에
포함돼야 한다(ADR-070 D3-6, 런북 지름길 절). **Track 1 ADR-069(T-325)와 머지 순서 무관**(어느 쪽이 먼저여도 플립은 막히지
않음)이나, T-325 구현 뒤에는 풀로드의 새 `data_token`이 소비자 전량 재계획을 유발한다(ADR-070 D8 — 수용, URL 전환은
`full_load_batch` SUCCESS 다음 날). 런북 [deploy/staging-full-load.md](deploy/staging-full-load.md) "빈 호스트(odroid) 풀로드 — 계획" 절.

- [~] **T-326a** — T-055/T-108 정정 + odroid envelope·n150 anon 실측 (규모 M; T-063 보류 승계)

  문서 정정은 이 PR에서 완료 ✅(`docs/t055-deployment-n150-odroid.md` 정정 블록 — x86 가정 → 실측 aarch64 Cortex-A55×4
  1.8 GHz·7,676 MiB·eMMC/NVMe, PG 값은 설계 §5.3(Manager ADR-58 결정 (8)) 포인터; `docs/t108-deploy-automation.md` 보류 블록 — 레지스트리·
  QEMU 불채택, `linux/arm64` 확정). 남은 것: (1) odroid envelope — **지금 가능**(NOPASSWD sudo·docker 그룹 완료, fact base
  §A3): `nvme smart-log`, `docker info`(`Architecture: aarch64`; `No memory limit support`·`No swap limit support` 문자열
  **부재**로 판정 — "WARNING 0건"은 쓰지 않는다), `scripts/capture_deployment_envelope.py --run-probes`(**스크립트 기본
  probe만**: fio randread 8k QD32 ×4 jobs + sysbench cpu/memory, `scripts/capture_deployment_envelope.py:134-176`; 스크립트는
  바꾸지 않는다). 실행 방법: 스크립트는 geo 체크아웃에 있고 odroid 체크아웃은 §11.1-8(Manager 설치)에서야 생기므로 `scp`로
  1파일 반입(의존 `fio`·`sysbench` apt); fio 위치는 `--probe-dir`(`:86-90`; `--fio-size` 기본 1G `:92`)로 eMMC가 아니라
  **지금은** `/mnt/media/<tmp>`(digitie 소유 임시 디렉터리), **디스크 단계(fstab bind) 뒤**에는 `/mnt/media/kor-travel/perf`
  (root:root 트리라 `sudo install -d -o digitie …/perf` 선행); **fstab bind 뒤**(Manager 몫, 미완): **수동 fio 3종**(ADR-070 D9;
  명령줄은 `docs/t055` 정정 블록, 같은 `--directory`)을 Plex 유휴·재생 중 **2회** → `artifacts/perf/n150-vs-odroid-<date>/odroid-m1s/`;
  (2) n150에서 지금 가능한 것 — ⓐ geo code-server `db_backup`·`mv_refresh` 중 cgroup anon 최대값(측정법은 ADR-070 D6;
  run 기동은 다음 야간 schedule을 기다리거나 admin `POST /v1/admin/maintenance/refresh-mv`(`src/kortravelgeo/api/routers/admin.py:1867`
  `@router.post("/maintenance/refresh-mv")` + `app.py:177` prefix — `/v1/admin/loads`에 `kind=mv_refresh`는 source-load op로 가므로
  아님)·`POST /v1/admin/backups`(`routers/admin.py:1928`)로) → **ADR-070 D6 플립 조건 입력**(anon ≤ 0.95 GiB(여유 0.2) — 미달이면
  geo n150 잔류); ⓑ 같은 창의 PG 컨테이너 cgroup anon — D6가 아니라 **Manager 쪽 §14-14(PG `mem_limit 4g` 가드 vs 하드 캡)
  입력**; ⓒ **전환 전 현재 값 기록 1회**(면제 여부는 코드·journal 2026-08-17로 이미 닫힘 — ADR-070 컨텍스트 1): n150 DB
  `SELECT count(*) FROM ops.public_api_keys WHERE active`(기대 ≥1) + 명령은 ADR-070 D2(대상 `.14`)로 Map `.env` **키 유효성** 200/401
  + n150 운영 `mv_geocode_target`·`tl_juso_text` `count(*)`(T-326b 6단계 비교 기준) → journal(소유자 §14-21 입력); 가능하면 T-290l
  scratch 풀로드(2026-07-12)의 wall clock을 `load_jobs`/run store에서 회수;
  (3) GDAL arm64 빌드 시간·메모리, Dagster base digest(`kor-travel-geo-dagster/docker/dagster.Dockerfile:34`)의 arm64 manifest
  존재 1회 확인(`docker buildx imagetools inspect` — Dockerfile `:31-32` 주석대로 index digest면 기대 결과이고 재핀 논의 없음;
  amd64 manifest일 때만 T-326b에서 ADR-070 D7 처리).
  - 수정 파일: `artifacts/perf/…`(산출물), `docs/t055-deployment-n150-odroid.md`(실측 수치 기입), `docs/journal.md`.
  - 수용 기준: envelope `system-envelope.md`에 `aarch64`·fio(스크립트 1 + 수동 3) 2회(유휴/재생) 수치; n150 cs anon·PG anon·
    Map 키 상태코드·active 키 수·운영 MV `count(*)`·base digest 확인 결과가 journal에 숫자로 기록돼 D6 판정(옮김/잔류)이 한 줄로
    내려진다.

- [ ] **T-326b** — 빈 호스트 풀로드 실행 + `mv_refresh` run 상한 결정 + `.env.prod.example` 주석 (규모 M, 실행 L)

  런북 "빈 호스트(odroid) 풀로드 — 계획" 절대로(순서 0 = §11.2 8a 완료 효과 검사 뒤): 소스 반입(파일 수 > 0·NVMe 장치
  프리플라이트) → `ensure geo` → **serving DB 직접** `full_load_batch`(`target_database` 없음; 라우팅 env 없음 —
  `_full_load_launch.py:9-11`; 이 한 run이 게이트 → `mv_refresh` child까지 돈다, `loaders/batch_dag.py:22`) → **standalone
  `mv_refresh` 1회**(`POST /v1/admin/maintenance/refresh-mv`, D4 입력) → 키 재발급(ADR-070 D2 (나)) → smoke. 소요를 런북 표에
  기록(batch 전체·child·standalone 따로). **`mv_refresh` 상한**(ADR-070 D4, standalone 실측 기준): (ⅰ) `LONG_JOBS`에 추가
  (`kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py:15`) 또는 (ⅱ) 실측×1.5를 `policy_for_job`의 job별 초 매핑으로
  (`recovery.py:21-27` → `RecoveryPolicy(max_runtime_seconds=…)`; **job 태그 인자로는 안 된다** — `geo_job`이 policy 태그를 뒤에
  병합해 21600으로 덮는다, `recovery.py:34`; `RecoveryPolicy.tags` 소스는 kortravelcommon이라 구현 전 1회 확인) — 어느 쪽이든
  `kor-travel-geo-dagster/tests/test_definitions.py:76-88`의 `"mv_refresh"` 기대값 동기. **Dagster base digest**(ADR-070 D7):
  T-326a (3)에서 **주석(`dagster.Dockerfile:31-32`)과 달리 amd64 manifest로 확인될 때만** 추천안은 `:34` 두 FROM을 index digest(또는
  arm64 manifest digest)로 재핀 + `tests/test_image_constraints.py:96-102` 기대값 갱신; 설계 §8.2/§8.4의 태그 완화를 소유자가
  고르면 같은 테스트의 완화가 따라온다(§14-6에 병기). ADR 상태 `proposed → accepted` 한 줄(게이트 3건 뒤).
  - 수정 파일: `kor-travel-geo-dagster/src/kortravelgeo_dagster/recovery.py`(필수 — (ⅰ) `LONG_JOBS` 또는 (ⅱ) 매핑),
    `kor-travel-geo-dagster/tests/test_definitions.py`, `kor-travel-geo-dagster/docker/dagster.Dockerfile:34`·
    `kor-travel-geo-dagster/tests/test_image_constraints.py`(digest 재핀 필요 시만), **`.env.prod.example`**(주석만 —
    `KTG_ADMIN_TRUSTED_PROXY_CIDRS` loopback 불변·`.14` 금지(ADR-070 D1), `KTG_DAGSTER_URL`의 `12502`는 standalone 스택 값이라
    "Manager compose 주입" 주석으로, `KTG_DAGSTER_PUBLIC_URL` = odroid plane 공개 host(§14-4), 소스 bind 기본 경로
    `/home/digitie/kor-travel-geo-data/source`와 "EXECUTED_JOB_KINDS 없음" 메모, `KTG_VWORLD_API_KEY` 비면 전부 거부 메모),
    `docs/ports.md:34`(같은 `12502` standalone 서술 정정), `docs/deploy/staging-full-load.md`(소요 표), `docs/adr/070-*.md`
    (상태 줄), `docs/journal.md`·`docs/resume.md`.
  - 수용 기준: 런북 순서 0 효과 검사 PASS(odroid validate의 geo host == odroid); odroid root `.env` `KOR_TRAVEL_GEO_VWORLD_API_KEY`
    비어 있지 않음(발급 전 `/v2/reverse?key=<VWorld 키>` 200 — 비면 `public_api_key.py:66-67`로 전부 거부); 풀로드 run **cancel
    없이 SUCCESS**(consistency report PASS 포함); `mv_refresh` 상한은 **효과로**(ADR-070 D4 — "< 상한의 70 %"는 (ⅱ)에서 항진명제라
    쓰지 않는다): (ⅱ)면 유효 태그 값 == `round(standalone 실측 s × 1.5)`이고 `test_definitions.py` 기대값이 그 숫자, (ⅰ)은 실측이
    21600 s를 넘었을 때만(숫자를 journal에); `mv_geocode_target`·`tl_juso_text` `count(*)` > 0이고 T-326a의 n150 운영 `count(*)`와
    비교해 차이가 기준월로 설명됨(숫자 둘 다 journal — 6,416,637은 참고값); `test_definitions.py` 초록 + **일부러 빨갛게**(기대값 한
    줄 바꿔 실패 확인); 키 재발급 뒤 `/v2/reverse` 200(런북 6단계 curl, 발급 키); 지름길 선택 시 — (a)면 수동 `pg_restore` 종료
    코드 0 + 위 count 기준, (b)면 `POST /v1/admin/restores`가 E0410 없이 run 생성.

- [ ] **T-326c** — 플립 뒤 검증 + Track 1 상호작용 확인 (규모 S, 설계 §11.2 9단계(소비자 URL 전환) 뒤)

  n150 geo-api **stop 상태**에서 Map geocode e2e 키 경로 200 + odroid access log peer `192.168.1.14`; n150→odroid
  `/v2/reverse` p50/p95(ADR-070 D8 ≈2.5 h+ 추정 검증); Track 1 센서는 **조건부** — T-325(ADR-069) 구현 완료 상태면 URL 전환 뒤
  계획 1건 생성(재계획 수용; dump 복원이면 0건) 확인, 미구현이면 이 항목 해당 없음(journal에 어느 쪽인지 기록);
  `docs/deploy/docker-compose.geo-source-vol.yml` 삭제는 Manager 상시 bind 머지 **그리고** `geo-materialize` 공유 볼륨이 Manager
  compose에 들어가거나 `source_rebuild_db` 경로 불사용 결정 뒤(overlay `:31,34,37` — ADR-070 D3-2).
  - 수정 파일: `docs/deploy/docker-compose.geo-source-vol.yml`(조건 충족 시 삭제), `docs/deploy/staging-full-load.md`,
    `docs/journal.md`·`docs/resume.md`.
  - 수용 기준: 위 효과 전부 숫자·로그로 journal에; "200이면 통과"만으로 닫지 않는다.

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
  **2026-10-13**: odroid(ODROID M1S, 실측)가 있으므로 odroid 몫은 **T-326a**가 승계한다(`docs/t055` 정정 블록) —
  이 항목은 SQL/REST 벤치마크 3회 반복 등 T-326a 범위 밖의 비교 측정만 남긴다.
