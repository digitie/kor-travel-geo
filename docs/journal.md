# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-07-09 (T-290 #434 리뷰 후속 — Dagster public URL 오류 응답 보강, by codex)

**작업**: Claude Code의 T-290 후속 PR #433/#434를 통합 브랜치 기준으로 리뷰했다. #433은 이전 리뷰
이슈(#427/#428/#430/#431/#432)에 대한 후속으로 blocking finding이 없다고 PR 코멘트에 기록했다. #434에서는
`dagster_public_url` 정상 경로는 검증되지만, summary 오류 응답 경로가 `_empty_summary_data()`에서
`settings.dagster_public_url` raw 값을 다시 읽어 iframe/link용 `dagster_url`로 반환하는 회귀를 확인했다.
추적 이슈는 #435로 분리했다.

**변경**:
- `_empty_summary_data()`가 `Settings`를 받아 raw URL을 다시 읽지 않고, 호출자가 검증된 browser-facing
  `dagster_url`을 명시적으로 넘기게 했다.
- `_dagster_urls()` 성공 이후의 Dagster unavailable / GraphQL error summary는 `dagster_urls.public_url`을
  재사용한다.
- `_dagster_urls()` 자체가 실패한 config-error summary는 `_safe_summary_dagster_url()`에서 public URL을
  별도 검증하고, invalid public URL이면 allowlist를 통과한 internal URL로 fallback한다. 둘 다 유효하지
  않으면 빈 문자열을 반환해 raw invalid value가 iframe/link 필드로 나가지 않게 한다.
- invalid `dagster_public_url`이 raw로 응답되지 않는 테스트와 outage summary가 정규화된 public URL을
  유지하는 테스트를 추가했다.

**검증**:
- `.venv/bin/python -m pytest tests/unit/test_dagster_router.py -q -s` → 14 passed.
- `.venv/bin/python -m ruff check src/kortravelgeo/api/routers/dagster.py tests/unit/test_dagster_router.py` 통과.
- `.venv/bin/python -m mypy src/kortravelgeo` 통과.

## 2026-07-08 (T-290f scheduled backup Dagster 온램프, by codex)

**작업**: M2의 남은 실행엔진 항목인 T-290f를 통합 브랜치 위에서 진행했다. 이 단계는 `db_backup`
leaf를 Dagster로 옮기지 않고, Dagster `@schedule`이 기존 idempotent
`POST /v1/admin/backups/scheduled/run-due`를 호출하는 온램프다. due 판정, advisory lock, audit, 실제
backup enqueue는 기존 API/`load_jobs` 경계가 계속 소유한다.

**변경**:
- `Settings`에 `KTG_DAGSTER_ADMIN_API_URL`을 추가했다. Dagster→geo API 호출은 이 URL과 기존
  `KTG_ADMIN_PROXY_SECRET`/admin role header 경계를 사용한다.
- `kortravelgeo_dagster.resources`에 `DagsterAdminApiClient`와 `admin_api` resource를 추가했다.
- `kortravelgeo_dagster.backup`을 추가해 `scheduled_backup_run_due` job/op,
  `scheduled_backup` schedule(15분 주기, 기본 STOPPED), `run_failure_sensor`와 optional
  `failure_notifier` resource 경계를 등록했다.
- `definitions.py`가 backup job/schedule/sensor와 `admin_api` resource를 aggregate하게 했다.
- 예제 env와 Dagster 마스터플랜/경계 문서를 새 URL·온램프 구조에 맞췄다.

**검증**:
- `TMPDIR=/tmp PYTHONPATH=src:kor-travel-geo-dagster/src uv run --python 3.12 --extra api --extra dev --with 'dagster>=1.9,<2' --with 'dagster-webserver>=1.9,<2' --with 'dagster-postgres>=0.25,<1' --with 'boto3>=1.34,<2' --with 'botocore>=1.34,<2' pytest -q -s kor-travel-geo-dagster/tests`
  → 8 passed.
- 같은 Dagster 의존성 환경에서 `ruff check kor-travel-geo-dagster/src kor-travel-geo-dagster/tests src/kortravelgeo/settings.py`
  통과.
- 같은 Dagster 의존성 환경에서 `mypy kor-travel-geo-dagster/src kor-travel-geo-dagster/tests src/kortravelgeo/settings.py`
  통과.
- 같은 Dagster 의존성 환경에서 `dagster definitions validate -m kortravelgeo_dagster.definitions` 통과.
- `uv run --python 3.12 --extra api --extra dev ruff check .` 통과.
- `uv run --python 3.12 --extra api --extra dev mypy src/kortravelgeo` 통과.
- `uv run --python 3.12 --extra api --extra dev lint-imports` 통과.
- `TMPDIR=/tmp uv run --python 3.12 --extra api --extra dev pytest -q -s` → 1152 passed, 75 skipped.

## 2026-07-08 (T-290c reconciler 리뷰 후속 — terminal orphan 경로 보강, by codex)

**작업**: Claude Code의 T-290 M1 PR #419~#423을 통합 브랜치 기준으로 리뷰했다. #420의
executor-aware recovery에서 순수 reconciler는 `failed + Dagster RUNNING -> FLAG_ORPHAN`을 갖고
있지만, 실제 `reconcile_dagster_jobs()` 경로가 `state='running'` 행만 조회하고 `job_state='running'`을
하드코딩해 해당 분기가 도달 불가능한 결함을 확인했다. 상세 리뷰 코멘트는 #420, 추적 이슈는 #424에
남겼다.

**변경**:
- `JobQueue.reconcile_dagster_jobs()`가 Dagster 실행 중인 `running` 행과 terminal orphan 후보
  (`failed`/`cancelled` + `orchestrator_run_id`)를 함께 스냅샷하고, row의 실제 `state`를
  `reconcile_load_job()`에 전달하게 했다.
- app-side `cancelled` 상태에서 Dagster run이 계속 `RUNNING`인 경우도 양방향 cancel 정책상
  `FLAG_ORPHAN`으로 처리하도록 decision table과 문서를 맞췄다.
- terminal orphan 후보 scan용 partial index `idx_load_jobs_dagster_terminal_orphan`을 fresh DDL,
  `sql/indexes.sql`, alembic 0024에 추가했다.
- public reconcile path 테스트가 `failed`/`cancelled` orphan cancel hook 호출까지 검증하도록 보강했다.

**검증**:
- `TMPDIR=/tmp uv run --extra api --extra dev pytest -s -q tests/unit/test_job_recovery.py tests/unit/test_job_queue.py tests/unit/test_ops_metadata.py`
  → 38 passed.
- `uv run --extra api --extra dev ruff check src/kortravelgeo/api/_job_recovery.py src/kortravelgeo/api/_jobs.py tests/unit/test_job_recovery.py tests/unit/test_job_queue.py tests/unit/test_ops_metadata.py alembic/versions/0024_t290c_orphan_idx.py`
  통과.
- `uv run --extra api --extra dev mypy src/kortravelgeo/api/_job_recovery.py src/kortravelgeo/api/_jobs.py`
  통과.
- `uv run --extra api --extra dev ruff check .` 통과.
- `uv run --extra api --extra dev mypy src/kortravelgeo` 통과.
- `uv run --extra api --extra dev lint-imports` 통과.
- `TMPDIR=/tmp uv run --extra api --extra dev pytest -q -s` → 1152 passed, 75 skipped.

## 2026-07-08 (T-290 Dagster 이관 M1 완결 — 패키지·배포·recovery 게이트, by claude/A)

**작업**: [ADR-066](adr/066-geo-independent-dagster-orchestration.md)·[마스터플랜](dagster-migration-plan.md)의
M1(Foundation)을 완결했다. Agent A 스트림 3개 태스크가 모두 머지되고 n150에서 실검증됐다.

**머지**:
- **T-290a**(#419): `kortravelgeo_dagster` 별도 top-level 패키지 스캐폴드 + resources(4-way fallback) +
  `mv_refresh` @op/@job. `dagster definitions validate`·mypy strict·ruff·pytest 통과.
- **T-290c**(#420): `load_jobs`에 `executor`/`orchestrator_run_id`/`lease_expires_at` 컬럼(3곳 drift +
  alembic 0023) + executor별 startup recovery split + 순수 reconciler(`_job_recovery.py`) + seam
  (RunLivenessProbe/OrchestratorCancelHook). 순수 additive — 기존 in-process 실행 무변경. 전체 pytest
  1158 passed.
- **T-290b**(#421, #422): geo Dagster 런타임 이미지(멀티스테이지 Dockerfile + `dagster.yaml`) + docker-manager
  compose 3서비스(db-init/webserver/daemon) + 메타 DB `kor_travel_geo_dagster`. docker-manager 레포에도
  버전관리(manager PR #47). 웹서버 포트는 map 포트 패턴(`12X0Y`: 02=Dagster)에 맞춰 **12502**로 확정
  (초기 12703은 map 127xx 블록 침범이라 #422로 정정).

**n150 실검증(M1 게이트)**: webserver(:12502)+daemon 기동, code location `kortravelgeo_dagster.definitions`
서빙, resources(client/rustfs/settings)가 n150 앱 DB에 정상 resolve, **`mv_refresh`를 실제 Dagster run으로
실행해 SUCCESS**(6.4M×2 MV concurrent refresh, ~7.6분). 기존 geo-api/ui/postgres 무손상.

**런타임 검증이 잡은 통합 버그(성과)**: 1차 mv_refresh run이 `QueryCanceled: statement timeout`으로 실패했다.
원인은 `make_async_engine`(`infra/engine.py`)가 모든 connection에 **서빙용 `statement_timeout`**을 걸고,
`refresh_mv` leaf의 `SET LOCAL 0`이 concurrent 경로의 후속 statement(`GeoCacheRepository.clear()` 등)까지
덮지 못한 것. **근본 fix**: Dagster는 서빙이 아니라 장시간 maintenance 오케스트레이터이므로 `client`
resource engine을 `statement_timeout=0`(maintenance engine)으로 빌드(ADR-066 §7). unit/`definitions validate`로는
못 잡고 n150 런타임에서만 드러난 케이스 — 배포 게이트 검증의 가치.

**운영 교훈(기록)**: n150 동시 배포 중 geo-api가 T-290c 신 코드로 재생성됐는데 그 순간 alembic 0023이 아직
미적용이라 startup recovery 쿼리(`executor` 컬럼 참조)가 실패해 잠깐 크래시 루프했다. 0023 적용 후 자가
회복. **마이그레이션은 코드 재생성 전에** 적용해야 한다는 deploy-runbook 규칙의 실증 — 특히 여러 에이전트가
같은 n150을 동시에 만질 때 순서 보장이 중요하다.

**다음**: M2 — A는 T-290f(scheduled backup @schedule 온램프 + @run_failure_sensor), B(codex)는 T-290d/290e
관측 표면(이미 머지)을 이어 배포. M2 완료 후 **live UI e2e #1**.

## 2026-07-08 (T-290e Dagster 관리자 관측 화면, by codex)

**작업**: T-290d 관측 API가 통합 브랜치에 머지된 뒤, Agent B 범위의 M2 작업 중 독립 완료 가능한
T-290e(`/admin/dagster` 관측 화면)를 진행했다. `main`은 건드리지 않고
`agent/claude-dagster-migration`에서 분기한 PR 단위로 작업했다.

**변경**:
- `lib/dagster.ts`를 추가해 OpenAPI 생성 타입(`types/api.gen.ts`) 기반 Dagster DTO alias와
  `useDagsterSummaryQuery`, `useDagsterRunDetailQuery` React Query hook을 제공한다.
- `/admin/dagster` 페이지와 `DagsterPanel`을 추가했다. 화면은 repository/assets/jobs/failed runs
  지표, Dagster webserver sandbox iframe, recent runs 표, 선택 run event log, code locations,
  schedules/sensors tick 표를 렌더한다.
- `ADMIN_PAGES`와 사이드바/관리 홈 아이콘 매핑을 갱신해 `백업·운영` 그룹에 Dagster 링크를 추가했다.
- Dagster API의 outage 응답(`status="unavailable"`)은 오류 배너와 빈 run 상태로 표시한다. 실패/
  overdue 알림과 artifact 링크는 계획대로 T-290h 범위에 남겼다.

**검증**:
- `kor-travel-geo-ui npm run type-check` 통과.
- `kor-travel-geo-ui npm run lint` 통과.
- `kor-travel-geo-ui npm run test` → 153 passed.
- `kor-travel-geo-ui npm run build` 통과(`/admin/dagster` static route 생성 확인).
- `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, 기존 warning 9건.
- `uv run --python 3.12 --extra api --extra dev ruff check .` 통과.
- `uv run --python 3.12 --extra api --extra dev mypy --strict src/kortravelgeo` 통과.
- `uv run --python 3.12 --extra api --extra dev lint-imports` 통과.
- `uv run --python 3.12 --extra api --extra dev pytest -q -s` → 1124 passed, 75 skipped.
- `scripts/export_openapi.py --check --output openapi.json` 통과.

## 2026-07-08 (T-290d Dagster 관측 API, by codex)

**작업**: 사용자 지시대로 20분 대기 후 신규 브랜치/PR을 확인했다. Claude의 T-290 계획 문서 PR #416은
CI green 상태라 `agent/claude-dagster-migration`에 머지했고, `main`은 건드리지 않았다. 이후 Agent B
범위에서 선행 T-290a 패키지 스캐폴드 없이 독립 완료 가능한 T-290d를 먼저 진행했다.

**변경**:
- `/v1/ops/dagster/summary`, `/v1/ops/dagster/runs/{run_id}` FastAPI 라우터를 추가했다.
- `kortravelgeo_dagster`는 아직 별도 패키지이므로 main lib에는 Dagster import를 넣지 않고, API가
  Dagster webserver GraphQL을 read-only로 호출해 admin UI용 DTO로 정규화한다.
- SSRF 방어를 넣었다: `http`/`https` scheme만 허용, userinfo/query/fragment 금지, host allowlist,
  GraphQL endpoint path `/graphql` 강제.
- Dagster webserver가 내려가거나 HTTP/JSON 오류가 나면 HTTP 200 + `status="unavailable"`로 반환한다.
  GraphQL top-level error는 Python dict repr이 아니라 `message`만 노출한다.
- `KTG_DAGSTER_URL`, `KTG_DAGSTER_GRAPHQL_URL`, `KTG_DAGSTER_ALLOWED_HOSTS`,
  `KTG_DAGSTER_REQUEST_TIMEOUT_SECONDS`, `KTG_DAGSTER_REPOSITORY_NAME`,
  `KTG_DAGSTER_REPOSITORY_LOCATION_NAME` 설정 키를 추가했다.
- `docs/ports.md`에 `kor-travel-geo` Dagster webserver host 포트 `12703`을 예약했다.
- OpenAPI와 UI 생성 타입(`types/api.gen.ts`, `lib/schemas.gen.ts`)을 갱신했다.

**검증**:
- `uv run --python 3.12 --extra api --extra dev ruff check .` 통과.
- `uv run --python 3.12 --extra api --extra dev mypy --strict src/kortravelgeo` 통과.
- `uv run --python 3.12 --extra api --extra dev lint-imports` 통과.
- `uv run --python 3.12 --extra api --extra dev pytest -q -s` → 1124 passed, 75 skipped.
- `scripts/export_openapi.py`, `kor-travel-geo-ui npm run gen:types` 실행.
- UI `npm run lint`, `npm run type-check`, `npm run test`(151 passed), `npm run build` 통과.
- `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, warning 9건. 경고는 기존
  `LogsPanel`/`OpsPanel`/`HotSwapTab`/`VirtualTable`/ui primitive/auth storage 파일의 선행 경고로,
  이번 생성 타입·Dagster API 변경 파일과 무관해 PR 범위에 섞지 않았다.

## 2026-07-07 (PR #406 관리 UI 개편 n150 배포 + live UI e2e, by claude)

**작업**: 2026-07-06 codex 항목의 예고("live UI e2e는 PR #406 최종 머지 후 백업 리스토어를 제외하고
이어서 실행한다")를 이어받아, PR #406(shadcn 관리 UI 전면 개편 + `/admin/files` 파일 관리 화면 +
통합 파일 인벤토리 API, T-283)의 n150 배포와 live UI e2e를 완료했다. PR #406은 이미 main에 머지돼
있었고(CI backend/frontend/openapi green), 열린 코드 태스크는 없었다. 요청대로 backup/restore는 제외했다.

**진단(배포 전 n150 상태)**:
- 운영 스택이 **pre-#406 이미지**로 가동 중이었다(`/v1/admin/storage/files` → 404). 앱 소스는 #406이
  반영돼 있었지만 이미지가 재빌드되지 않았다.
- UI/API 컨테이너의 admin 인증 env가 **전부 빈 값**(hash/secret/proxy len 0)이라 로그인이 깨져 있었다.
  원인은 직전 재생성이 docker-manager override의 `${KTG_UI_ADMIN_PASSWORD_HASH:-}` 치환을
  `--env-file .env` 없이 수행해 조용히 빈 값으로 뜬 것(로컬 배포 런북 §1의 바로 그 함정 재현).
  시크릿 값 자체는 docker-manager `.env`에 존재했다.

**조치(배포)**:
- origin/main HEAD 소스를 n150 앱 디렉터리에 rsync 반영(`.env*`·data·artifacts·node_modules·`.next`·
  `.git`·`*.local.md` 등 제외 → prod 설정 보존).
- ktdctl과 동일한 `docker compose --env-file .env -f docker-compose.yml -f docker-compose.override.yml`
  invocation으로 **api·ui만** 재빌드·`--force-recreate`. postgres/DB는 건드리지 않았다(DB 무손상,
  backup/restore·full-load 제외).

**검증**:
- 재생성 후 컨테이너 env 복구 확인: UI hash/secret/proxy·API proxy/cidrs 모두 채워짐.
- 로그인 POST 200 + httpOnly `SameSite=Strict` 세션 쿠키, 틀린 비번 401.
- `/v1/admin/storage/files` 403(role gate — route 존재 = #406 이미지 배포 확인), readyz/healthz 200,
  v1 geocode는 구조화 vworld 에러(key 요구)로 route 정상.
- live UI e2e(`tests/e2e/live`, read-only 구성 — 공개키 mutation·rebuild opt-in 미설정): 배포된 n150
  스택 대상 **Chromium 229 passed / 4 skipped, Firefox 229 passed / 4 skipped**(각 233 project). 4 skip은
  의도된 파괴적/mutation opt-in(공개키 생성·rebuild) 2건 + 조건부(when-exists) API 2건. `/admin/files`
  파일 인벤토리 등 #406 신규 화면 렌더까지 통과.

**환경 메모(ADR-065 fallback 사유)**: n150 Linux Playwright를 먼저 시도했으나, n150 headless에 chromium
시스템 라이브러리(`libatk-1.0.so.0` 등)가 없고 passwordless sudo가 없어 브라우저 launch가 불가했다
(API 계층 186건 통과, 브라우저 45건 launch 실패). 그래서 Windows Playwright를 n150 UI(LAN) 대상으로
fallback 실행했다. n150 Linux e2e 상시화에는 n150에서 `sudo npx playwright install-deps chromium`
(+firefox) 1회가 필요하다.

## 2026-07-06 (PR #406 Claude Code 리뷰 후속 반영, by codex)

**작업**: 최근 5일(2026-07-01 KST 이후) Claude Code 공동 작성 PR을 closed 포함으로 확인했다.
GitHub 검색 결과 닫힌 대상 PR은 없고, Claude 공동 작성 커밋이 포함된 open PR #406만 대상이었다.
PR #406에 리뷰 코멘트를 남기고, 유사 항목을 #407(CRLF/후행 공백), #408(파일 인벤토리 API
정합성), #409(mypy 2.1 optional `osgeo` import ignore 코드)로 묶어 이슈화했다.

**변경**:
- PR #406 변경 파일 중 CRLF로 저장된 UI/테스트 파일 47개를 LF로 정규화하고 EOF blank line을 정리했다.
- `file_inventory_page()`가 `kind=all`에서도 category를 source group/artifact/orphan에 일관 적용하고,
  조합 후 전체 `limit`을 적용하도록 보정했다.
- source group lifecycle에서 retired/invalid 같은 과거 match set 이력과 현재 후보 match set을 분리해,
  과거 이력만 있는 파일이 `staging`으로 남지 않게 했다.
- optional GDAL import의 mypy ignore 코드를 `import-not-found`/`import-untyped` 양쪽 판정에 맞췄다.
- 위 동작을 `tests/unit/test_file_inventory.py`에 추가했다.

**검증**:
- `git diff --check origin/main` 통과.
- `uv run --extra api --extra dev ruff check src/kortravelgeo/core/file_inventory.py src/kortravelgeo/infra/file_inventory_repo.py src/kortravelgeo/client.py tests/unit/test_file_inventory.py` 통과.
- `uv run python -m mypy src/kortravelgeo/core/file_inventory.py src/kortravelgeo/infra/file_inventory_repo.py src/kortravelgeo/client.py` 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp uv run python -m pytest tests/unit/test_file_inventory.py -q` → 15 passed.
- WSL/ext4 미러 `~/dev/kor-travel-geo-codex-pr406-test`에서 `pytest -q` → 1125 passed, 67 skipped.
- 같은 미러에서 `ruff check .`, `mypy src/kortravelgeo scripts/export_openapi.py`, `lint-imports`,
  `python scripts/export_openapi.py --check --output openapi.json` 통과.
- `kor-travel-geo-ui/scripts/frontend_check.sh` 통과: types 생성, eslint, tsc, vitest 151 passed, Next build 통과.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, error 0, warning 24.
- live UI e2e는 PR #406 최종 머지 후 백업 리스토어를 제외하고 이어서 실행한다.

## 2026-06-28 (Linux-only 개발환경 정책 정리, by codex)

**작업**: 사용자 지시에 따라 개발환경 정책을 Linux-only로 전환했다. 모든 개발 명령은 WSL을 포함한 Linux
환경에서 실행하고, Git/CodeGraph도 Linux 경로 기준으로 repair·실행한다. Playwright e2e는 n150 Linux
환경에서 먼저 실행하며, 불가할 때만 Windows Playwright fallback을 사용하고 사유와 명령을 기록한다.

**문서**:
- ADR-065를 추가하고 ADR-041을 superseded 처리했다.
- `AGENTS.md`, `SKILL.md`, `README.md`, `docs/dev-environment.md`,
  `docs/runbooks/agent-workflow.md`, `docs/runbooks/agent-failure-patterns.md`,
  `docs/codegraph-worktree.md`, `docs/live-e2e.md`, `docs/geocoding-readiness.md`,
  `docs/architecture/architecture.md`, `docs/architecture/frontend-package.md`,
  `docs/code-guide-for-beginners.md`, `kor-travel-geo-ui/README.md`를 갱신했다.

**검증**:
- 문서 변경만 수행했다. 코드 테스트는 실행하지 않았다.

## 2026-06-24 (PR #403 n150 배포와 full live e2e 완료, by codex)

**작업**: concierge #127 origin allowlist 반영 PR #403을 n150에 배포하고 Windows Playwright full live
e2e를 Chromium/Firefox 모두 실행했다.

**배포**:
- `~/kor-travel-geo` 배포 복사본에 현재 PR 소스를 rsync로 반영했다. `.env`, `.env.local`, `data`,
  `artifacts`, `node_modules`, `.next`는 배포 중 보존했다.
- `~/kor-travel-docker-manager/.env.kor-travel-geo-ui.local`에 `KTG_UI_PUBLIC_ORIGINS`를 실제
  `KTDM_PROD_URL_GEO` 값으로 설정했다. 값 자체는 로그와 문서에 남기지 않았다.
- `backend/ktd_venv/bin/ktdctl ensure geo --build --recreate --stream`으로 API/UI 이미지를 빌드하고
  컨테이너를 재생성했다. 명령은 기존과 같이 `/data/juso` 원천 파일 mount empty precheck에서 exit 1로
  끝났지만, 새 API/UI 컨테이너는 healthy다.

**smoke**:
- `kor-travel-geo-api-latest`, `kor-travel-geo-ui-latest`, `kor-travel-geo-postgres` 모두 healthy.
- UI 컨테이너에 `KTG_UI_PUBLIC_ORIGINS`가 주입되어 있다.
- `/v1/readyz` 200, `/login` 200.
- `/api/auth/login` JSON POST에서 allowlisted 공개 origin은 CSRF를 통과해 잘못된 credential 기준
  `401 INVALID_CREDENTIALS`, 임의 origin은 `403 INVALID_ORIGIN`으로 갈라짐을 확인했다.
- v1 geocode smoke는 `서울특별시 중구 세종대로 110` 기준 `status=OK`,
  `bd_mgt_sn=11140103200500100011000000`, `zip_no=04524`, 좌표
  `126.97770627907322,37.56620502187806`로 응답했다.

**full live e2e**:
- Windows Playwright, n150 `PLAYWRIGHT_BASE_URL=http://192.168.1.14:12505`,
  `KTG_LIVE_E2E_API_BASE_URL=http://192.168.1.14:12501`,
  `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1`.
- Chromium: `npx playwright test --config playwright.config.ts --project chromium --workers 1 tests/e2e/live`
  → 227 passed, 3 skipped.
- Firefox: `npx playwright test --config playwright.config.ts --project firefox --workers 1 tests/e2e/live`
  → 227 passed, 3 skipped.

## 2026-06-24 (concierge #127 origin allowlist 반영과 n150 geo 데이터 확인, by codex)

**작업**: `kor-travel-concierge` PR #127의 공개 도메인 로그인 `403 INVALID_ORIGIN` 수정 내용을
`kor-travel-geo-ui`에 맞춰 반영했다. TLS 종단 프록시가 `X-Forwarded-Proto=https`를 주입하지 않아
요청 origin이 내부 `http`로 재구성되는 경우를 위해 `KTG_UI_PUBLIC_ORIGINS` 신뢰 목록을 추가했다.
브라우저 `Origin`이 재구성 origin과 다르면 명시된 공개 origin만 추가 허용하고, 그 외 외부 origin은
계속 거부한다.

**변경**:
- `requestHasSameOrigin()`이 `KTG_UI_PUBLIC_ORIGINS`를 쉼표 구분 목록으로 읽고 정상 URL origin만
  비교하도록 했다. 잘못된 설정 항목은 무시한다.
- `.env.example`, `.env.prod.example`, `kor-travel-geo-ui/.env.local.example`에 운영 설정 예시를
  추가했다.
- TLS 프록시 proto 누락 상황의 origin 허용/거부 단위 테스트를 추가했다.

**검증**:
- WSL ext4 테스트 미러에서 `npm run test -- tests/unit/auth.test.ts`, `npm run type-check`,
  `npm run lint -- --no-warn-ignored`를 통과했다.
- WSL ext4 테스트 미러에서 `scripts/frontend_check.sh`를 통과했다.
- WSL ext4 테스트 미러에서 `npx react-doctor@latest . --offline --verbose --json`을 실행해
  `ok=true`, error 0, warning 0, diagnostics 0을 확인했다.
- n150 PostgreSQL의 `public.tl_juso_text`와 `public.mv_geocode_target`은 각각 6,416,637행이다.
- n150 API에서 `서울특별시 중구 세종대로 110` v1 geocode smoke가 `status=OK`, 좌표
  `126.97770627907322,37.56620502187806`, `bd_mgt_sn=11140103200500100011000000`,
  `zip_no=04524`로 응답했다.
- n150의 API 컨테이너 `/data/juso` 원천 파일 mount는 비어 있다(`0` files). 따라서
  docker-manager의 source-file precheck는 `/data/juso` empty로 실패할 수 있지만, 현재 DB 적재
  데이터와 API serving 경로는 정상이다.

## 2026-06-24 (PR #402 n150 배포와 풀 live e2e 완료, by codex)

**작업**: PR #402(`agent/codex-auth-followups-pr37-pr38`)를 n150에 배포하고 Windows Playwright로
n150 대상 풀 live e2e를 Chromium/Firefox 모두 실행했다.

**배포**:
- n150 실제 SSH 계정은 `digitie@192.168.1.14`이며, `~/kor-travel-geo`는 Git checkout이 아니라
  rsync 배포용 복사본이다. `.env*`, `data`, `artifacts`, `node_modules`, `.next`는 보존하고 현재 PR
  소스를 rsync로 반영했다.
- `~/kor-travel-docker-manager`에서 `backend/ktd_venv/bin/ktdctl ensure geo --build --recreate --stream`을
  실행해 API/UI 이미지를 새 소스로 빌드하고 컨테이너를 재생성했다.
- manager의 후속 source check는 `/data/juso`가 비어 있어 `source directory is empty: /data/juso`로
  exit 1을 반환했다. 다만 API/UI 컨테이너는 새 이미지로 기동했고 `/v1/readyz` 200, `/login` 200,
  `kor-travel-geo-api-latest`/`kor-travel-geo-ui-latest` healthy를 확인했다.

**live e2e**:
- Windows Playwright, n150 `PLAYWRIGHT_BASE_URL=http://192.168.1.14:12505`,
  `KTG_LIVE_E2E_API_BASE_URL=http://192.168.1.14:12501`,
  `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1`.
- Chromium: `npx playwright test --config playwright.config.ts --project chromium --workers 1 tests/e2e/live`
  → 227 passed, 3 skipped.
- Firefox: `npx playwright test --config playwright.config.ts --project firefox --workers 1 tests/e2e/live`
  → 227 passed, 3 skipped.
- 최초 Chromium run에서 `client_ip_hash`를 항상 요구하던 live spec 기대치가 실패했다. n150처럼
  `KTG_UI_TRUSTED_PROXY_HOPS=0`인 직접 노출 UI는 spoof 가능한 `X-Forwarded-For`를 버리므로
  `client_ip_hash`가 비는 것이 의도된 정책이다. live spec은 client IP hash를 optional로 보되
  user-agent hash는 계속 요구하도록 보정했다.

**PR 상태**: PR #402 head `712463e` 기준 GitHub CI `backend`/`frontend`/`openapi`는 모두 green이었다.
문서 기록 커밋 후 CI를 재확인하고 머지한다.

## 2026-06-24 (React Doctor 경고 0 정리와 n150 live e2e 준비, by codex)

**작업**: 사용자 추가 지시에 따라 Admin 보안 후속 변경 위에서 React Doctor 경고를 모두 제거했다.
기존 중간 일지의 warning 34 상태에서 이어서 UI 접근성, hook 구조, 대형 컴포넌트, false-positive 항목을
정리했다.

**변경**:
- `ManifestViewer`, `ConsistencyPanel`, `ReconcileTab`의 role 기반 모달을 native `dialog`로 바꿨다.
- `VirtualTable`의 virtualized grid에서 semantic table role 흉내를 제거하고 clickable row keyboard
  activation을 보강했다.
- `HotSwapTab`, `RestoreWizard`, `UploadTab`, `ReconcileTab`의 다중 상태를 reducer와 하위 패널로
  정리해 React Doctor hook/giant component 경고를 제거했다.
- component 파일의 non-component export를 `manifest-utils`, `restore-reconcile-utils`, `map-utils`로
  분리했다.
- VWorld 관련 테스트의 storage 접근은 test-only 우회 함수로 감싸 `auth-token-in-web-storage`
  false-positive를 제거했다.

**검증**:
- WSL backend 전체: `python -m pytest -q` → 1110 passed, 67 skipped
- WSL backend 정적 게이트: `ruff check .`, `mypy src/kortravelgeo scripts/export_openapi.py`,
  `lint-imports`, `python scripts/export_openapi.py --check --output openapi.json` → 통과
- WSL frontend 전체: `scripts/frontend_check.sh` → gen:types/lint/type-check/unit/build 통과
- WSL React Doctor: `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, error 0,
  warning 0, diagnostics 0

**다음**: PR을 열고 n150에 배포한 뒤 Windows Playwright로 n150 풀 live e2e를 실행하고, 통과 후 머지한다.

## 2026-06-24 (Admin 보안 후속 — docker-manager #37/#38 대응 반영, by codex)

**작업**: `kor-travel-docker-manager` PR #37/#38의 auth fix-forward 항목을 `kor-travel-geo` 구조에 맞춰
반영했다. CORS 항목은 이 프로젝트가 브라우저 → Next.js BFF → FastAPI 내부 호출 구조라
`CORSMiddleware`를 쓰지 않아 적용 대상이 아니다. metrics service 항목도 docker-manager 전용이라 제외했다.

**변경**:
- Admin 로그인은 username이 틀려도 PBKDF2를 수행해 username timing 차이를 줄인다.
- 로그인 rate limit은 backend `ops.audit_events`의 `admin_auth.login` 이벤트를 우선 조회해 durable하게
  판단하고, audit 조회가 실패하면 기존 process-local limiter로 fallback한다.
- 로그아웃 감사 이벤트는 유효 세션 쿠키가 실제로 폐기된 경우에만 기록한다.
- 공개 API key 검증의 process-local TTL cache와 `KTG_PUBLIC_API_KEY_CACHE_TTL_S` 설정을 제거했다. v1/v2
  공개 API는 요청마다 DB의 활성 key hash를 조회하므로 key 폐기가 다른 API worker에도 즉시 반영된다.
- Admin Settings의 생성된 1회성 공개 API key 영역에 `지우기` 버튼을 추가했다.

**문서**: ADR-064, frontend/backend architecture 문서, CHANGELOG를 갱신했다.

**검증(진행 중)**:
- WSL targeted backend: `python -m pytest tests/unit/test_public_api_key.py tests/unit/test_admin_auth_events.py -q`
  → 12 passed
- WSL targeted backend lint: `ruff check src/kortravelgeo/api/public_api_key.py src/kortravelgeo/infra/public_api_keys.py src/kortravelgeo/settings.py tests/unit/test_public_api_key.py`
  → 통과
- WSL targeted UI: `npm run test -- tests/unit/auth.test.ts` → 7 passed
- WSL UI: `npm run type-check` → 통과
- WSL UI: `npm run lint -- --no-warn-ignored` → 통과
- WSL backend 전체: `python -m pytest -q` → 1110 passed, 67 skipped
- WSL backend 정적 게이트: `ruff check .`, `mypy src/kortravelgeo scripts/export_openapi.py`, `lint-imports`,
  `python scripts/export_openapi.py --check --output openapi.json` → 통과
- WSL frontend 전체: `scripts/frontend_check.sh --install` 및 재동기화 후 `scripts/frontend_check.sh`
  → gen:types/lint/type-check/unit/build 통과
- WSL React Doctor: `npx react-doctor@latest . --offline --verbose --json` → `ok=true`, error 0,
  warning 34. 이번 변경으로 새로 생겼던 `LoginForm` autofocus 경고는 제거했다.

**다음**: Windows Playwright local/live e2e, n150 배포와 운영 live e2e를 이어서 수행한다.

## 2026-06-23 (Admin 로그인·공개 API key 보안과 live e2e, by codex)

**작업**: 사용자 요청에 따라 Admin UI 로그인과 공개 REST API key 검증을 추가했다. UI는 단일
admin 계정 로그인, httpOnly `SameSite=Strict` 세션 cookie, user-agent fingerprint, logout revocation,
로그인 rate limit을 사용한다. API는 trusted admin proxy shared secret과 proxy peer 검증을 거쳐
admin API 및 공개 API key 검증 우회를 분리한다. 공개 v1/v2 API는 VWorld 호환 `key` query parameter를
요구하며, 활성 DB key가 없을 때만 `KTG_VWORLD_API_KEY`를 기본 key로 인정한다. UI에서 생성한 key는
plaintext를 한 번만 보여 주고 DB에는 hash와 hint만 저장한다.

**변경**: `ops.public_api_keys` migration과 repository/cache를 추가했고, Admin UI `/admin/settings`에
key 생성·목록·폐기 및 로그인 기록 패널을 추가했다. 로그인 시도·성공·실패·로그아웃 이벤트는
`ops.audit_events`에 저장하며 client IP/user-agent는 hash로만 저장한다. ADR-013은 superseded로 표시하고
ADR-064를 추가했다. `kor-travel-map` #508과 같은 prod endpoint 노출 패턴을 확인해 이 저장소의 stale
local endpoint 예시를 placeholder로 redaction했다.

**검증/배포**: WSL ext4 미러에서 backend 전체 `pytest -q` 1107 passed/67 skipped, `ruff check .`,
`mypy src/kortravelgeo`, `lint-imports`, OpenAPI `--check`를 통과했다. UI는 `npm run type-check`,
`npm run test` 129건, `npm run lint`, `npm run build`, React Doctor(`ok=true`, warning 33건)를 통과했다.
로컬 production Docker API/UI를 재빌드·재기동하고 migration `0022_public_api_keys`를 적용한 뒤 Windows
Playwright live e2e를 Chromium/Firefox 모두 실행했다. mutation 허용 로컬 production run은 각 browser
230건 중 222 passed/8 skipped였고, 신규 auth/public-key live spec은 각 browser 7/7 통과했다. 이후 운영
호스트에 소스와 prod-only env/compose override를 반영하고 API/UI 이미지를 재빌드, migration 적용,
컨테이너 재기동, `/v1/readyz`와 `/login` smoke를 완료했다. 운영 전체 live e2e는 prod DB key row 생성을
피하려고 `KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS`를 끈 상태로 Chromium/Firefox 각 230건 중 221 passed/9 skipped를
확인했다.

## 2026-06-21 (Admin UI live e2e 2배 추가 증설, by codex)

**작업**: 사용자 추가 요청에 따라 `tests/e2e/live/*`의 라이브 풀스택 테스트를 81개에서 223개로
다시 늘렸다. 공개 API read-only 행렬 94개와 admin API query 행렬 48개를 더해, v1/v2 geocode·reverse·
search·zipcode·pobox·within-radius, validation 실패, tables/logs/backups/jobs/loads/consistency/
audit/snapshots/releases/artifacts/maintenance/cache/source catalog GET 계약을 촘촘히 검증한다.

**결정**: 추가된 행렬도 모두 same-origin UI proxy를 통과하는 live read-only 테스트로 제한했다.
admin API는 GET만 호출하고, 공개 API 행렬은 상태 변경이 없는 검색·조회와 입력 검증 실패만 다룬다.

**검증**: Windows Playwright `--list tests/e2e/live` 기준 446건(Chromium/Firefox 2 project,
단일 project 223건)을 확인했다. WSL 미러의 Next 서버를 새로 올려 Windows Playwright 전체 live suite
9개 spec을 실행했고 446건 중 430건 통과·16건 skip이었다. skip은 `source_file_viewer` role과
destructive rebuild opt-in 환경이 없는 기본 live 실행에서 기대되는 건이다. WSL ext4 테스트 미러에서
UI `type-check`, `lint`, unit test 123건, `build`, React Doctor(`ok=true`, 기존 UI 경고 33건)를
다시 통과했다.

## 2026-06-21 (Admin UI live e2e 커버리지 증설, by codex)

**작업**: 사용자 요청에 따라 mock 기반 e2e가 아니라 `tests/e2e/live/*`의 라이브 풀스택 admin UI
테스트를 22개에서 81개로 늘렸다. 추가 테스트는 실 백엔드+실 DB를 대상으로 하며, API read-only
계약 30개와 브라우저 read-only 화면/탭 검증 29개를 더했다.

**결정**: live admin 테스트는 파괴적 작업을 누르지 않는 읽기 전용 검증으로 유지했다. 백업/복원,
rebuild, reconcile 실행, hard-delete 같은 상태 변경은 트리거하지 않고, role-gated source-files read는
`KTG_LIVE_E2E_ADMIN_PROXY=1`과 `source_file_viewer` role이 있을 때만 실행되도록 분리했다.

**검증**: Windows Playwright `--list tests/e2e/live`로 162건(Chromium/Firefox 2 project 기준,
단일 project 81건)을 확인했다. WSL ext4 테스트 미러에서 UI `type-check`, `lint`, unit test 123건,
`build`, React Doctor(`ok=true`, 기존 UI 경고 33건)를 통과했다. 이후 WSL 미러의 Next 서버를 새로
올려 Windows Playwright로 admin live 3개 spec(`admin-readonly`, `admin-api-readonly`,
`admin-browser-readonly`)을 Chromium/Firefox 양쪽에서 실행했고, 132건 중 118건 통과·14건
role-gated skip이었다.

## 2026-06-20 (PR #384/#392 Claude Code post-merge 리뷰 후속, by codex)

**작업**: 사용자 요청에 따라 2026-06-19 KST 이후 Claude Code가 올린 PR을 closed 포함으로
확인했다. 대상은 #384(dev/prod 환경 분리)와 #392(Tailwind v4 전환)였고, conversation comment,
review body, inline review thread를 모두 확인했다. 두 PR 모두 unresolved thread는 0건이고 CI는
green이었다.

**변경**: #384 후속으로 `scripts/docker_app.sh`의 `KTG_ENV_FILE=.env.dev` 같은 상대 경로를 repo
root 기준으로 해석하게 했다. `kor-travel-geo-ui/README.md`와 `docs/live-e2e.md`의 Docker/dev
실행 설명을 현재 host network + `12501`/`12505` dev 프로파일로 맞췄고,
`CHANGELOG.md`와 `docs/postmerge-review-fixups-pr384-pr392.md`에 #384/#392 리뷰 후속을 기록했다.

**검증**: WSL ext4 미러에서 `bash -n scripts/docker_app.sh`, 전체 `pytest -q`
(`1094 passed, 67 skipped`), `ruff check .`, `mypy src/kortravelgeo scripts/export_openapi.py`,
`lint-imports`, OpenAPI `--check`를 통과했다. UI는 stale `node_modules` 때문에 첫
`scripts/frontend_check.sh`가 `@tailwindcss/postcss` 부재로 실패했으나, `--install` 재실행으로
gen:types/lint/type-check/unit 123건/build가 통과했다. React Doctor는 `ok=true`, 기존 warning
31건이다. Windows Playwright는 WSL UI server `12515`에 붙여 Chromium/Firefox
`navigation.spec.ts`와 `vworld-map.spec.ts` 각 3건을 통과했다.

## 2026-06-20 (kor-travel-geo-ui Tailwind v4 전환, by claude)

**작업**: 사용자 요청으로 admin UI(`kor-travel-geo-ui`)를 Tailwind CSS v3 → v4로 전환했다.
형제 `kor-travel-map` admin은 이미 v4였고 geo-ui만 v3였다.

**결정**: 회귀 위험 최소화를 위해 **@config 보존 방식**을 택했다. `tailwind.config.ts`
(테마/색 토큰 매핑)를 그대로 두고 `app/globals.css`에서 `@config "../tailwind.config.ts"`로
로드한다. `@tailwind base/components/utilities` → `@import "tailwindcss"`, postcss는
`tailwindcss`+`autoprefixer` → `@tailwindcss/postcss`, deps는 `tailwindcss@^4`+
`@tailwindcss/postcss`로 올리고 `autoprefixer` 제거. 컴포넌트는 이미 v4 호환 idiom
(`ring-3`, `shadow-[var(--shadow-*)]`, `outline-none`)이라 유틸리티 rename은 불필요했다
(bare ring/shadow/border 사용 0).

**검증**: `tailwindcss@4.3.1` 설치 후 UI `type-check`·`lint`(0)·`build`(컴파일 성공,
17 static pages)·`test`(28 files / 123 passed) 통과. 시각 회귀(Playwright e2e)는
남은 게이트 — 테마/유틸리티 무변경이라 위험은 낮다.

## 2026-06-20 (T-278 Admin UI Next 기본 오류 화면 복구 보강)

**작업**: 사용자가 Firefox에서 Admin UI가 `This page couldn’t load` / `Reload to try again, or go back.`
기본 오류 화면으로 떨어진다고 보고했다. 과거 브라우저 공통 재현 이력을 다시 확인하고 #390/T-278로
분리했다. 현재 live Docker UI에서는 즉시 재현되지는 않았지만, 기본 오류 화면이 사용자에게 그대로
노출되는 방어 공백을 닫았다.

**결정**: App Router segment/global error boundary를 추가해 Next 기본 영어 오류 화면 대신 한국어
복구 패널을 보여 준다. chunk/RSC/network 계열 런타임 오류는 sessionStorage flag로 같은 pathname당
1회 hard reload를 시도하고, 반복 실패는 재시도/이전 화면/오류 정보 패널로 남긴다. `/admin/ops`
성능·검증 요약에 남아 있던 `next/link` 상세 이동은 `DocumentNavLink`로 바꿔 `_rsc` client routing
요청을 만들지 않는다.

**검증**: WSL ext4 미러에서 UI `type-check`, `lint`, targeted unit, `build`, 전체 unit,
React Doctor(`ok=true`, 기존 warning 31건), `scripts/frontend_check.sh`를 통과했다. Docker UI를
재빌드/재기동한 뒤 Windows Playwright Firefox `navigation`/`ops-perf-summary`/`vworld-map` 5건,
Chromium `navigation`/`ops-perf-summary` 3건을 통과했고, `http://127.0.0.1:12505/debug/geocode`와
`/api/proxy/v1/healthz`가 HTTP 200을 반환했다.

## 2026-06-20 (T-219 잔여 L v1/OpenAPI 계약 정리)

**작업**: T-219 잔여 low-priority 항목을 `codex/t219-v1-compat-minors`에서 처리했다.
보조 API contract 에이전트 검토를 받아 v1 Starlette 404/405, coordinate bounds 문구,
ADR-053 문서 gap, non-vworld OpenAPI `422` drift를 확인했다.

**결정**: v1 404/405는 `/v1/address/geocode`·`/v1/address/reverse`처럼 operation을
명확히 결정할 수 있는 경로만 VWorld error envelope로 감싼다. coordinate bounds는 한글 범위
메시지로 통일하되 v1은 VWorld `INVALID_RANGE`, v2는 `E0102`를 유지한다. v2에서 폐기한
`StructuredErrorEnvelope`는 되살리지 않고, legacy non-vworld 경로 문서화용
`LegacyErrorEnvelope`를 OpenAPI component로 추가한다.

**검증**: Windows quick check로 targeted pytest 55건과 ruff를 통과했다. NTFS 변경 파일을
WSL ext4 미러에 반영한 뒤 OpenAPI `--check`, targeted pytest 55건, backend 전체
`pytest` 1086 passed/75 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`,
UI lint/type-check/unit/build를 통과했다. React Doctor는 `ok=true`였고 기존 UI 경고 31건을
보고했다.

## 2026-06-20 (T-177H 벤치마크 수용 완료)

**작업**: PR #387(T-197 REST 벤치마크 client disconnect cancellation 오탐 수정)을 머지한 뒤,
`codex/t177h-benchmark-acceptance`를 `origin/main`
`2a3bee2b3db5675e39066abb31029feaa5b66573` 위로 리베이스했다. 사용자 지시에 따라 다음
벤치마크 전 `README.md`, `SKILL.md`, runbook, architecture/resume/ADR/tasks, `docs/ports.md`,
`docs/dev-environment.md`, T-177 계획, `.env.dev.example`, `.env.prod.example`,
`kor-travel-geo-ui/.env.local.example`를 다시 읽었다.

**결정**: 새 prod 정의는 공식 도메인과 `.env.prod` 기준이므로, T-177H는 prod가 아니라 dev
프로파일 기준으로 명시한다. API는 WSL ext4 테스트 미러에서 `127.0.0.1:12501`에만 띄우고,
PostgreSQL은 이미 동작 중인 `127.0.0.1:5432`의 T-177G DB
`kor_travel_geo_t177g_codex_20260618133300`에 접속했다. 저장소 정책대로 PostgreSQL/RustFS
생명주기는 조작하지 않았다.

**검증**: SQL 벤치마크 산출물
`/home/digitie/dev/kor-travel-geo-codex-test/artifacts/perf/t177h-sql-20260619T182225Z`는
18,000 measurement/error 0, 최악 p95 SQL c64 `Q4_SEARCH/search_fuzzy` 146.225ms를 기록했다.
REST 벤치마크 산출물
`/home/digitie/dev/kor-travel-geo-codex-test/artifacts/perf/t177h-rest-20260619T182653Z`는
21,600 measurement/error 0, 최악 p95 REST c64
`Q8_NO_RESULT/geocode_no_result_road` 406.511ms를 기록했다. 벤치마크 뒤 dev API 프로세스는
종료했고 `12501` 포트가 비었음을 확인했다. 최종 판정은
`docs/t177h-benchmark-acceptance.md`에 남겼다.

## 2026-06-19 (T-197 REST benchmark client disconnect cancellation 오탐 수정)

**작업**: T-177H REST benchmark를 T-177G DB
`kor_travel_geo_t177g_codex_20260618133300`에 붙인 dev API(`127.0.0.1:12501`)로 실행하자,
client error 4,104건(`Server disconnected without sending a response`)과 API
`CancelledError` 로그가 반복됐다. 문제를 #386/T-197로 분리하고 T-177H를 일시 중단했다.

**결정**: `ClientDisconnectCancellationMiddleware`가 `http.disconnect`에서 app task를 cancel한
직후 receive task와 app task가 동시에 완료되면, app task의 `CancelledError`가 ASGI error로
흐를 수 있었다. middleware가 응답 완료 여부를 추적하게 하고, disconnect receive task가
완료된 경우를 우선 처리해 정상 취소를 흡수하도록 고쳤다. body streaming 중 실제 disconnect와
빈 body GET 실행 중 disconnect는 계속 app task를 취소하며, 응답 완료 뒤 들어온 disconnect만
정상 응답을 취소하지 않는다.

**검증**: WSL ext4 미러에서 targeted
`tests/unit/test_api_app_contract.py::test_client_disconnect_cancels_public_address_request_while_body_streams`
와
`tests/unit/test_api_app_contract.py::test_client_disconnect_after_empty_body_cancels_public_get`,
`tests/unit/test_api_app_contract.py::test_disconnect_after_response_complete_does_not_cancel_public_request`
3건을 포함한 `test_api_app_contract.py` 전체 8건을 통과했다. 패치된 API로 같은 SQL corpus REST full benchmark
`t197-rest-disconnect-fix-20260619T175900Z`를 실행해 21,600 measurement, error 0을 확인했다.
dev API 프로세스는 종료했고 `12501` 포트가 비었음을 확인했다.

## 2026-06-19 (T-183 UI 기반 full-load 적재 e2e 완료)

**작업**: PR #383(T-196) 머지 뒤 `codex/t183-ui-full-load-e2e`를 `origin/main`의
dev/prod 환경 분리 정의(#384) 위로 리베이스하고 관련 문서(`docs/ports.md`,
`docs/t108-deploy-automation.md`, `.env.*.example`, runbook)를 다시 읽었다. 새 정의에 맞춰
다음 live 검증은 prod 도메인이 아니라 dev 기본 포트(API `12501`, UI `12505`)에서 수행했다.

**결정**: T-183 live run은 이미 완료된 `source_rebuild_db`
`job_5e7106d5ca58414f86f1bc7d26953f35` / `full_load_batch`
`batch_66a52eb91d9c4833b1e8763cf1ec72e0`를 채택해 post-load serving evidence를 재검증했다.
이전 Playwright 실패는 실제 적재 실패가 아니라 forced promotion 근거를
`dataset_snapshot.metadata`에서 찾던 테스트 계약 오류였다. API 응답 정본은
`dataset_snapshot.source_set.rebuild_metadata`와 `serving_release.consistency_gate`이므로 live
spec을 그 구조에 맞췄다. Admin UI에는 rebuild control job과 downstream batch 진행 상태를
보여 주는 패널을 추가해 실제 UI에서 적재 진행을 추적할 수 있게 했다.

**검증**: `kor_travel_geo_t213_20260615_r3` DB에 API/UI를 붙여 Windows Playwright live e2e
`tests/e2e/live/source-files-rebuild-live.spec.ts`를 Chromium/Firefox에서 각각 1/1 통과했다.
최종 serving release는 `b232a167-682d-4e5c-b197-577f617e5107`, snapshot은
`6fb47bac-dccd-4791-a39f-f2f1e712689e`이며 row count는
`mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`,
`tl_juso_text=6,419,795`, `tl_juso_parcel_link=1,771,043`이다. 산출물은
`artifacts/t183/t183-ui-rebuild-20260618T120705Z/t183-ui-rebuild-live.json`에 남겼다. WSL
프론트 게이트 `scripts/frontend_check.sh`는 lint/type-check/unit 120건/build까지 통과했고,
React Doctor는 `ok=true`로 종료했다(기존 warning 31건, 이번 변경 파일 신규 warning 없음).

## 2026-06-19 (T-196 rebuild-db materialize OOM 완화)

**작업**: T-195 force-promotion live UI e2e 재시도에서 UI POST와 `source_rebuild_db`
control job 생성은 성공했지만, RustFS materialize 단계가 `[Errno 12] Cannot allocate memory`로
실패했다(#382). 실패 job payload에는 `force_promotion=true`, actor/reason이 정상 기록됐고,
API/UI는 계속 응답했다.

**결정**: 대형 materialize category(`navi_full`, `electronic_map_full`)가 포함된 rebuild는
압축 해제를 한 번에 하나만 수행하도록 제한했다. 내비게이션 `.7z` 해제는 `7z` 출력을
메모리 `PIPE`로 누적하지 않고 임시 파일로 흘린 뒤 tail만 읽으며, `-mmt=1`로 내부 thread
메모리 사용을 줄인다. materialize 실패 메시지에는 `category/source_file_group_id`를 포함해
다음 live 실패 때 어느 원천에서 터졌는지 바로 볼 수 있게 했다.

**검증**: WSL ext4 테스트 미러에서
`python -m pytest tests/unit/test_t189_rebuild_materialize.py -q` 13건을 통과했다. 이후
`python -m pytest -q` 1075건 통과(75 skipped), `ruff check .`,
`python -m mypy src/kortravelgeo`, `lint-imports` 통과. PR로 머지하고 T-183/T-195 live UI e2e를
다시 시작한다.

## 2026-06-19 (아키텍처 문서 UI 테이블 의존성 정정)

**작업**: `docs/architecture/architecture.md`의 프론트엔드 테이블 항목이 여전히
native table 우선, TanStack Table 후속 승격으로 설명되어 있어 현재 UI 구현과 달랐다.
실제 `kor-travel-geo-ui`는 `@tanstack/react-table`과 `@tanstack/react-virtual` 기반
공용 `VirtualTable`로 관리 UI 표면을 통일했다.

**결정**: `architecture.md`와 `frontend-package.md`를 현재 구현 기준으로 정정했다.
지도 의존성은 `maplibre-vworld-js`가 아니라 ADR-063의 `maplibre-vworld-react` 기준을
유지한다.

**검증**: 문서 변경만 수행했다. `rg`로 `docs/architecture/architecture.md`에
`maplibre-vworld-js`가 남아 있지 않고, 테이블 설명이 `TanStack React Table` /
`TanStack React Virtual` 기준으로 바뀐 것을 확인했다.

## 2026-06-18 (T-193 text loader event loop starvation 해소)

**작업**: T-183 live UI e2e 재개 중 `source_rebuild_db` 제어 job과 RustFS materialize는
완료됐지만, downstream batch의 첫 `juso_text_load` child가 시작된 뒤 `/v1/healthz`,
`/v1/readyz`, `/v1/admin/jobs/{job_id}`가 60초 이상 응답하지 않았다. 원인은 대용량 text
loader handler가 row parsing/COPY loop를 API main asyncio event loop 안에서 직접 실행한
것으로 보고 #376으로 분리했다.

**결정**: text 계열 loader handler만 coroutine factory를 worker thread의 별도 event loop에서
실행하도록 `_run_loader_off_event_loop()`를 추가했다. SHP/SPPN은 이미 내부에서 worker thread를
사용하고 있고, `source_rebuild_db` materialize는 이번 재현에서 status polling이 가능했으므로
범위를 넓히지 않았다.

**검증**: WSL ext4 테스트 미러에서 targeted
`tests/unit/test_api_app_contract.py::test_loader_thread_wrapper_keeps_api_event_loop_responsive`를
통과했다. 이후 `python -m pytest -q` 1072건 통과(75 skipped), `ruff check .`,
`python -m mypy src/kortravelgeo`, `lint-imports` 통과. PR 머지 뒤 T-183 live UI e2e를
처음부터 다시 실행한다.

## 2026-06-18 (T-192 JobQueue drain nudge/exception logging)

**작업**: T-183 live UI e2e 재개 중 `rebuild-db` POST가 200을 반환하고
`source_rebuild_db` 제어 job을 만들었지만, live API에서 job이 `queued`에 머물고
`log_tail=[]` 상태로 worker progress가 기록되지 않는 문제를 #374로 분리했다.

**결정**: `JobQueue.enqueue()` 직후 drain task가 방금 commit된 queued row를 놓치거나
advisory lock이 잠깐 busy인 상태를 queue empty처럼 처리하지 않도록, 즉시 drain과 짧은 지연
nudge를 함께 등록하고 lock busy는 backoff 후 재시도한다. queue semaphore가 있어 중복 drain은
직렬화된다. drain task가 실패하면 `logger.exception`으로 회수해 live 로그에서 원인을 볼 수
있게 했다.

**검증**: WSL ext4 테스트 미러에서 targeted `tests/unit/test_job_queue.py`와
`tests/unit/test_t189_rebuild_materialize.py` 13건을 먼저 통과했다. 이후
`python -m pytest -q` 1071건 통과(75 skipped), `ruff check .`,
`python -m mypy src/kortravelgeo`, `lint-imports` 통과. T-183 live UI e2e는 PR 머지 뒤
재개한다.

## 2026-06-18 (T-191 rebuild-db audit outcome 제약 위반 수정)

**작업**: T-183 live UI e2e 재시작 중 `rebuild-db` 버튼이 `source_rebuild_db` 제어 job을
enqueue한 뒤 HTTP 500(`database statement failed`)을 반환했다. 원인은 enqueue 직후
`ops.audit_events.outcome`에 `queued`를 기록했지만, 실제 CHECK 제약과 DTO 계약은
`started`/`succeeded`/`failed`/`cancelled`/`denied`만 허용하는 불일치였다. 실행 중이던
실패 재현 job은 `/v1/admin/jobs/{job_id}/cancel`로 취소했다.

**결정**: HTTP 요청은 `source_rebuild_db` 제어 job을 시작시키는 lifecycle 이벤트이므로
새 outcome을 추가하지 않고 기존 허용값인 `started`를 기록한다. route unit test도 이 값을
계약으로 고정한다.

**검증**: WSL ext4 테스트 미러에서 targeted
`tests/unit/test_t189_rebuild_materialize.py` 10건, `python -m pytest -q` 1068건 통과(75 skipped),
`ruff check .`, `python -m mypy src/kortravelgeo`, `lint-imports` 통과. T-183 live UI e2e는
PR 머지 뒤 재개한다.

## 2026-06-18 (T-190 rebuild-db 요청 timeout 해소)

**작업**: Admin UI live T183 `rebuild-db` 요청이 Next.js proxy 5분 timeout
(`UND_ERR_HEADERS_TIMEOUT`)에 걸리고, backend가 `pg_try_advisory_lock` 뒤
idle-in-transaction 연결을 유지한 채 RustFS materialize를 계속하던 문제를 백엔드에서
T-190/#370으로 분리해 수정했다. `POST /v1/admin/source-match-sets/{id}/rebuild-db`는 이제 즉시
`source_rebuild_db` 제어 job을 영속 큐에 넣고 반환한다. 제어 job이 기존
`prepare_source_match_set_rebuild()` 경로로 integrity gate와 RustFS materialize를 수행한 뒤
기존 `full_load_batch`를 enqueue한다.

**결정**: full async 재설계 대신 최소 변경으로 `load_jobs` 기반 제어 job을 추가했다. 제어
job은 `full_load_batch`가 생성되면 `load_batch_id`로 연결해 진행 상황을 추적할 수 있게 했다.
`source_rebuild_db`를 batch successor 계산의 control kind에 포함해 consistency가 조기 enqueue되지
않게 했고, session advisory lock helper는 lock/unlock 직후 commit해 장시간 lock 보유 중
idle-in-transaction 상태를 만들지 않게 했다.

**검증**: WSL ext4 테스트 미러에서 targeted pytest 44건을 먼저 통과한 뒤
`python -m pytest -q` 1068건 통과(75 skipped), `ruff check .`,
`python -m mypy src/kortravelgeo`, `lint-imports` 통과. 실제 T183 live UI 재실행은
아직 미검증이다.

## 2026-06-18 (라이선스 GPL-3.0-only 전환)

**작업**: 사용자 요청에 따라 프로젝트 라이선스 표기를 MIT에서 `GPL-3.0-only`로
변경했다. 공식 FSF GPLv3 본문을 `LICENSE`로 추가하고, `pyproject.toml`의 license
metadata/classifier, README badge와 법적 고지, `CHANGELOG.md`를 함께 갱신했다.

**결정**: "GPL3" 요청은 별도 `or later` 명시가 없으므로 `GPL-3.0-only`로 해석했다.
현재 reference 문서의 MIT 현재형 문구는 "당시 MIT"로 고쳤다. 기존 작업 로그의
과거 항목은 당시 의사결정 기록이므로 소급 수정하지 않았다.

**검증**: `rg`로 현재 표기 대상의 `MIT` 잔존 여부를 확인하고, license metadata와 README
로컬 `LICENSE` 링크를 확인한다. 코드 동작 변경은 없어 전체 테스트는 실행하지 않는다.

## 2026-06-18 (README 중복 정리)

**작업**: 사용자 요청에 따라 `README.md`를 정리했다. README에 길게 복제되어 있던
진행 상황 목록, 상세 개발환경 절차, ADR 표, 외부 API 세부 설명, VWorld/MapLibre 세부
설명을 줄이고, 각각의 정본 문서(`docs/resume.md`, `docs/dev-environment.md`,
`docs/architecture/*`, `docs/adr/README.md`, `docs/architecture/external-apis.md`)로
연결했다.

**결정**: README는 새 진입자가 "무엇인지"와 "어디를 읽을지"를 판단하는 입구 문서로
유지하고, 변경 가능성이 높은 실측 상태와 운영 절차는 세부 문서에만 둔다. Python 지원
버전 badge도 `pyproject.toml`의 `requires-python >=3.12`와 맞췄다.

**검증**: 문서 전용 변경이라 코드 테스트는 실행하지 않았다. README의 로컬 링크와
마크다운 구조를 별도로 확인한다.

## 2026-06-18 (T-189 rebuild-db RustFS staging materialize 누락 수정)

**작업**: T-183 live UI full-load e2e 준비 중 Admin UI에서 `rebuild-db`를 실제 enqueue했지만,
backend가 RustFS registry 객체를 로컬 staging으로 materialize하지 않은 채
`rebuild_staging/<match-set>/<category>` 상대 경로만 batch payload에 넣어 loader가
`text source path does not exist`로 실패했다. 이를 #367/T-189로 분리해
`prepare_source_match_set_rebuild()`가 integrity gate 통과 뒤 RustFS 객체를 다운로드하고
loader별 입력 형태로 풀어 둔 다음 batch를 enqueue하도록 고쳤다.

**결정**: UI/API의 `rebuild-db` 경로는 기본적으로
`settings.rustfs_materialize_dir/rebuild_staging/<source_match_set_id>/run_<uuid>` 아래에
category별 staging을 만든다. 같은 match set 재시도가 이전 loader 입력을 지우지 않도록
attempt-scoped 경로를 사용한다. 도로명주소 한글 원천은 같은 staging path를 공유하는
`juso_text_load`와 `juso_parcel_link_load` 두 child로 fan-out하며, FK 순서가 뒤집히지 않도록
batch child `created_at`에 microsecond offset을 부여한다. 기존 T-213 live pipeline은 자체
artifact staging을 사용하므로 `materialize=False`로 기존 동작을 유지한다.

**검증/문서**: materializer 단위 테스트는 텍스트 ZIP 추출, 전자지도 시도별 ZIP 추출, ZIP-aware
loader 입력 보존, generic RustFS object key 충돌 회피, roadname fan-out을 고정한다. Windows와
WSL ext4 미러에서 T189 타깃 pytest 55건을 통과했고, WSL 전체 backend gate는 pytest
1072건, ruff, mypy, lint-imports를 통과했다. T-183 live UI e2e는 이 PR 머지 뒤 같은
DB/RustFS로 재시작한다.

## 2026-06-18 (T-184 opt-in live e2e admin role proxy)

**작업**: T-183 UI 기반 적재 e2e의 선행 조건으로, Next.js `/api/proxy`가 live e2e에서만
backend admin role gate용 `X-KTG-Actor`/`X-KTG-Roles`를 주입할 수 있게 했다. 기본 allow-list는
`accept`/`content-type`/`user-agent`만 유지하고, 브라우저가 직접 보낸 `X-KTG-*` 헤더는 계속
버린다.

**결정**: role header는 `KTG_LIVE_E2E_ADMIN_PROXY=1`, `KTG_LIVE_E2E_ADMIN_ACTOR`, 유효한
`KTG_LIVE_E2E_ADMIN_ROLES`가 모두 있을 때만 주입한다. role 문자열은 backend
`KNOWN_ADMIN_ROLES`와 같은 `source_file_viewer`/`source_file_manager`/`rebuild_operator`/
`destructive_admin`으로 제한하고, `system`이나 미지 role은 버린다. backend 쪽 trust 경계는
기존 `KTG_ADMIN_TRUSTED_PROXY_CIDRS`를 사용한다.

**검증/문서**: WSL ext4 미러에서 `api.test.ts` 7/7과 production `next build`를 통과했다.
fresh T-177G DB `kor_travel_geo_t177g_codex_20260618133300`에 API/UI를 붙여
`/api/proxy/v1/admin/source-file-categories`와 `/api/proxy/v1/admin/source-match-sets?limit=5`
가 각각 200을 반환함을 확인했고, Windows Playwright
`tests/e2e/live/admin-readonly.spec.ts`는 chromium 7/7 통과했다. `docs/live-e2e.md`에는
T-184 env 예시와 source-files RBAC 제약 갱신을 추가했다.

## 2026-06-18 (T-177G/T-188 전국 long-run full-load e2e 완료)

**작업**: T-177G fresh run `t177g-codex-20260618T022500Z-fresh-t187`는 전국 원천 적재와
serving MV swap까지 완료했지만, `postload_serving_smoke_consistency`에서 smoke sample SQL이
전국 `mv_geocode_target` 후보를 `ORDER BY CASE WHEN EXISTS (...)`로 정렬하다
`statement_timeout`에 걸렸다. 이를 #364/T-188로 분리했다.

**결정**: smoke sample은 acceptance용 대표 row 1건이면 충분하므로 전체 후보 정렬을 없앴다.
기존 T-177F acceptance의 `has_locsum_link is True` 의미는 유지하기 위해 locsum-linked entrance
row를 `LIMIT 1`로 고르고, 선택된 단일 `bd_mgt_sn`에 대해서만 roadaddr link 여부를 확인한다.
이 쿼리는 실패 DB에서 0.028초, 전체 smoke report는 0.097초에 완료됐다.

**검증/문서**: 실패 DB `kor_travel_geo_t177g_codex_20260618112500`에서 post-load phase를 다시
실행해 1,466.775초에 성공했고, release `585e4e86-6ed7-4287-9d58-7d7b70615a99`와 snapshot
`8206cafa-e271-4307-9a9c-ff7e2ba2c468`을 기록했다. 이후 fresh scratch DB
`kor_travel_geo_t177g_codex_20260618133300`에서 run
`t177g-codex-20260618T043300Z-fresh-t188`를 처음부터 다시 실행해 2:05:08에 통과했다.
성공 artifact는 `artifacts/t177/t177g-codex-20260618T043300Z-fresh-t188/t177g-nationwide-longrun-full-load.json`이고,
DB 크기는 35GB, serving MV 2종은 각각 6,419,795행이다. 같은 DB에 API/UI를 붙여 Windows
Playwright live e2e `tests/e2e/live`를 chromium으로 실행했고 20/20 통과했다.

## 2026-06-18 (T-277 `maplibre-vworld-react` 지도 전환)

**작업**: 사용자 지시에 따라 디버그 UI 지도를 GitHub `digitie/maplibre-vworld-react` 기반으로
전환했다. npm registry에는 공개 package가 없어 GitHub tarball
`a7cb0f8f41ec00b44b1d106664506730b87033bd`를 고정했고, 기존
`maplibre-vworld-js`/`maplibre-vworld` dependency는 제거했다. `kor-travel-geo-ui/lib/vworld.ts`는
`packages/vworld-map-web/src/*` source의 `VWorldMapView`, `Marker`, map hook, VWorld helper를
재수출하고, `CoordinateMap`은 click callback, key 미설정 preview, tile error overlay 임계치,
API 응답 geometry overlay만 계속 domain wrapper로 담당한다.

**결정**: `maplibre-vworld-react` root tarball은 monorepo source를 포함하고
`vworld-map-web`이 bare import `vworld-map-core`를 사용하므로, TypeScript/Vitest/Next webpack뿐
아니라 Next.js 16 Turbopack `resolveAlias`도 함께 둔다. 전역 CSS는 package CSS가 아니라
`maplibre-gl/dist/maplibre-gl.css`를 import한다. 새 core style source id는 `vworld-base`와
`vworld-satellite` 기준으로 테스트를 갱신했다. 의존성 선택은 ADR-063에 기록하고,
ADR-020/028/032는 최신 의존성 선택만 ADR-063으로 넘긴다.

**검증**: WSL ext4 테스트 미러에서 `npm ci`, `npm run lint`, `npm run type-check`,
`npm run test`(27 files / 118 tests), `npm run build`, `npx react-doctor@latest . --offline --verbose --json`을
실행했다. React Doctor는 exit 0이지만 기존 source-files/VirtualTable 계열 경고 29건이 남아 있어
이번 변경 범위에서는 수정하지 않았다. Windows Playwright는 WSL production `next start` 서버에 붙여
`tests/e2e/vworld-map.spec.ts`를 `chromium`과 `firefox` project에서 각각 2/2 통과시켰다.

## 2026-06-18 (T-185/T-186 T-177G DB live UI e2e 선행 검증)

**작업**: T-183/T-184 진행 전에 T-177G로 적재된
`kor_travel_geo_t177g_codex_20260618073652` DB를 API/UI에 붙여 Windows Playwright live UI e2e를
먼저 실행했다. 첫 실행은 20건 중 19건이 통과했고, `/admin/ops` read-only 테스트만
`ops.serving_releases=0`, `ops.dataset_snapshots=0` 때문에 실패했다. 동시에 T-177G pytest
후처리 실패 원인인 link evidence 집계가 SQL 최적화 뒤에도 기본 `statement_timeout=5s`에
걸릴 수 있음을 #359/T-185로, ops ledger 공백을 #360/T-186으로 분리했다.

**결정**: timeout은 전역 설정을 바꾸지 않고 T-177G post-load 호출에서만
`statement_timeout=0`을 `SET LOCAL`로 적용한다. T-177G의 serving MV swap 뒤에는 새 ledger
로직을 만들지 않고 기존 `AdminRepository.record_mv_refresh_release()`를 재사용해
`ops.dataset_snapshots`와 active `ops.serving_releases`를 남긴다. 이 hook은 기존 active release를
transaction 안에서 supersede하므로 live UI가 기대하는 운영 표면과 같다.

**검증/문서**: 실제 T-177G DB에서 link evidence는
`text_rows=6419795`, `locsum_rows=6405091`, `locsum_resolved_rows=2905941`,
`locsum_serving_rows=2905941`, `locsum_smokeable_serving_rows=2905941`을 9.784초에 반환했다.
같은 DB에 release `e2f5c948-b64c-4f08-a618-d20c7bb84653`와 snapshot
`d27900cc-41a0-49e4-bdc7-97c7f4e81ea5`를 기록한 뒤, live UI e2e
`tests/e2e/live`는 20/20 통과했다. 2026-06-16 이후 PR 리뷰/코멘트를 다시 훑었고,
PR #318/#319 지적은 #320/T-269에서 이미 닫혔으며 마지막 T-181 머지 이후 새 Claude Code
후속 코멘트는 없었다. T-177G 본체는 fresh scratch DB 재실행 전까지 진행 중으로 유지한다.

## 2026-06-17 (T-182 T-177G long-run 디스크 여유 preflight)

**작업**: T-177G를 T-181 fix 포함 새 scratch DB에서 재실행하던 중, artifact materialize가
약 19GB까지 진행되고 도로명주소 한글 적재가 시작된 뒤 PostgreSQL 5432 연결 거부와 WSL
`Bus error`/`Input/output error`가 발생했다. Windows `C:` 여유가 약 2.5GB였고, WSL 기본 명령
(`/bin/true`, `/bin/pwd`, `ls`, `df`, `dmesg`)도 실패해 #355/T-182로 분리했다.

**결정**: 이 저장소는 DB/WSL을 직접 재시작하지 않으므로, long-run e2e가 환경을 망가뜨리기
전에 중단해야 한다. T-177G 전용으로 artifact filesystem free space를 먼저 검사하고, 기본
요구량을 120GiB로 둔다. 로컬 장비별 여유 공간 정책은 `KTG_TEST_FULL_LOAD_E2E_LONGRUN_MIN_FREE_GB`
환경변수로 명시 override한다.

**검증/문서**: 단위 테스트는 기본 요구량, override, 부족 시 `T177PreflightError` 메시지를
고정한다. T-177G success/failure artifact에는 통과한 disk space report를 함께 남긴다.
현재 WSL/DB 런타임은 외부 복구가 필요하므로, 복구 뒤 fresh scratch DB로 T-177G를 다시 실행한다.

## 2026-06-17 (T-181 전국 long-run 링크 증거 집계 timeout 해소)

**작업**: T-177G 전국 long-run full-load e2e 중 실제 전국 원천 적재와 serving MV swap까지
완료된 뒤, 후처리 smoke의 위치정보요약DB 링크 증거 집계가 `statement_timeout`으로 실패하는
문제를 #353/T-181로 분리했다.

**결정**: 실패한 쿼리는 `mv_geocode_target` 전체 row에서 `tl_locsum_entrc` 존재 여부를
`EXISTS`로 세는 형태였다. 전국 DB에서는 같은 증거를 더 안정적으로 수집하기 위해
`tl_locsum_entrc`의 resolved `bd_mgt_sn` distinct key를 `MATERIALIZED` CTE로 먼저 만들고,
unique `mv_geocode_target.bd_mgt_sn`과 조인한다. 전역 timeout 설정은 바꾸지 않는다.

**검증/문서**: 실패 DB `kor_travel_geo_t177g_codex_20260617183049`에서 새 쿼리가
`text_rows=6419795`, `locsum_rows=6405091`, `locsum_resolved_rows=2905941`,
`locsum_serving_rows=2905941`, `locsum_smokeable_serving_rows=2905941`을 약 10초에 반환했다.
회귀 테스트는 링크 증거 SQL이 materialized locsum key 조인을 쓰고 `WHERE EXISTS`로 되돌아가지
않음을 고정한다. T-181 PR 머지 뒤 T-177G는 fresh scratch DB에서 다시 실행한다.

## 2026-06-17 (T-177F post-load serving/smoke/consistency fast-sample e2e)

**작업**: T-177 파일 기반 full-load e2e의 다섯 번째 구현 Task로 실제 텍스트 snapshot,
위치정보요약DB, 전자지도 SHP, 도로명주소 출입구 정보, `TL_SPPN_MAKAREA` fast-sample을 한
scratch PostGIS DB에 적재한 뒤 post-load serving 표면을 검증하는 opt-in 테스트를 추가했다.

**결정**: 현재 보존 원천에는 materialize되지 않은 daily ZIP과 7z 내비게이션용DB만 있어,
T-177F는 T-177C helper를 그대로 재사용하지 않고 도로명주소 한글 snapshot과 위치정보요약DB를
직접 적재하는 전용 fast-sample helper를 둔다. fresh DB에서는 `refresh_mv(strategy="swap")`보다
`rebuild_mv()`가 단순하고 안정적인 serving 구축 표면이므로, 링크 해소 뒤
`resolve_text_geometry_links()`와 `rebuild_mv()`를 실행한다. 서비스 캐시가 post-load smoke를
가릴 수 있으므로 T-177F smoke client는 cache를 끄고, smoke 직전 `geo_cache`를 비운다. C1~C10
consistency severity는 fast-sample의 원천 기준월 혼합과 제한된 row 수 때문에 acceptance gate로
보지 않고, SQL 실행과 artifact 생성 smoke로만 검증한다.

**검증/문서**: `tests/integration/_t177_full_load_harness.py`에 T-177F text snapshot load,
위치정보요약DB 링크 evidence, serving object/index report, cache-off API-level smoke,
consistency report helper를 추가했다. `tests/integration/test_t177_file_driven_full_load_e2e.py`는
opt-in 상태에서 `t177f-postload-serving-smoke.json` artifact를 쓰고, GDAL Python binding이
없으면 skip한다. WSL scratch DB `kor_travel_geo_t177f_codex_20260617181345`에서 실제 opt-in 한
건이 통과했으며 `mv_geocode_target=34`, `mv_geocode_text_search=34`, `region_radius_parts=271`,
`load_consistency_reports=1`, `locsum_smokeable_serving_rows=33`, geocode/reverse/search/zipcode
smoke `OK`, geocode/reverse source `local`을 확인했다. 다음 PR은 T-177G 전국 long-run full-load
e2e다.

## 2026-06-17 (T-177E 선택 보강 원천 fast-sample e2e)

**작업**: T-177 파일 기반 full-load e2e의 네 번째 구현 Task로 실제 도로명주소 출입구 정보와
`TL_SPPN_MAKAREA` 원천을 scratch PostGIS DB에 적재하는 opt-in 테스트를 추가했다.

**결정**: fast-sample은 전국 전체가 아니라 세종 ZIP 단일 파일을 선택한다. `roadaddr_entrance`
원천은 폴더월 `202604`와 ZIP 내부 `RNENTDATA_2605_*` 파일명월이 다르므로, loader 호출 시
`source_yyyymm=None`을 넘겨 파일명 기준월 `202605`를 row/manifest에 기록한다. SPPN 원천은
실제 보존 경로 `구역의도형/202603`과 과거 문서 경로 `구역의 도형`을 모두 discovery 후보로
본다. core `reverse_geocode()`는 serving MV를 요구하므로 T-177E에서는
`ReverseRepository.sppn_areas()`까지를 reverse smoke로 보고, MV 기반 reverse smoke는 T-177F로
분리한다.

**검증/문서**: `tests/integration/_t177_full_load_harness.py`에 T-177E source 선택, table reset,
manifest, SRID/validity, SPPN geocode/reverse repository smoke, C10 report helper를 추가했다.
`tests/integration/test_t177_file_driven_full_load_e2e.py`는 opt-in 상태에서
`t177e-supplemental-fast-sample-load.json` artifact를 쓰고, GDAL Python binding이 없으면 skip한다.
WSL scratch DB `kor_travel_geo_t177e_codex_20260617173732`에서 실제 opt-in 한 건이 통과했다.
다음 PR은 T-177F post-load serving, smoke, consistency e2e다.

## 2026-06-17 (T-177D 전자지도 SHP/PostGIS geometry fast-sample e2e)

**작업**: T-177 파일 기반 full-load e2e의 세 번째 구현 Task로 실제 전자지도 SHP를 selected
시도 단위로 scratch PostGIS DB에 적재하는 opt-in 테스트를 추가했다.

**결정**: SHP loader에는 공개 `layers=`/row limit 옵션이 없으므로 private `_load_plans_sync()`에
의존하지 않는다. 대신 전자지도 월 폴더에서 세종 ZIP 또는 dataset을 우선 선택하고, 없으면
이름순 첫 시도 원천을 고른다. ZIP 원천은 artifact 작업 디렉터리에 materialize한 뒤 공개
`load_shp_polygons(mode="full")` API로 serving 9개 레이어를 모두 적재한다. 적재 뒤 CLI/API와
같은 후처리 의미를 확인하기 위해 `refresh_region_radius_parts()`도 실행한다.

**검증/문서**: `tests/integration/_t177_full_load_harness.py`에 T-177D source 선택, SHP row
guard, table count, SRID 5179, `ST_IsValid`, source metadata, `region_radius_parts` report helper를
추가했다. `tests/integration/test_t177_file_driven_full_load_e2e.py`는 opt-in 상태에서
`t177d-shp-geometry-fast-sample-load.json` artifact를 쓰고, GDAL Python binding이 없으면 skip한다.
다음 PR은 T-177E 선택 보강 원천 e2e다.

## 2026-06-17 (T-180 SHP invalid geometry repair)

**작업**: T-177D 실제 opt-in 실행 중 세종 202604 전자지도 SHP 적재 결과에서
`ST_IsValid(geom)=false` row가 남는 문제를 #348/T-180으로 분리했다.

**결정**: `ogr2ogr` subprocess를 도입하지 않고 기존 GDAL Python binding 적재 경로를 유지한다.
대신 SHP geometry target table 적재가 끝난 직후 target table별 DDL geometry type에 맞춰
`ST_MakeValid`와 `ST_CollectionExtract`를 적용하고 SRID 5179 `MultiPolygon`/`MultiLineString`으로
되돌린다. geometry가 없는 `tl_sprd_intrvl`은 repair 대상에서 제외한다.

**검증/문서**: `tests/unit/test_shp_loader_gdal.py`가 repair가 analyze 전에 실행되고
`tl_sprd_manage`/`tl_spbd_buld_polygon` repair type이 target DDL과 맞는지 고정한다. 이 fix를
main에 먼저 머지한 뒤 T-177D opt-in e2e를 다시 실행한다.

## 2026-06-17 (T-177C 텍스트 정본/daily delta fast-sample e2e)

**작업**: T-177 파일 기반 full-load e2e의 두 번째 구현 Task로 실제 텍스트 계열 원천 fast-sample DB 적재 테스트를 추가했다.

**결정**: 테스트는 `scripts/fullload_test.sh`를 재사용하지 않고, `load_juso_hangul`, `load_juso_parcel_link_snapshot`, `load_daily_juso_delta`, `load_daily_parcel_link_delta`, `load_locsum`, `load_navi`, `resolve_text_geometry_links()`를 직접 호출한다. 지번 링크 loader의 FK 제약 때문에 sample 지번/daily LNBR 행의 parent `tl_juso_text` row를 먼저 seed한다. 기본 sample limit은 2행이고 `KTG_TEST_FULL_LOAD_E2E_SAMPLE_LIMIT`로 조정한다.

**검증/문서**: `tests/integration/_t177_full_load_harness.py`에 T-177C source path, target reset, loader 실행, table count, manifest, 링크 해소 metric helper를 추가했다. `tests/integration/test_t177_file_driven_full_load_e2e.py`는 opt-in 상태에서 `t177c-text-delta-fast-sample-load.json` artifact를 쓰고 `load_manifest`와 링크 해소 전후 수치를 검증한다. 다음 PR은 T-177D 전자지도 SHP/PostGIS geometry e2e다.

## 2026-06-17 (T-177B opt-in full-load e2e 하니스)

**작업**: T-177 파일 기반 full-load e2e의 첫 구현 Task로 opt-in pytest 하니스와 destructive preflight를 추가했다.

**결정**: 하니스는 `KTG_TEST_FULL_LOAD_E2E=1`, `KTG_TEST_PG_DSN`, `KTG_TEST_FULL_LOAD_E2E_CONFIRM="RUN-T177-E2E <database>"`를 모두 요구한다. DB 이름은 `t177`/`test`/`scratch` 계열 scratch DB만 허용하고, 기존 row가 있으면 typed confirmation만으로는 부족하게 두어 `KTG_TEST_FULL_LOAD_E2E_ALLOW_NONEMPTY=1`을 별도로 요구한다. 저장소는 PostgreSQL을 구동/정지하지 않고, 이미 떠 있는 DB에 schema/index smoke만 수행한다.

**검증/문서**: `tests/integration/_t177_full_load_harness.py`가 data-root discovery plan과 JSON artifact를 만들고, `tests/integration/test_t177_file_driven_full_load_e2e.py`가 opt-in DB preflight를 수행한다. 기본 CI에서는 skip되며 `tests/unit/test_t177_full_load_harness.py`가 env gate, confirmation, non-empty guard, discovery artifact shape를 검증한다. 다음 PR은 T-177C 텍스트 정본/daily delta 실제 파일 적재 e2e다.

## 2026-06-17 (T-179 CI GDAL 설치 hardening)

**작업**: PR #344의 backend CI가 `Install GDAL system libraries` 단계에서 장시간 진행 중으로 멈춘 문제를 #345/T-179로 분리했다.

**결정**: backend workflow는 외부 apt mirror/network/lock 상태에 직접 의존하므로, job 전체 timeout과 GDAL 설치 step timeout을 명시한다. `apt-get update`에는 retry를 두고, install에는 `Dpkg::Lock::Timeout`, `--no-install-recommends`, `DEBIAN_FRONTEND=noninteractive`를 적용해 실패가 무기한 대기로 바뀌지 않게 한다.

**검증/문서**: `.github/workflows/ci.yml`, `CHANGELOG.md`, `docs/tasks-done.md`, `docs/resume.md`를 갱신한다. 이 PR이 머지되면 #344를 최신 main으로 갱신하거나 CI를 재실행해 T-177B를 계속 진행한다.

## 2026-06-17 (T-177A 파일 기반 full-load e2e 계획)

**작업**: 사용자의 "T-073 스크립트에 맞추지 말고 e2e 테스트가 파일을 읽어 DB를 구축" 지시에 맞춰 T-177 테스트 계획을 먼저 검토하고 Task로 쪼갰다.

**결정**: T-177은 shell script 재실행이 아니라 pytest opt-in integration/e2e 트랙으로 진행한다. 테스트는 `KTG_TEST_PG_DSN`으로 이미 떠 있는 scratch PostgreSQL/PostGIS에 접속하고, `KTG_TEST_FULL_LOAD_E2E=1`과 typed confirmation, DB 이름 allowlist를 모두 요구한다. Loader Python API가 실제 파일 discovery/parse/load를 수행하고, fast sample e2e에서 전국 long-run e2e와 benchmark acceptance로 확장한다.

**검증/문서**: `docs/t177-file-driven-full-load-e2e-plan.md`를 추가하고 `docs/tasks.md`에 T-177B~T-177H를 등록했다. T-178a~T-178f 선행 리뷰 후속은 모두 완료됐으므로 다음 PR부터 T-177B 하니스 구현에 들어간다.

## 2026-06-17 (T-178f RustFS HEAD/size 정직화)

**작업**: #336/T-178 선행 리뷰 후속 중 PR #290 Claude Code 코멘트를 반영했다. RustFS HEAD 오류와 `content-length` 부재가 missing 또는 size `0`으로 뭉개지던 경로를 분리했다.

**결정**: RustFS HEAD 404만 object missing으로 본다. 그 밖의 HEAD 오류나 불완전한 HEAD 응답(`content-length` 부재/비정수/음수)은 숨기지 않는다. Restore/relink/source-reconcile처럼 상태를 바꾸는 경로는 비-404 HEAD 오류를 실패로 드러내고, 백업 manifest inventory처럼 best-effort인 경로는 `head_error` status/count로 기록한다. 진짜 0바이트와 알 수 없는 크기를 섞지 않기 위해 `head.size or 0/None` 패턴을 제거했다.

**검증/문서**: RustFS transport, backup source inventory, manifest source reconcile 단위 테스트에 404/missing과 head_error/불완전 응답 분리 회귀를 추가했다. 이로써 T-178a~T-178f 선행 리뷰 후속은 모두 닫혔다.

## 2026-06-17 (T-178e pg_stat snapshot retention)

**작업**: #336/T-178 선행 리뷰 후속 중 PR #253 Claude Code 코멘트를 반영했다. `ops.pg_stat_statements_snapshots`가 주기 capture로 무한 증가하지 않도록 retention 설정과 pruning 경로를 추가했다.

**결정**: 기본 보존 기간은 7일로 두고, capture interval이 켜져 있을 때 scheduler와 수동 Admin API capture가 모두 같은 retention 정책을 탄다. 삭제는 `pg_stat_statements` capture advisory transaction lock을 잡은 같은 transaction 안에서 실행해 중복 scheduler worker 간 pruning 경쟁을 줄인다. `retention_days < 1` 직접 호출은 방금 캡처한 row까지 지울 수 있으므로 입력 오류로 막는다.

**검증/문서**: `tests/unit/test_ops_metadata.py`와 `tests/unit/test_settings.py`에 설정 기본값, scheduler 전달, 저장소 pruning SQL 회귀를 추가했다. 남은 선행 후속은 T-178f RustFS HEAD/size 정직화 하나다.

## 2026-06-17 (T-178d DBAPIError 분류)

**작업**: #336/T-178 선행 리뷰 후속 중 PR #266 Claude Code 코멘트를 반영했다. `DBAPIError` handler가 모든 DBAPI 오류를 transient 503으로 접던 것을 `OperationalError`/connection-invalidated와 그 밖의 DBAPI 오류로 분리했다.

**결정**: 연결 단절·운영 장애는 기존 503 `database operation failed`와 retry 안내 hint를 유지한다. `ProgrammingError`/`IntegrityError` 같은 SQL/schema/constraint 오류는 재시도 가능한 운영 장애로 보이지 않도록 500 `database statement failed`로 반환한다. 두 경로 모두 SQL/parameter는 응답에 노출하지 않는다.

**검증/문서**: `tests/unit/test_api_responses.py`에 legacy/v1 VWorld shape의 운영 DB 오류와 비운영 DBAPI 오류 회귀 테스트를 추가했다. `docs/tasks.md`의 선행 후속은 T-178e~T-178f만 남았다.

## 2026-06-17 (T-178c 번호형 가지도로 파싱)

**작업**: #336/T-178 선행 리뷰 후속 중 PR #277 Claude Code 코멘트를 반영했다. `테헤란로1길 10`, `올림픽로35길 123-4` 같은 번호형 가지도로를 도로명으로 보존하도록 `_ROAD_RE`를 보정했다.

**결정**: `로/대로 + 숫자 + 길`은 건물번호가 아니라 도로명 suffix의 일부로 우선 인식한다. 건물번호 없는 `올림픽로35길` 같은 road-name-only 입력은 `35`를 건물번호나 지번으로 소비하지 않고 `InvalidAddressError`로 남겨, v2 geocode의 도로 도형 fallback 경로가 처리하게 한다.

**검증/문서**: T-165 normalization 테스트에 번호형 가지도로 full address 2건과 road-name-only negative 2건을 추가했다. `docs/tasks.md`의 선행 후속은 T-178d~T-178f만 남았다.

## 2026-06-17 (T-178b cache write best-effort)

**작업**: #336/T-178 선행 리뷰 후속 중 PR #285 Claude Code 코멘트를 반영했다. Geocode/reverse OK 응답을 계산한 뒤 `geo_cache` write가 실패해도 응답이 500으로 바뀌지 않게 했다.

**결정**: cache read 실패는 기존처럼 호출 경로에서 오류를 드러내지만, cache write는 결과 저장 부가 경로이므로 best-effort로 처리한다. 실패 시 warning log만 남기고 uncached 응답을 반환한다.

**검증/문서**: T-156 cache 단위 테스트에 geocode/reverse write 실패 회귀 테스트를 추가했다. `docs/tasks.md`의 선행 후속은 T-178c~T-178f만 남겼다.

## 2026-06-17 (T-178a Claude Code 리뷰 후속)

**작업**: 2026-06-16 이후 PR을 Closed 포함해 훑고, 리뷰 반영 PR은 제외한 뒤 Claude Code 코멘트 중 미반영으로 보이는 6건을 #336/T-178로 분리했다. 그중 T-178a로 PR #248 코멘트를 먼저 반영했다.

**결정**: v2 geocode의 보조 road 후보 조회는 primary geocode OK 응답을 보강하는 best-effort 경로다. 따라서 보조 조회 실패는 warning log만 남기고 이미 계산된 primary 응답을 반환한다. `InvalidAddressError` 이후의 fallback 후보 조회는 primary 응답이 없으므로 기존처럼 실패를 드러낸다.

**검증/문서**: `tests/unit/test_v2_api.py`에 보조 `GeometryRepository.road_geometries()` 실패 시 primary 후보가 유지되는 회귀 테스트를 추가했다. 남은 T-178b~T-178f는 `docs/tasks.md`에 열린 선행 리뷰 후속으로 등록했다.

## 2026-06-17 (T-119/T-139 종료 판정)

**작업**: `docs/tasks.md`에서 `T-119`를 보류 항목에서 제거하고 완료/종료 항목으로 이동했다. `T-139`도 조건부 대기 항목에서 제거하고 완료/종료 항목으로 이동했다. `docs/resume.md`의 현재 기준과 "다음 한 작업"도 두 task가 잔여로 보이지 않도록 갱신했다.

**결정**: `T-119`는 T-137 최종 gate와 T-153 acceptance 근거에 따라 C11 active serving promotion no-go로 닫는다. C11은 validation-only로 고정하며, 향후 새 같은 기준월 C11 원천 또는 동등한 새 증거가 있으면 기존 task 재개가 아니라 신규 task/ADR과 사용자 명시 승인으로 다룬다. `T-139`는 T-153 기준 구조적 성능 blocker가 없어 별도 변경 DB 실험을 no-action 종료한다.

**검증/문서**: 문서-only 변경이다. `CHANGELOG.md`에도 backlog 종료 기준을 기록했고, `git diff --check`로 공백 오류를 확인했다.

## 2026-06-16 (Timescale PostgreSQL 계열 Codex skill 변환)

**작업**: `timescale/pg-aiguide`의 `skills/` 하위 Claude Code용 skill 8종을 Codex repo-scoped skill 형식으로 변환해 `.agents/skills/`에 추가했다. Codex frontmatter에는 `name`/`description`만 남기고, 원본 `license`/`compatibility`/source URL은 본문 상단에 보존했다. `postgres` 통합 skill의 reference 파일은 Windows에서 symlink 텍스트로 남지 않도록 실제 대상 내용을 펼쳐 넣었다.

**결정**: subagent는 `.codex/agents`, skill은 Codex 공식 repo discovery 위치인 `.agents/skills`를 사용한다. `agents/openai.yaml`은 `skill-creator` 스크립트로 생성한다. 원본 skill 본문은 제공자 원문이므로 영어를 유지한다.

**검증/문서**: `quick_validate.py`로 8개 skill 모두 검증했고, YAML frontmatter가 `name`/`description`만 갖는지 별도 파싱으로 확인했다. 같은 agent/skill 구성을 `F:\dev` 바로 아래 다른 Git repo 78개에도 복사했고, 모든 대상이 agent 6개와 skill 8개를 갖는 것을 확인했다. `.codex/agents`와 `.agents/skills`는 어느 대상 repo에서도 ignore되지 않아 `.gitignore` 추가 수정은 없었다.

## 2026-06-16 (Codex 프로젝트 subagent 정의 등록)

**작업**: VoltAgent core-development subagent 6종(`api-designer`, `backend-developer`, `frontend-developer`, `mobile-developer`, `ui-designer`, `ui-fixer`)을 프로젝트 `.codex/agents/`에 추가해 Git 추적 대상 구성으로 옮겼다. 기존 사용자 전역 `C:\Users\digit\.codex\agents` 복사본도 같은 값으로 맞췄다.

**결정**: 모든 subagent의 `model`은 `gpt-5.5`, `model_reasoning_effort`는 `xhigh`로 통일한다. 프로젝트 `.codex/agents/`가 전역 agent보다 우선하므로 이 저장소에서는 repo-scoped 정의를 기준으로 사용한다.

**검증/문서**: Python `tomllib`로 전역/프로젝트 TOML 12개를 파싱하고 `name`, `description`, `developer_instructions`, model 설정을 확인했다. 코드 변경이 아니라 pytest/Ruff/mypy는 실행하지 않았다.

## 2026-06-16 (T-153 최종 안정화 acceptance)

**작업**: Agent A 성능·정확도 트랙과 Agent B Admin UI·백업/복원 트랙을 `docs/t153-final-stabilization-acceptance.md`로 묶었다. Golden corpus, C1~C17, SQL/REST c64 budget, Admin UI Playwright, 백업/복원 round-trip·fault injection·hot-swap, React Doctor, OpenAPI/typegen drift를 같은 수락 표로 정리했다.

**결정**: T-153은 "새 release blocker 없음"으로 완료한다. C1~C10 `ERROR`는 T-213 r3 force promotion의 known source-quality 상태로 유지하고, C11 active serving promotion은 T-137 결론대로 금지한다. 실제 60분 live soak, N150/Odroid 실측, T-219 published contract 정합, T-105 audit 이후 ADR-060 반영 backlog는 T-153 blocker가 아니라 별도 잔여다. 사용자 지시에 따라 T-246은 acceptance 근거로만 인용하고 추가 작업·추가 리뷰는 하지 않는다.

**검증/문서**: React Doctor hard error 3건(`JobProgress` prop-state sync, `MatchSetComparePanel` query result 구독, `useModalA11y` dependency)을 정리했다. WSL ext4 미러에서 backend pytest 997 passed/69 skipped, Ruff, mypy, import-linter, OpenAPI check, frontend `gen:types`/lint/type-check/unit 110/build를 통과했다. React Doctor는 `ok=true`, warning 16, error 0이며 생성 타입 drift는 0이다.

## 2026-06-16 (T-127 optional source 구조 validator 강화)

**작업**: `core.source_validation`에 optional single-file category 6종(`detail_address_db_full`, `national_point_grid_shape`, `national_point_grid_center`, `civil_service_institution_map`, `address_db_full`, `building_db_full`)의 상세 구조 profile을 추가했다. `infra.source_member_scan`은 UTF-8 flag가 없는 legacy ZIP member name을 CP949로 복원하고, member filename에서 기준월을 감지한다. `national_point_grid_center` catalog의 `expected_member_kinds`는 실제 `SPPN_*.TXT` 원천에 맞춰 `grid_center_txt`로 정정했다.

**결정**: T-216 수용 결과를 깨지 않도록 `.prj` 누락은 계속 `warning`이다. 필수 TXT prefix, SHP layer, `.shp/.shx/.dbf` sidecar 누락은 `failed`로 좁혔다. 한 archive 안에서 여러 기준월이 감지되면 `warning`으로 기록한다.

**검증/문서**: Windows에서 `PYTHONPATH=src`를 명시하고 focused pytest 61개와 변경 파일 Ruff를 통과했다. WSL ext4 테스트 미러에서는 전체 pytest 990 passed/61 skipped, Ruff, mypy, import-linter, OpenAPI drift check를 통과했다. 실제 보존 원천 smoke는 `data/juso/unused` 또는 `F:/dev/geodata/juso/unused`가 있을 때만 ZIP 중앙 디렉터리를 읽고, 현재 6개 실제 archive는 기대 결과(`national_point_grid_shape`만 `.prj` 없음 warning, 나머지 passed)를 만족했다. 상세는 `docs/t127-optional-source-validator.md`에 기록했다.

## 2026-06-16 (T-158 slow-query·overload 구조화 로깅)

**작업**: `ops.slow_observability_samples`와 Alembic `0021_t158_slow_observability`를 추가했다. `infra.slow_observability`가 느린 API 요청, admission overload, 느린 DB query를 sample rate·최소 간격·queue 크기로 제한해 큐에 넣고, API lifespan flush task가 batch insert한다. DB query metric hook은 `ops_slow_samples_enabled=true`일 때만 slow query callback을 설치한다.

**결정**: 기본은 비활성이다. 원문 SQL, query parameter, 주소 문자열은 저장하지 않고 `query_fingerprint`와 literal 마스킹 `query_preview`만 남긴다. Optional plan은 `KTG_OPS_SLOW_QUERY_EXPLAIN_ENABLED=true`일 때 `SELECT`/`WITH` 쿼리에 한해 `EXPLAIN (FORMAT JSON)`으로 수집하며 `ANALYZE`는 사용하지 않는다. Admission timeout은 `sample_type="overload"` 표본으로 기록하되 raw 요청 값은 저장하지 않는다.

**검증/문서**: Windows 집중 검증에서 T-158/관측성 관련 단위 테스트 42개 통과, 변경 파일 Ruff 통과, `mypy`는 변경 infra 모듈 3개 기준 통과했다. Windows 전체 app mypy는 기존 GDAL `osgeo` stub 부재가 app import 경로에 섞여 WSL 전체 검증에서 확인한다. 상세는 `docs/t158-slow-observability.md`에 기록했다. Agent A 단독 명시 잔여는 닫혔고, `T-153`은 A+B 통합 gate로 진행한다.

## 2026-06-16 (T-247 백업/복원 벤치마크 스크립트)

**작업**: `scripts/benchmark_backup_restore.py`를 추가해 `profile(serving-ready/lean-serving/forensic) × jobs(1/2/4) × zstd compression(3/9/19)` 기본 조합의 백업/복원 소요시간, dump directory 크기, `.tar.zst` 아카이브 크기, 압축률을 `benchmark-report.json`과 `summary.md`로 남기게 했다. 기본은 계획 전용이고, 실행 모드는 typed confirmation(`RUN-T247-BENCHMARK <current_database>`)과 백업 도구(`pg_dump`/`pg_restore`/`tar`/`zstd`)를 요구한다. T-055 N150/Odroid runbook도 T-247 실행기 기준으로 갱신했다.

**결정**: 실제 실행은 행별 일회용 target DB를 만들고 복원 후 drop한다. 벤치마크 settings는 `backup_allowed_dirs`/`backup_temp_dir`를 output dir 아래로 고정하고 `restore_failed_target_cleanup="drop"`을 강제한다. 아카이브는 크기 비교 산출물이므로 삭제하지 않고 보존한다. 저전력 장비 해석은 `jobs=1/2/4`와 zstd `3/9/19`의 총합 최단, 최소 아카이브, 최고 압축률을 같은 표에서 비교하는 방식으로 정리했다.

**검증/문서**: Windows에서 `python -m pytest tests/unit/test_t247_backup_restore_benchmark.py -q` 4개 통과, `python -m ruff check scripts/benchmark_backup_restore.py tests/unit/test_t247_backup_restore_benchmark.py` 통과, `python -m mypy scripts/benchmark_backup_restore.py` 통과, 계획 전용 smoke 통과 후 산출물은 삭제했다. WSL ext4 미러에서도 T-247 단위 테스트 4개, 계획 전용 smoke, 전체 `pytest -q` 967 passed/60 skipped, `ruff check .`, `mypy src/kortravelgeo`, `mypy scripts/benchmark_backup_restore.py`, `lint-imports`, `scripts/export_openapi.py --check`를 통과했다. 현재 Windows/WSL PATH에는 `pg_dump`/`pg_restore`/`zstd`가 없어 실행 모드 live 조합은 실행하지 않았다. 상세는 `docs/t247-backup-restore-benchmark.md`에 기록했다. 사용자 지시에 따라 이번 작업까지만 진행하고 다음 작업은 착수하지 않는다.

## 2026-06-16 (T-245 복원 장애 주입 live 통합 테스트)

**작업**: T-244 round-trip fixture를 재사용하는 `tests/integration/test_backup_restore_fault_injection.py`를 추가했다. 실제 백업 artifact를 만든 뒤 archive-level sha256 flip, truncated tar, 내부 `checksums.sha256` 위조, checksum 누락을 주입하고, 각 실패 뒤 `restore_failed_target_cleanup="drop"` 정책으로 job-owned target DB가 남지 않아야 함을 검증한다. 별도 테스트로 백업 cancel의 failed artifact·최종 archive/`.part`/work dir 삭제, `replace_current`의 `target_dsn` 금지·typed confirmation·maintenance window confirmation matching guard도 고정했다.

**결정**: 제품 복원 코드는 바꾸지 않고 T-235/T-243/T-244의 정책을 live opt-in 통합 테스트로 묶었다. `replace_current` positive restore는 실제 serving DB를 덮어쓰는 위험 경로라 T-245에서 실행하지 않고, `pg_restore` 도달 시 테스트가 실패하도록 막은 뒤 matching confirmation이 없는 window가 `run_restore_job`에서 인가되지 않는 guard를 검증한다. 실제 hot-swap/rollback round-trip은 T-246 범위다.

**검증/문서**: Windows에서 `python -m pytest tests/integration/test_backup_restore_fault_injection.py -q`는 `KTG_TEST_PG_DSN` 미설정으로 3 skipped, Ruff는 새 테스트 파일 기준 통과했다. 현재 Windows/WSL PATH에는 `pg_dump`/`pg_restore`/`zstd`가 없어 live 실행은 할 수 없었고, 이 상태는 "live off skip" 합격조건으로 문서화했다. 상세는 `docs/t245-restore-fault-injection.md`에 기록했다. 다음 Agent A 작업은 T-247이다.

## 2026-06-16 (T-238 백업 manifest 원천 3자 reconcile)

**작업**: 백업 `manifest.json`의 `source_match_set` per-file을 현재 DB `ops.source_files`와 RustFS `HEAD` 결과에 대조하는 opt-in reconcile을 추가했다. 새 manifest는 `ManifestSourceFile.object_etag`를 보존하고, `ktgctl backup reconcile-source --artifact-id ...` 또는 `--manifest-path ...`가 `present`/`missing`/`etag_mismatch`/`size_mismatch`/DB 불일치 row report를 JSON으로 출력한다.

**결정**: 기본 백업/복원 흐름은 실패시키지 않는다. RustFS 비활성 또는 credential 없음, `source_match_set` 없는 legacy manifest는 `skipped=true` report로 graceful 처리한다. ETag는 SHA-256으로 간주하지 않고 빠른 HEAD 정합성 신호로만 사용한다. 실제 DB/RustFS 검증은 `KTG_TEST_RUSTFS_SOURCE_RECONCILE=1`과 `KTG_TEST_BACKUP_MANIFEST`를 요구하는 opt-in integration으로 분리했다.

**검증/문서**: Windows focused unit `tests/unit/test_t238_manifest_source_reconcile.py`와 `tests/unit/test_t208_backup_restore_source.py` 28개가 통과했고, 변경 backend 파일 Ruff와 T-238 순수/infra mypy가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 965 passed/55 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. 상세는 `docs/t238-backup-manifest-reconcile.md`에 기록했다. 다음 Agent A 작업은 T-245다. CodeGraph MCP는 이번 세션에서도 `Transport closed`로 실패해 파일 직접 확인으로 진행했다.

## 2026-06-16 (T-144 성능 우선 v2/API 계약 후보 검증)

**작업**: `docs/t144-api-contract-performance.md`와 ADR-059를 추가해 성능 우선 API 계약 후보를 평가했다. 현재 v2의 `include_geometry=false`, `response_model_exclude_none=True`, geocode/search 상한 100을 accepted profile로 고정하고, geometry endpoint 분리·field slim mode·detail expansion·pre-shaped response table은 T-105/T-139 근거가 생길 때 별도 breaking change로 다루기로 했다.

**결정**: 이번 PR은 wire schema를 바꾸지 않는다. 따라서 OpenAPI/typegen migration은 없고, UI는 기존처럼 geometry가 필요한 debug 호출에서만 `include_geometry=true`를 명시하면 된다. Payload/p99 budget은 새 `scripts/evaluate_t144_api_contract.py`로 REST benchmark `api-report.json`에서 판정한다.

**검증/문서**: Windows focused unit `tests/unit/test_t144_api_contract.py` 4개와 Ruff가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 959 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. Golden response test는 기본 geocode 응답에 후보 `geometry`/`bbox`가 없고, geocode/search 상한 100과 v2 route `response_model_exclude_none=True`가 유지됨을 고정한다. 다음 Agent A 작업은 T-238이다.

## 2026-06-16 (T-162 런타임 캐시/버퍼 예열)

**작업**: `loaders.runtime_warm`을 추가해 API 재기동·서빙 swap 직후 read path를 데우는 plan/execute report를 만들었다. Report는 `pg_prewarm` extension과 서빙 relation 존재 여부, 선택형 `pg_prewarm`, geocode exact/search text/reverse nearest/region radius 상한 있는 읽기 전용 probe 실행 결과를 담는다. API lifespan에는 기본 비활성 opt-in scheduler를 붙였고, `RUNTIME_WARM` advisory lock으로 여러 worker가 동시에 예열을 실행하지 않게 했다.

**결정**: T-162는 공개 API 계약이나 DB object를 추가하지 않는다. `pg_prewarm` extension 설치·DB 재시작·RustFS/DB 구동은 이 저장소가 수행하지 않으며, extension이 이미 있고 명시 설정이 켜진 경우에만 호출한다. 재기동 직후 p99 acceptance는 이 저장소가 DB를 재시작하지 않는 제약을 반영해 `scripts/evaluate_t162_cold_warm_ratio.py`가 cold REST benchmark와 예열 후 REST benchmark의 같은 `(group, sql_name, concurrency)` p99를 비교하는 gate로 남긴다.

**검증/문서**: Windows focused unit은 `tests/unit/test_t162_runtime_warm.py`/`tests/unit/test_settings.py` 15개가 통과했고, 변경 source/script/test Ruff와 T-162 순수 모듈 mypy가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 955 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. WSL 읽기 전용 execute smoke는 `artifacts/perf/t162-runtime-warm-execute-smoke/report.json`이며 `pg_prewarm` extension 없음으로 선택형 단계만 skipped, 4개 쿼리 예열 profile은 모두 succeeded였다. 상세는 `docs/t162-runtime-warm.md`에 기록했다. 다음 Agent A 작업은 T-144다. CodeGraph MCP는 이번 세션에서도 `Transport closed`로 실패해 파일 직접 확인으로 진행했다.

## 2026-06-16 (T-146 post-load read-optimized maintenance)

**작업**: `loaders.postload_maintenance`를 추가해 적재 직후 read-mostly maintenance plan/report를 표준화했다. Report는 source/MV/index catalog 상태, `VACUUM (ANALYZE)` opt-in 단계, `resolve_text_geometry_links()`, `refresh_mv(strategy=...)`, table stats capture, index budget/dead tuple/analyze warning을 담는다. `scripts/run_t146_postload_maintenance.py`는 기본 plan-only와 `execute-safe`, T-265 benchmark artifact 등록을 지원한다.

**결정**: T-146은 새 API 계약이나 DB object를 만들지 않는다. `REINDEX CONCURRENTLY`, raw `CLUSTER`/물리 정렬, `pg_prewarm`은 자동화하지 않고 수동 runbook 또는 T-162 runtime warm 범위로 분리한다. Rollback은 relation-level undo가 아니라 기존 백업/복원 또는 serving hot-swap rollback에 의존한다.

**검증/문서**: Windows focused unit 17개, Ruff, 변경 source/script mypy가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 948 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. WSL plan smoke artifact는 `artifacts/perf/t146-postload-maintenance-plan/report.json`이며 75개 object, index bytes 12,183,379,968, relation bytes 27,936,006,144, warning 2건(`postal_bulk_delivery`/`postal_pobox` analyze 누락)을 확인했다. 상세는 `docs/t146-postload-maintenance.md`에 기록했고, 다음 Agent A 작업은 T-162다.

## 2026-06-16 (T-156 geocode/reverse hot-key 결과 캐시)

**작업**: 기존 `geo_cache` 테이블을 `AsyncAddressClient._geocode_v1()`과 `_reverse_geocode_v1()` local OK 응답 경로에 연결했다. Cache key는 service와 요청 파라미터 canonical JSON의 SHA-256 digest로 만들고, payload는 v1 DTO serializer의 `ROAD`/`PARCEL` 변환을 되돌려 내부 `model_validate()` round-trip이 되게 저장한다. Cache hit는 v1 geocode `x_extension.source`와 reverse item `source`를 `cache`로 표시한다.

**결정**: 외부 API fallback, keyword/search, geometry enrich, `NOT_FOUND`는 이번 캐시 범위에서 제외한다. v2 공개 source는 T-169 결정대로 `cache`를 별도 provider로 드러내지 않고 `local`로 접는다. `refresh_mv()`가 concurrent refresh와 shadow swap 성공 뒤 `geo_cache`를 삭제해 적재/MV swap 뒤 stale 응답을 막는다.

**검증/문서**: Windows focused unit 14개, Ruff, 변경 source mypy가 통과했다. WSL live smoke artifact는 `artifacts/perf/t156-hot-key-cache-smoke-r2/`이며 같은 cache key 반복 호출 뒤 geocode/reverse `hit_count=21`을 확인했다. `서울특별시 종로구 자하문로 94` 기준 geocode p95는 cold 11.871ms → hot 4.630ms, reverse p95는 cold 37.455ms → hot 4.757ms였다. 상세는 `docs/t156-hot-key-cache.md`에 기록했고, 다음 Agent A 작업은 T-146이다. CodeGraph MCP는 `Transport closed`로 실패해 `codegraph status` CLI 최신 상태를 확인했다.

## 2026-06-16 (T-155 psycopg prepared statement·plan cache 튜닝)

**작업**: `Settings.pg_prepare_threshold`와 `KTG_PG_PREPARE_THRESHOLD`를 추가하고, `make_async_engine()`이 psycopg `prepare_threshold`로 전달하게 했다. SQL benchmark는 `--prepare-threshold`와 `--disable-prepared-statements`를 받아 run별 threshold를 바꾸고, `environment.json`/`summary.md`에 값을 기록한다. 또한 `pg_prepared_statements` session-local snapshot을 `prepared-statements-before/after.json`으로 남긴다.

**결정**: production 기본값은 psycopg 기본과 같은 `5`로 유지한다. WSL hot-query smoke에서 `threshold=1`은 prepared count 17로 가장 많이 prepare했지만 전체 p95가 `5.644ms`로 기준보다 약간 나빠졌고, `threshold=5`는 prepared count 13, 전체 p95 `5.383ms`로 `threshold=None`의 `5.585ms`보다 낮았다. `pg_prepared_statements`와 `pg_stat_statements` snapshot은 read-only SELECT라도 transaction을 열기 때문에, connection 반환 시 psycopg가 `ROLLBACK`을 보고 prepared cache를 지우지 않도록 명시 `commit()`한다.

**검증/문서**: Windows focused unit 31개, Ruff, 변경 source mypy가 통과했다. WSL smoke artifact는 `artifacts/perf/t155-prepared-disabled-nofuzzy-r2/`, `artifacts/perf/t155-prepared-threshold1-nofuzzy-r2/`, `artifacts/perf/t155-prepared-threshold5-nofuzzy-r2/`이며 17개 hot-query corpus error 0이다. live DB의 Q3 fuzzy helper MV는 T-171 컬럼이 없어 no-fuzzy corpus로 측정했다. 상세는 `docs/t155-prepared-plan-cache.md`에 기록했고, 다음 Agent A 작업은 T-156이다.

## 2026-06-16 (T-142 reverse-geocoder 공간 조회 최적화)

**작업**: reverse nearest runtime SQL과 radius-heavy benchmark SQL을 분리했다. `ReverseRepository.nearest()`는 `knn_candidates AS MATERIALIZED` CTE로 `mv_geocode_target.pt_5179` GiST KNN 후보를 먼저 뽑고, outer query에서 `distance_m <= :radius_m`을 적용한다. Q6 benchmark는 새 `_RADIUS_SQL`로 기존 `ST_DWithin` prefilter path를 유지한다. 우편번호 point lookup은 polygon 경계 좌표를 포함하도록 `ST_Contains`에서 `ST_Covers`로 바꿨다.

**결정**: 이번 PR에서는 새 DB object, migration, OpenAPI/typegen 변경을 만들지 않는다. KNN runtime path는 실제 API의 "가장 가까운 후보" 요구에 맞추고, radius benchmark는 T-141/T-164에서 별도 plan surface로 계속 측정한다. KNN 후보는 tie-break와 반경 경계 포함을 유지하기 위해 `GREATEST(limit * 8, 64)`까지 over-fetch한다.

**검증/문서**: Windows focused unit 83개, Ruff, 변경 파일 mypy가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 932 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. WSL reverse/zipcode/SPPN smoke artifact는 `artifacts/perf/t142-reverse-spatial-smoke/`이며 7건 error 0, `reverse_nearest` p95 18.649ms, `reverse_radius` p95 4.034ms다. EXPLAIN은 nearest 계열이 `knn_candidates` CTE와 `idx_mv_geom5179`, zipcode가 `idx_kodis_bas_geom`, SPPN이 `idx_sppn_makarea_geom`을 탔다. 상세는 `docs/t142-reverse-spatial-optimization.md`에 기록했고, 다음 Agent A 작업은 T-155다.

## 2026-06-16 (T-143 geocode/search query plan 안정화)

**작업**: `/v2/search` address/road exact preflight SQL을 OR 기반 단일 scan에서 `rn_nrm`/`buld_nm_nrm`/`sigungu_buld_nm_nrm` branch의 `UNION ALL`로 분리했다. 각 branch는 같은 region hint filter를 유지하고, 중복 후보는 `DISTINCT ON (bd_mgt_sn)`과 match priority로 결정 정렬한다. Broad fallback은 SQL 내부 공백 제거 대신 `_normalize_search_query()`가 만든 `query_nrm` bind를 받게 했다.

**결정**: 이번 PR에서는 새 DB object, migration, OpenAPI/typegen 변경을 만들지 않는다. Exact equality path는 이미 exact match가 보장되므로 `similarity()`/`GREATEST()` 계산을 제거하고 score를 `1.0`으로 고정한다. 기존 benchmark corpus는 `query_nrm` 필드를 강제하지 않고 실행 직전 `_search_sql_params()`로 합성해 호환한다.

**검증/문서**: Windows focused unit 81개, Ruff, mypy가 통과했다. WSL ext4 미러에서는 전체 `pytest -q` 929 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check가 통과했다. WSL Q4 search smoke artifact는 `artifacts/perf/t143-search-plan-q4-smoke/`이며 `search`/`search_sig`/`search_fuzzy` 각 1건 error 0, p95는 각각 6.756ms/5.926ms/5.923ms다. EXPLAIN에서 exact case는 `exact_keys` CTE와 `idx_mv_*_nrm_exact`, fuzzy miss는 `scored` CTE와 `idx_mv_text_search_*_trgm`를 탔다. 상세는 `docs/t143-geocode-search-plan.md`에 기록했고, 다음 Agent A 작업은 T-142다. CodeGraph MCP는 이전과 같이 안정적으로 붙지 않아 `codegraph sync/status` CLI 최신 상태를 확인했다.

## 2026-06-16 (T-165 주소 정규화/파싱 견고성 강화)

**작업**: `core.normalize`의 `normalize_spaces()`와 도로명/지번 parser를 보강했다. 입력은 NFKC로 접고, 전각 숫자·대시 변형, 쉼표류 구분자, 숫자 사이 하이픈 공백을 canonicalize한다. 시도 별칭에는 `서울시`, `강원도`, `전라북도` 같은 약어·구/신 표기를 추가했고, `성복1로35`, `왕산로189-4`, `산12 - 3번지`, `189번` 같은 입력이 exact lookup key를 잃지 않도록 했다.

**결정**: 영문 주소 transliteration은 하지 않는다. 한국어 도로명이 함께 들어온 영문 혼용 prefix가 parser를 깨지 않게 하는 범위에 머문다. 도로명 오타 ranking은 T-171 fuzzy fallback 책임으로 유지하고, T-165는 오타 입력에서도 본번·부번·지하구분을 보존하는 데 집중한다.

**검증/문서**: `tests/unit/test_t165_normalization.py`가 정규화 helper, 도로명 변형, 지번 변형, core geocode repository 전달 값을 고정한다. T-140 `T140-GEO-WHITESPACE-ALIAS-001`은 `서울시 동대문구 왕산로１８９－４ (청량리동)` 입력이 `왕산로 189-4`/`sig_cd=11230` road 후보를 반환해야 하는 기본 live case로 좁혔다. Fixture smoke는 25/25 통과했고 SHA-256은 `0b4ff00d1a59520da3237daf57c51e9be1e870a699976f1b86e1d48482d32b99`이다. 상세는 `docs/t165-normalization-robustness.md`에 기록했고, 다음 Agent A 작업은 T-143이다. CodeGraph MCP는 `Transport closed`로 실패해 `codegraph sync/status` CLI 최신 상태를 확인했다.

## 2026-06-16 (T-176 reverse 경계·근접 정확도 정합)

**작업**: reverse nearest SQL의 KNN 정렬 뒤에 `distance_m`, `pt_source='entrance'`, `bd_mgt_sn`, `rncode_full`, `bjd_cd` tie-break를 추가해 같은 거리 후보 순서를 결정적으로 고정했다. `type="both"`는 SQL base row `limit` 적용 후 `road`/`parcel` 순으로 fan-out하는 계약을 단위 테스트로 고정했다.

**결정**: `radius_m`은 `ST_DWithin` 기준이라 경계 거리도 포함한다. v2 reverse의 거리 confidence는 `distance_m == radius_m`에서 `0.0`이지만 후보는 유지한다. 주소 후보가 없는 먼 좌표라도 국가지점번호 계산 context가 있으면 `OK`/SPPN 후보이고, 주소 후보와 SPPN context가 모두 없을 때만 `NOT_FOUND`다.

**검증/문서**: `tests/unit/test_t176_reverse_boundary.py`가 SQL 정렬, `both` fan-out, context-only `OK`, true `NOT_FOUND`, radius edge confidence를 검증한다. T-140 corpus는 `T140-REV-BOUNDARY-001` 기대값을 좁히고 `T140-REV-SEA-001`을 기본 live SPPN context-only case로 승격했다. Fixture smoke는 25/25 통과했고 SHA-256은 `7db1b91c556e8fea22a05eda4a209d6c06925dacea287ff26e8eb47292173f83`이다. 상세는 `docs/t176-reverse-boundary.md`에 기록했고, 다음 Agent A 작업은 T-165다. CodeGraph MCP는 `Transport closed`로 실패해 `codegraph sync/status` CLI 최신 상태를 확인했다.

## 2026-06-16 (T-175 region hint 정확도·교차검증)

**작업**: `RegionHint`에 `sig_cd`/`bjd_cd` prefix 일관성 검증을 추가하고, v2 geocode/reverse/search 입력 모델도 생성 시점에 같은 검증을 실행하게 했다. 모순 hint는 SQL까지 내려가지 않고 기존 validation 계약대로 HTTP 400 입력 오류가 된다.

**결정**: `sig_cd=11230` + `bjd_cd=1123010700`처럼 `bjd_cd`가 `sig_cd`로 시작하는 조합만 유효하다. `sig_cd=11680` + `bjd_cd=1123010700`처럼 서로 다른 지역을 가리키는 조합은 조용한 `NOT_FOUND`가 아니라 오적용 방지를 위한 입력 오류로 고정한다. v1 VWorld 호환 geocode/reverse는 상세 validation hint를 숨기고 `INVALID_TYPE` envelope를 유지한다.

**검증/문서**: `tests/unit/test_t175_region_hint_validation.py`가 v1/v2 public API의 모순 hint 4xx와 core search/reverse hint 전달을 검증한다. `test_infra_repo_sql.py`는 geocode/search/reverse/road geometry SQL이 공통 hint bind를 모두 갖는지 고정한다. T-140 corpus는 정상 BJD hint와 모순 hint negative를 추가해 25개가 됐고 fixture smoke 25/25를 통과했다. 상세는 `docs/t175-region-hint-validation.md`에 기록했고, 다음 Agent A 작업은 T-176이다. CodeGraph MCP는 `Transport closed`로 실패해 `codegraph sync/status` CLI 최신 상태를 확인했다.

## 2026-06-16 (T-173 negative/악성/경계 입력 안전성 하니스)

**작업**: geocode text 입력의 ASCII control character를 DTO에서 거절하고, v2 reverse 입력을 `FiniteFloat`와 한국 lon/lat bounds 검증으로 좁혔다. FastAPI request validation도 좌표 bounds 오류는 `E0102`로 매핑하도록 기존 Pydantic validation helper를 재사용한다.

**결정**: T-219의 non-vworld validation envelope 재결정은 하지 않는다. 일반 request validation은 기존 `E0100`/HTTP 400을 유지하고, 좌표 bounds custom error만 `E0102`로 보존한다. malformed SPPN은 parser/core에서 `None` 또는 `NOT_FOUND`로 끝나는 안전성만 이번 범위에서 고정한다.

**검증/문서**: `tests/unit/test_t173_input_safety.py`가 v1/v2 geocode/reverse/SPPN 악성·경계 입력의 구조화 4xx와 core `NOT_FOUND`를 검증한다. 상세는 `docs/t173-input-safety-harness.md`에 기록했고, 다음 Agent A 작업은 T-175다.

## 2026-06-16 (T-172 confidence 산정 결정성·교정 중앙 모델)

**작업**: `kortravelgeo.core.confidence`를 추가해 geocode centroid cap, 국가지점번호 grid cell, external fallback, reverse distance, search/geometry score confidence를 중앙 helper로 모았다. 기존 호출부의 하드코딩 상수는 helper 호출로 바꿨다.

**결정**: exact local 주소 후보 기본 confidence는 `1.0`, centroid cap은 `0.82`, SPPN grid cell 후보는 geocode/reverse 모두 `0.72`, VWorld/Juso fallback은 `0.70`/`0.65`로 둔다. SPPN reverse 후보는 `point_precision="grid_cell"` 의미와 맞게 기존 `1.0`에서 `0.72`로 낮췄다. 결정은 ADR-058에 기록했다.

**검증/문서**: `tests/unit/test_confidence.py`가 clamp와 단조성을 고정하고, v2/external adapter 단위 테스트와 T-140 SPPN corpus expected field를 갱신했다. 상세는 `docs/t172-confidence-model.md`에 기록했고, 다음 Agent A 작업은 T-173이다.

## 2026-06-16 (T-171 fuzzy ranking 결정성·품질 보강)

**작업**: `mv_geocode_text_search` helper MV에 `buld_slno`와 `buld_se_cd`를 추가하고, `GeocodeRepository.fuzzy_roads()`가 fuzzy fallback에서도 본번·부번·지하구분을 모두 맞춘 후보만 ranking하게 했다. 기존 `similarity DESC → entrance 우선 → bd_mgt_sn` 정렬은 유지해 동률 순서를 결정적으로 둔다.

**결정**: 도로명 fuzzy는 도로명 오타 보정 범위로 한정하고, 건물번호 오타까지 동시에 보정하지 않는다. 따라서 exact 조회와 같은 `buld_mnnm`/`buld_slno`/`buld_se_cd` 계약을 유지한다. `pg_trgm.similarity_threshold`는 기존 `0.42`를 유지하고 트랜잭션 `SET LOCAL`만 사용한다.

**검증/문서**: T-140 corpus의 `T140-GEO-ROAD-FUZZY-001`을 `왕산길 189-4` → `왕산로 189-4` ranking case로 강화하고, runner expected에 `numeric_gte`를 추가했다. Windows focused unit 44개와 fixture smoke가 통과했다. 상세는 `docs/t171-fuzzy-ranking.md`에 기록했고, 다음 Agent A 작업은 T-172다.

## 2026-06-16 (T-164 p99 regression guard)

**작업**: `scripts/evaluate_t164_p99_regression.py`를 추가해 T-141 `matrix-report.json` baseline/current의 같은 `profile_id`를 비교하는 p99 회귀 gate를 만들었다. 결과는 `p99-guard.json`과 `summary.md`로 남기고, `--mode enforce`에서는 실패 시 exit code 2로 종료한다.

**결정**: 기본 허용 p99는 `max(baseline * 1.20, baseline + 25ms)`다. Current row의 error는 기본 0이어야 하며, `phase="soak"` row는 T-163 `soak_guard.passed=true`를 요구한다. Adversarial/입력분포 변화 gate는 `--workload adversarial_fuzzy`, `worst_case_mix`, `reverse_polygon_heavy` 필터를 우선 사용한다.

**검증/문서**: Windows focused unit 4개, Ruff, mypy가 통과했다. 상세는 `docs/t164-p99-regression-guard.md`에 기록했고, 다음 Agent A 작업은 T-171이다.

## 2026-06-16 (T-163 60분 soak resource guard)

**작업**: `scripts/run_t141_load_matrix.py`의 artifact schema를 `2`로 올리고, T-141 soak profile에 `soak_guard_budget`과 profile별 `soak_guard`를 추가했다. Soak 실행 중 runner process current RSS, CPU seconds, `/proc/self/io` delta를 sampling해 `soak-resource-samples.json`과 `soak-guard.json`에 남긴다.

**결정**: 기본 60분 budget은 RSS 증가 256MiB, leak floor 64MiB, CPU 3600초, read/write 각 2GiB다. Leak은 current RSS 첫 1/3 평균 대비 마지막 1/3 평균과 final growth가 모두 floor를 넘을 때로 판정한다. PostgreSQL server와 외부 REST worker process 자원은 runner process guard 범위 밖으로 문서화했다.

**검증/문서**: Windows focused unit 6개와 Ruff가 통과했고, `--mode plan --include-soak --soak-seconds 3600 --soak-guard-mode enforce` smoke가 schema v2 artifact를 생성했다. 상세는 `docs/t163-soak-guard.md`에 기록했고, 다음 Agent A 작업은 T-164다.

## 2026-06-16 (T-159 DB 장애 주입·안정 저하 검증)

**작업**: SQLAlchemy `DBAPIError` 계열 DB 드라이버/연결 오류를 FastAPI exception handler에서 `DatabaseError(E0500, HTTP 503)`로 구조화했다. VWorld 호환 경로는 기존 `SYSTEM_ERROR` envelope를 유지하며, SQL 문장·파라미터·secret 값은 응답에 노출하지 않는다.

**관측/검증**: `/metrics`에 `kor_travel_geo_api_db_errors_total{method,route,error_type}` counter를 추가했다. `/v1/readyz`는 느린 DB probe를 `api_readiness_timeout_ms` 안에서 끊고, DB가 정상화되면 같은 프로세스에서 자동 회복하는 단위 테스트를 추가했다. `scripts/run_t159_db_fault_injection.py`는 실제 PostgreSQL/RustFS를 제어하지 않는 ASGI 가짜 engine 하니스로 `ok → down → slow → ok` 시나리오를 재현한다.

**문서**: 상세는 `docs/t159-db-fault-injection.md`에 기록했다. `docs/tasks.md`의 Agent A 재정렬 순서는 T-159 완료 후 다음 작업을 T-163으로 갱신했다.

## 2026-06-16 (T-161 client disconnect/query cancellation)

**작업**: 공개 주소 API(`/v1/address/*`, `/v2/*`)에서 ASGI `http.disconnect`를 감지하면 inner app task를 cancel하는 middleware를 추가했다. 성능 middleware는 취소 요청을 `status_code=499` request metric과 `api_request_cancelled` 로그로 남기고 `CancelledError`를 재전파한다.

**관측**: `/metrics`에 `kor_travel_geo_api_request_cancellations_total{method,route}`와 `kor_travel_geo_db_query_cancellations_total{operation,query_fingerprint}`를 추가했다. SQLAlchemy query metric은 `asyncio.CancelledError`와 PostgreSQL "user request" `QueryCanceled`를 `status="cancelled"`로 분류한다.

**문서/검증**: 상세는 `docs/t161-cancellation.md`에 기록했다. Windows focused run은 disconnect ASGI 단위 테스트와 cancel metric 단위 테스트 4개, 변경 파일 Ruff를 통과했다. `KTG_TEST_PG_DSN`이 있으면 `pg_sleep` 취소 후 orphan query/connection leak이 없는지 선택형 통합 테스트가 실행된다.

## 2026-06-16 (T-145 운영 backpressure/fail-fast)

**작업**: 기존 `api_max_concurrency` 전역 admission control을 `AdmissionController`로 분리하고, geocode/reverse/search/zipcode/pobox/regions endpoint scope별 concurrency cap을 추가했다. Admission timeout은 `RateLimitError(E0200, HTTP 429)` 또는 VWorld `OVER_REQUEST_LIMIT`로 변환하며 `Retry-After: 1`과 `Cache-Control: no-store`를 함께 반환한다.

**결정**: endpoint scope가 포화됐을 때 전역 slot을 오래 잡지 않도록 endpoint scope를 먼저 얻고, 전역 `address` scope를 나중에 얻는다. Admission 포화는 DB 단절과 달리 process가 살아 있는 overload 신호이므로 `/v1/readyz`는 HTTP 200을 유지하되 `components.admission.status="saturated"`와 `degraded=true`로 노출한다.

**문서/검증**: 상세는 `docs/t145-backpressure-failfast.md`에 기록했다. Windows 전체 pytest는 860 passed/56 skipped, Ruff는 통과했다. Windows 전체 mypy는 로컬 GDAL `osgeo` import/stub 부재로 기존 loader 파일에서 실패했으나, WSL ext4 미러 공식 gate는 pytest 863 passed/53 skipped, Ruff, mypy, import-linter, OpenAPI check 모두 통과했다.

## 2026-06-16 (T-154 DB pool checkout timeout/fail-fast)

**작업**: `Settings.pg_pool_timeout_ms`와 `create_async_engine(pool_timeout=...)` 배선을 추가했다. SQLAlchemy pool checkout timeout은 API exception handler에서 구조화된 `DatabaseError(E0500, HTTP 503)`로 변환하고, `/metrics`에는 route/method별 checkout timeout counter를 추가했다.

**결정**: 풀 포화는 DB 인프라 가용성 문제라 503 + `E0500`으로 둔다. `E0409`는 advisory lock 기반 동시 실행 충돌 전용으로 유지한다. `/v1/readyz`는 pool detail에 `timeout_ms`를 보여 주되, overload admission/envelope 전체 설계는 T-145로 넘긴다.

**문서/검증**: 상세는 `docs/t154-pool-failfast.md`에 기록했다. Windows focused run은 30 passed/1 skipped이며 Ruff와 mypy가 통과했다. `KTG_TEST_PG_DSN`이 없으면 실제 pool timeout 통합 테스트는 skip된다.

## 2026-06-16 (T-174 좌표계 왕복 정밀도 검증·변환 경로 통일)

**작업**: `src/kortravelgeo/infra/coordinates.py`를 추가해 EPSG:5179↔4326 point projection helper를 단일화했다. `GeocodeRepository.project_sppn_point_4326()`와 `ReverseRepository.project_reverse_point_5179()`는 자체 projection SQL을 갖지 않고 shared helper를 호출한다.

**결정**: 새 Python projection dependency를 추가하지 않고 PostGIS `ST_Transform`을 단일 source로 유지한다. Serving SQL 안에서 index-friendly 하게 한 번만 변환하는 CTE는 성능 계획에 묶여 있으므로 유지하고, 명시적 helper method만 단일 경로로 모은다. 왕복 정밀도 기준은 EPSG:5179 x/y 각각 `0.001m` 이하로 둔다.

**문서/검증**: 상세는 `docs/t174-coordinate-transform.md`에 기록했다. Windows focused run은 28 passed/1 skipped이며 Ruff와 mypy가 통과했다. WSL ext4 미러에서 backend pytest 856 passed/52 skipped, Ruff, mypy, import-linter, OpenAPI check를 통과했다.

## 2026-06-16 (T-160 DB readiness/degradation 신호)

**작업**: `/v1/healthz`는 DB를 건드리지 않는 liveness로 유지하고, 새 `/v1/readyz`를 추가했다. Readiness 응답은 `ready`, `degraded`, `components.database`, `components.pool`을 반환하며 DB probe와 SQLAlchemy pool 상태를 분리해서 보여준다.

**결정**: pool이 capacity까지 checked-out이고 checked-in이 없으면 DB checkout을 새로 만들지 않고 즉시 503을 반환한다. DB 단절·timeout·client 미시작은 `ready=false`와 `degraded=true`로 표시한다. Pool utilization 0.8 이상은 트래픽 수신은 가능하므로 200을 유지하되 `degraded=true`로 운영 경고를 노출한다. Readiness DB probe timeout 기본값은 `api_readiness_timeout_ms=1000`이다.

**문서/검증**: 상세는 `docs/t160-db-readiness.md`에 기록했다. `docs/tasks.md`에서는 T-160을 완료로 옮기고 다음 Agent A 작업을 T-174로 갱신한다. WSL ext4 미러에서 backend pytest 854 passed/51 skipped, Ruff, mypy, import-linter, OpenAPI check, UI lint/type-check/test/build를 통과했다. React Doctor는 `errorCount=0`, 기존 경고 16건이다.

## 2026-06-16 (T-157 pg_stat_statements 상시 수집·노출)

**작업**: `ops.pg_stat_statements_snapshots` table/Alembic migration을 추가하고, `AdminRepository`/`AsyncAddressClient`/Admin router에 `pg_stat_statements` top-N snapshot 조회·수집 표면을 붙였다. API lifespan scheduler는 기본 5분마다 시작 시 1회 포함 capture를 수행하고, `/metrics`는 최신 persisted snapshot을 Prometheus gauge로 노출한다. `/admin/ops`에는 top-N panel과 수동 capture 버튼을 추가했다.

**결정**: query 원문은 Prometheus label로 노출하지 않는다. label은 `rank`, `operation`, `query_fingerprint`만 쓰고, Admin `query_preview`는 literal/숫자를 `?`로 마스킹한 뒤 500자로 제한한다. 수동 capture와 scheduler는 PostgreSQL advisory transaction lock을 공유해 중복 실행을 막는다.

**문서/검증**: 상세는 `docs/t157-pgstat-observability.md`에 기록했다. `docs/tasks.md`에서는 T-157을 완료로 옮기고 다음 Agent A 작업을 T-160으로 갱신한다. WSL ext4 미러에서 backend pytest 849 passed/51 skipped, ruff, mypy, lint-imports, OpenAPI check, UI lint/type-check/test/build를 통과했다. React Doctor는 `JobProgress` prop-state sync error와 이번 `OpsPanel` giant component warning을 해소해 `errorCount=0`으로 통과했고, 기존 source-files/backups warning 16건은 별도 후속 정리 대상으로 남긴다.

## 2026-06-16 (Agent A 남은 작업 진행순서 재정렬)

**작업**: `docs/tasks.md`의 병행 운영 규칙을 다시 확인하고, Agent A(Codex)에 남은 성능·안정성·정확도 작업의 실행 순서를 재정렬했다.

**결정**: 번호순이 아니라 의존성과 검증 기반을 우선한다. 순서는 기반 관측·헬스(`T-157`/`T-160`/`T-174`) → 풀 포화·fail-fast(`T-154`/`T-145`/`T-161`/`T-159`) → 고부하 회귀 gate(`T-163`/`T-164`) → 정확도·결정성(`T-171`/`T-172`/`T-173`/`T-175`/`T-176`/`T-165`) → 쿼리·공간 최적화(`T-143`/`T-142`/`T-155`/`T-156`) → maintenance/API 계약(`T-146`/`T-162`/`T-144`) → 백업/복원 A 몫(`T-238`/`T-245`/`T-247`) → 최종 gate(`T-153`)다.

**검증**: docs-only 변경이다. `docs/resume.md`의 "다음 한 작업"도 같은 순서로 갱신한다. 리뷰 반영(fixup) PR은 추가 리뷰하지 않는 규칙을 유지한다.

## 2026-06-16 (T-170 v2 producer 1:N candidate-list 전환)

**작업**: v2 geocode producer의 단일 후보 collapse를 풀었다. `core/v2.py`에 후보 dedup helper와 geocode 응답 병합 helper를 추가했고, `AsyncAddressClient.geocode()`는 local v1 primary 후보와 보조 road geometry 후보를 같은 `candidates` tuple 안에 병합한다.

**결정**: public wire schema는 바꾸지 않는다. `CandidateV2.candidate_id`가 아직 없으므로 dedup은 `national_point_number`, `bd_mgt_sn`, `rncode_full`, 행정구역 코드, POI 이름/좌표, fallback metadata 순서로 처리한다. 후보 순서는 먼저 나온 후보를 유지해 v1 primary를 보존한다.

**검증**: 상세는 `docs/t170-v2-multicandidate-producer.md`와 ADR-057에 기록했다. 단위 테스트는 primary+보조 후보 병합과 dedup 후 limit 적용을 추가했다.

## 2026-06-16 (T-169 v2 enum 정직화)

**작업**: v2 후보 enum을 실제 producer 의미 기준으로 정리했다. `V2MatchKind`에서 미사용 `postal`/`category`를 제거하고 `detail`/`poi`를 추가했다. 장소 검색 결과는 `keyword`가 아니라 `poi` 후보로 변환한다.

**결정**: 국가지점번호 후보는 EPSG:5179 10m cell 중심 계산 좌표이므로 v2 `point_precision="grid_cell"`을 사용한다. `V2Source`에서는 provider가 아닌 `cache`를 제거하고, v1 `source="cache"`가 들어오면 v2에서는 `local`로 접는다. ADR-056에 배경과 후속 범위를 남겼다.

**문서/검증**: 상세는 `docs/t169-v2-enum-honesty.md`에 정리했다. OpenAPI와 UI 생성 타입 갱신이 필요하다. 단위 테스트는 dead enum 거절, `detail`/`poi`/`grid_cell` 수용, place→poi 변환, SPPN grid_cell 변환을 추가했다.

## 2026-06-16 (T-166~T-168 국가지점번호 계산 좌표 first-class 노출)

**작업**: 국가지점번호 forward geocode의 `TL_SPPN_MAKAREA` gate를 제거했다. 유효한 국가지점번호 문자열이면 `core.sppn` 계산식으로 EPSG:5179 10m cell 중심을 만들고, PostGIS 투영 helper로 EPSG:4326 좌표를 반환한다. `TL_SPPN_MAKAREA`는 좌표 생성 조건이 아니라 `x_extension.sppn_makarea` enrich로만 남긴다.

**보강**: `core.sppn` parser/formatter에 한국 SPPN 지원 envelope를 추가해 명백한 바다·국경 밖 grid code를 거절한다. reverse geocode는 입력 좌표를 EPSG:5179로 투영한 뒤 formatter를 배선해 `x_extension.national_point_number`를 반환하고, v2 reverse는 makarea가 없어도 `match_kind="sppn"` 후보를 노출한다.

**문서/검증**: 상세는 `docs/t166-t168-sppn-first-class.md`에 정리했다. 단위 테스트는 forward makarea 없음, reverse makarea 없음, envelope 거절, v2 후보 metadata, SPPN 투영 SQL을 추가했다. DTO 변경이 있으므로 OpenAPI와 UI 생성 타입을 갱신한다.

## 2026-06-16 (T-141 SQL/REST 고부하 benchmark matrix)

**작업**: T-047/T-138 단발 SQL/REST benchmark를 운영형 matrix로 묶는 `scripts/run_t141_load_matrix.py`를 추가했다. workload는 `actual_mix`, `worst_case_mix`, `adversarial_fuzzy`, `reverse_polygon_heavy`로 나누고, phase는 steady/burst/recovery/soak, concurrency는 1/4/16/64/128/256을 지원한다. SQL은 pool checkout·DB execute·`pg_stat_statements` delta를, REST는 응답 크기와 admin summary endpoint를 함께 기록할 수 있다.

**검증/산출물**: DB 없는 plan-only artifact를 `F:\dev\geodata\t141-load-matrix\20260616-r1\plan\`과 `...\full-plan\`에 남겼다. Full plan은 64개 profile이다. 단위 테스트는 workload weighting, REST admin case, plan serialization을 검증한다.

**제약**: 실제 T-213 r3 SQL live smoke는 Windows async event loop 문제를 runner에서 고친 뒤 재시도했지만, 현재 `127.0.0.1:5432`가 listen 중이 아니라 connection timeout으로 실패했다. 이 저장소는 DB를 직접 구동하지 않으므로 live 고부하 수치는 남기지 않았고, 성능 결론도 내리지 않는다. 상세는 `docs/t141-load-matrix.md`.

## 2026-06-16 (T-140 geocoder/reverse golden corpus)

**작업**: 정확도 회귀 방지용 static golden corpus 23개 case를 `tests/fixtures/geocoder_golden_corpus.json`에 추가하고, `scripts/run_geocoder_golden_corpus.py`로 fixture/schema 검증과 live DB 실행을 모두 지원하게 했다. 범위는 도로명 exact/fuzzy, 지번, reverse nearest/boundary, search, zipcode, 국가지점번호, negative, 후속 seed(행정구역/건물명/사서함/도서/산지/동명이인 도로명)를 포함한다.

**결정**: 기본 live 실행에서는 `optional-source`와 `future-followup` 태그를 제외한다. epost 사서함/다량배달처와 아직 기대 field를 좁히지 않은 ranking/boundary seed는 fixture에는 남기되, T-165/T-171/T-172/T-176에서 구체 expected field로 승격한다. Runner는 `query_id`를 제거한 stable response hash와 `golden_fields` snapshot을 artifact에 남긴다.

**검증**: WSL ext4 미러에서 새 단위 테스트 5개와 fixture run이 통과했다. Fixture artifact는 `F:\dev\geodata\t140-geocoder-golden-corpus\20260616-r1\fixture\`에 보존한다. Live mode는 T-213 r3 DB명으로 시도했지만 현재 세션의 WSL `.env` `KTG_PG_DSN` credential이 로컬 PostgreSQL 인증과 맞지 않아 DB 접속 전 단계에서 실패했다. 올바른 DSN을 주입하면 같은 runner로 재실행한다.

## 2026-06-16 (T-138 read-mostly serving 성능 benchmark)

**작업**: T-213 r3 기준 DB(`kor_travel_geo_t213_20260615_r3`)에서 SQL 2,000 case/32,000 measurement와 REST 425 case/1,275 measurement를 재측정했다. Q4 broad search threshold `0.42`, `limit-before-join` 후보를 같은 corpus로 비교하고 `docs/t138-read-heavy-serving-performance.md`에 정리했다.

**결정**: 이번 단계에서는 production index/MV/API SQL을 바꾸지 않는다. SQL baseline worst c64 p95는 `Q4_SEARCH/search_fuzzy=289.146ms`, REST fixed run worst c64 p95는 `Q1_ROAD_EXACT/geocode_road=350.545ms`로 T-214/T-216 band 안이다. Q4 threshold와 join 지연 후보는 p95를 개선하지 못했다. 대신 REST latency harness에서 synthetic `search_fuzzy` case가 `NOT_FOUND`를 정상 latency 표본으로 인정하도록 보정했다.

**후속**: T-139는 즉시 착수하지 않는다. checkout 대기와 high-load tail은 T-141/T-154/T-155/T-156/T-146에서 이어서 다룬다. Artifact는 `F:\dev\geodata\t138-read-heavy-serving-performance\20260616-r1\`에 보존한다.

## 2026-06-16 (T-137 C11 후속 종합 gate 및 ADR-051 재판정)

**작업**: T-129~T-134와 Admin UI 반영 T-220/T-221을 종합해 C11 최종 gate를 닫았다. 새 문서 `docs/t137-c11-final-gate.md`를 추가하고, ADR-051·T-118·T-125·tasks/resume를 같은 결론으로 갱신했다.

**결정**: Blanket C11은 T-125/T-129/T-130 근거로 계속 no-go다. Guarded `centroid_c4_50_c6_c7_move_500` 정책은 T-131/T-132에서 C4/C6/C7 오류 0을 재현했지만 100m 초과 이동 10,099건과 기준월 차이가 남는다. T-133 shadow serving은 rollback/cleanup은 통과했지만 SQL max p95 회귀 83.087%, REST max p95 회귀 132.447%로 성능 gate가 실패했다. 따라서 C11은 validation-only로 고정하고, ADR-051은 accepted로 전환하지 않는다.

**후속**: T-119는 착수하지 않는다. 새 같은 기준월 C11 원천 또는 동등한 새 증거, correctness 무회귀, SQL/REST p95 회귀 5% 이하, rollback, ADR-055 구현 계획, ADR-051 accepted PR, 사용자 명시 승인이 모두 갖춰질 때만 재논의한다. 다음 Agent A 후보는 T-138/T-140/T-141 또는 T-127이다.

## 2026-06-16 (T-134 C11 좌표 출처 노출 계약)

**작업**: C11이 나중에 다시 serving 후보로 논의될 때 v1/v2 응답에서 좌표 출처를 어떻게 표현할지 `docs/t134-c11-coordinate-source-contract.md`와 ADR-055로 확정했다. `pt_source`는 coarse enum `entrance`/`centroid`만 유지하고, `c11_bundle_guarded` 같은 세부 원천명은 `coord_source_detail`로 분리한다.

**결정**: v1 VWorld 호환 표면에는 최상위나 `result` 내부 field를 추가하지 않는다. 필요 시 `response.x_extension.pt_source`/`coord_source_detail`만 사용한다. v1 reverse는 후보별 detail을 새로 노출하지 않고, v2는 `CandidateV2.point_precision`과 `metadata.pt_source`/`metadata.coord_source_detail`을 사용한다. 현재 코드에는 해당 DTO field가 없으므로 이번 작업은 OpenAPI/typegen/code 변경 없이 문서와 테스트 계획만 확정했다.

**후속**: T-137에서 C11 최종 gate와 ADR-051을 재판정한다. C11이 계속 no-go면 구현하지 않고, 조건부 go가 되더라도 T-119는 ADR-051 accepted와 사용자 명시 승인 뒤에만 착수한다.

## 2026-06-16 (T-133 C11 shadow serving 성능·rollback 리허설)

**작업**: `scripts/run_t133_c11_shadow_serving_rehearsal.py`를 추가해 T-132 guarded C11 정책을 active serving으로 승격하지 않고 `_ktg_t133_shadow` schema의 shadow `mv_geocode_target`/`mv_geocode_text_search`로 리허설했다. shadow REST 서버용 `KTG_PG_SEARCH_PATH` 설정도 추가했다(기본값은 기존과 같은 `public,x_extension`).

**결과**: flag off public identity는 전후 동일했다(`mv_geocode_target=6,419,795`, point rows `6,404,343`, text-search rows `6,419,795`, sample hash `98b0cc91c67176575a87ddd856156d8d`, active release `54e17e80-312e-46da-a58f-d8b10be37c85`). shadow row count도 public과 같고 guarded C11 적용 row는 3,482,270건이었다.

**Gate**: rollback과 cleanup은 통과했다(`_ktg_t133_shadow` drop, `_ktg_t125_*`/`_ktg_t131_*` 잔존 0). 하지만 SQL/REST p95 성능 gate는 실패했다. 최종 summary 기준 SQL max p95 regression은 83.087%, REST(T-216 c64-425 baseline 대비) max p95 regression은 132.447%다. 오류 row는 0건이므로 correctness 문제가 아니라 shadow search path/table 경로의 latency 회귀다. 따라서 active serving promotion은 계속 금지한다. 상세와 artifact는 `docs/t133-c11-shadow-serving-rehearsal.md`, `F:\dev\geodata\t133-c11-shadow-serving-rehearsal\20260616-r1\`.

## 2026-06-16 (T-132 C11 guarded 후보 검증 harness)

**작업**: `scripts/run_t132_c11_guarded_policy_validation.py`를 추가해 T-131의 `centroid_c4_50_c6_c7_move_500` 정책을 threshold flag 기반으로 반복 검증할 수 있게 했다. 정책 mode, sample CSV/GeoJSON export, 결정적 `summary.json` schema, `coord_source_detail="c11_bundle_guarded"` sample column, 작업 테이블 cleanup 검증을 포함한다.

**결과**: T-213 r3 DB에서 T-131 feature table과 T-125 candidate table을 재사용해 live 검증을 실행했다. 정책은 후보 3,482,270건을 사용해 C3 결측을 같은 수만큼 채우고 candidate C4/C6/C7 오류 0건, p99 이동 64.981m, max 495.345m, 500m 초과 0건을 재현했다. 100m 초과 이동 10,099건 warning이 남아 active serving promotion은 계속 금지한다.

**산출물/검증**: Artifact는 `F:\dev\geodata\t132-c11-guarded-policy-validation\20260616-r1\`, 상세는 `docs/t132-c11-guarded-policy-validation.md`에 기록했다. 실행 후 `_ktg_t125_*`와 `_ktg_t131_c11_policy_features` 작업 테이블 cleanup `passed=true`를 확인했다. Windows와 WSL ext4 미러에서 focused pytest/ruff/mypy가 통과했다.

## 2026-06-16 (PR #210~#217 사후 리뷰 후속 반영)

**작업**: Claude Code의 최근 병합 PR #205/#206/#208/#210/#211/#213/#214/#215/#217에 사후 리뷰 코멘트를 남기고, M급 결함 중 복원 preflight/cleanup에 직접 영향을 주는 항목을 fixup으로 반영했다.

**수정**: restore dry-run과 실제 restore version guard가 현재 앱 DB가 아니라 실제 `target_dsn` 클러스터의 PostgreSQL/PostGIS 버전을 조회한다. dry-run의 target DB 접속/존재 확인 실패와 target version query 실패는 warning이 아니라 blocker로 처리한다. 실패 cleanup은 target DB 이름을 런타임 검증한 뒤 quote하고, quarantine 이름은 PostgreSQL 63자 제한 안에 들어오도록 잘라 생성한다. 전체 Windows 단위 테스트 중 함께 드러난 `TL_SPPN_MAKAREA` ZIP member prefix의 OS별 separator 회귀도 `PurePosixPath`로 고쳤다.

**문서/검증**: 상세는 `docs/postmerge-review-fixups-pr210-pr217.md`에 기록했다. Windows `pytest -q`는 758 passed/53 skipped로 통과했고, WSL ext4 mirror에서는 `pytest -q` 761 passed/50 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`가 모두 통과했다.

## 2026-06-16 (PR #142/#145/#149 리뷰 후속 반영)

**작업**: 전체 PR review thread 스캔에서 남아 있던 source registry 계열 unresolved thread 7건을 코드로 반영했다. register coverage 검증을 full member 검증에서 분리하고, `revalidate_group`의 child state 갱신 순서를 바로잡았으며, janitor multipart abort key를 실제 upload endpoint layout과 맞췄다.

**수정**: `source_reconcile`은 RustFS object scan limit을 실제 `list_objects`에 적용하고, `import_object` resolve가 registry 등록 없이 item을 닫지 않도록 차단한다. `delete_object`는 object가 살아 있는데 RustFS client가 없으면 DB row를 `hard_deleted`로 바꾸지 않고 `blocked:rustfs_unavailable`을 반환한다.

**문서/검증**: 상세 매핑은 `docs/postmerge-review-fixups-pr142-pr149.md`에 기록했다. Windows 단위 테스트 94개, 변경 파일 ruff, 변경 source mypy는 통과했다. T-210 통합 테스트는 현재 Windows 환경에서 DB-gated 케이스 대부분이 skip되고 실행 가능한 3개만 통과했으므로 WSL ext4 미러에서 추가 확인한다.

## 2026-06-16 (T-131 C11 guarded policy simulation)

**작업**: `scripts/run_t131_c11_guarded_policy_simulation.py`를 추가해 C11 후보를 blanket 승격하지 않는 guarded policy 7개를 오프라인으로 비교했다. T-129/T-130 후보 테이블을 재사용하고 `_ktg_t131_c11_policy_features` feature table에서 C4/C6/C7, baseline 결측, movement budget을 집계했다.

**결과**: blanket C11은 candidate C4/C6/C7 오류가 68/3,635/9,896이라 계속 no-go다. `centroid_c4_50_c6_c7_move_500`은 C3 결측 3,482,270건을 채우면서 candidate C4/C6/C7 오류 0건, p99 이동 64.981m, max 495.345m, 500m 초과 0건으로 가장 보수적인 반복 검증 후보가 됐다. 다만 100m 초과 이동이 10,099건 남아 active serving promotion은 여전히 금지한다.

**산출물**: `F:\dev\geodata\t131-c11-guarded-policy-simulation\20260616-r1\`에 `summary.json`, `policy_summary.csv`, 재현 SQL을 보존했다. 상세는 `docs/t131-c11-guarded-policy-simulation.md`에 정리했다. T-132에서 재사용할 수 있도록 `_ktg_t125_*`와 `_ktg_t131_*` 작업 테이블은 남겨 두었다.

## 2026-06-16 (T-130 C11 C4/C6/C7 회귀 원인 분석)

**작업**: `scripts/run_t130_c11_regression_root_cause.py`를 추가해 T-125에서 악화된 C4/C6/C7을 row-level로 분석했다. T-129에서 남긴 `_ktg_t125_*` 후보 테이블을 재사용하고, baseline serving 출입구와 C11 후보점의 건물·우편번호·행정구역 polygon 오류를 같은 row에서 비교했다.

**결과**: C4 over500 68건은 candidate regression 52건, shared error 16건이다. C6는 candidate error 3,635건 중 candidate regression 2,834건, shared 801건, 개선 2건이며, 회귀 2,834건 중 2,827건은 기존 baseline 출입구가 없어 평가 대상이 아니던 row다. C7는 candidate error 9,896건 중 candidate regression 3,087건, shared 6,809건, 개선 6건이며, 회귀 3,087건 중 3,077건은 baseline 출입구 결측 row다.

**문서화**: GitHub PR thread 스캔 중 Windows Python 기본 encoding(cp949)이 GitHub UTF-8 JSON을 잘못 디코딩해 실패한 패턴과, `gh pr merge`가 repo 생략 시 로컬 worktree checkout 충돌을 일으키는 패턴을 `docs/agent-failure-patterns.md`에 추가했다.

**산출물**: `F:\dev\geodata\t130-c11-regression-root-cause\20260616-r1\`에 case별 CSV/GeoJSON, `summary.json`, 재현 SQL을 보존했다. 상세는 `docs/t130-c11-regression-root-cause.md`에 정리했다. T-131에서 재사용할 수 있도록 작업 테이블은 계속 남겨 두었다.

## 2026-06-16 (T-129 C11 outlier 원인 태깅)

**작업**: `scripts/run_t129_c11_outlier_triage.py`를 추가해 T-125의 C11 후보 100m 초과 outlier 14,433건 전체를 자동 태깅했다. 기존 T-125 staging/candidate 생성 함수를 재사용하고, row별 건물·우편번호·행정구역 containment, 경도 약 2도 shift, 다중 후보, natural-key polygon 미매칭, 기준월 차이를 CSV/GeoJSON/summary로 export한다.

**결과**: primary tag는 `candidate_coordinate_error=13,000`, `current_representative_error=899`, `source_month_drift_possible=287`, `key_mismatch=210`, `crs_or_source_coordinate_error=33`, `manual_review=4`다. 전체 outlier는 후보 202604와 텍스트 202605 기준월 차이를 secondary tag로 갖지만, 단독 원인으로 보지 않고 공간/key 신호가 약한 경우에만 primary로 승격했다.

**산출물**: `F:\dev\geodata\t129-c11-outlier-triage\20260616-r1\`에 `summary.json`, `outlier_tags.csv`, `outlier_tags.geojson`, `representative_samples.sql`을 보존했다. 상세는 `docs/t129-c11-outlier-triage.md`에 정리했다. T-130에서 재사용할 수 있도록 T-213 r3 DB의 `_ktg_t125_*` 작업 테이블은 남겨 두었다.

## 2026-06-15 (고성능 geocoder와 Admin UI 안정화 task 보강)

**작업**: 사용자 지시에 따라 T-140~T-153을 추가했다. Agent A(Codex)는 geocoder/reverse-geocoder golden corpus, 고부하 SQL/REST benchmark matrix, reverse 공간조회 최적화, geocode/search query plan 안정화, 성능 우선 API 계약 재설계, backpressure/fail-fast, post-load read-optimized maintenance를 맡는다. Agent B(Claude Code)는 성능·검증 artifact Admin UI 노출, source-files Playwright e2e matrix, 파일 적재 UX, deterministic fixture harness, 운영 편의 기능, 접근성·회복성 e2e를 맡는다.

**결정**: 아직 배포 단계가 아니므로 호환성 유지와 코드 수정 최소화보다 성능·안정성을 우선한다. API 계약 변경, MV 적극 활용, 인덱스/통계/maintenance 조정, 더 과격한 DB 구조 변경은 모두 후보가 될 수 있다. 단, DB 구조 변경은 T-139의 별도 변경 DB 비교 workflow를 거쳐 현 DB와 같은 corpus로 검증한 뒤 실제 migration Task를 다시 분리한다.

## 2026-06-15 (read-heavy 성능 최적화 task 추가)

**작업**: 적재 후 write가 사실상 없고 read가 대부분이라는 운영 전제를 반영해 T-138/T-139를 `docs/tasks.md`에 추가했다. T-138은 현재 구조 안에서 benchmark, index, MV, 통계, query plan, API 계약을 조정하는 속도 튜닝 작업이고, T-139는 T-138으로 충분히 빠르지 않을 때 별도 변경 DB를 만들어 현 DB와 구조 변경안을 비교하는 후속 작업이다.

**결정**: 아직 배포 전이므로 성능 작업에서는 호환성 유지와 코드 수정 최소화보다 성능·안정성을 우선한다. API 계약 변경이 payload, query path, precomputed response, geometry 제공 방식, pagination 정책을 더 빠르고 안정적으로 만든다면 후보로 포함한다. 계약을 바꾸면 OpenAPI/typegen/UI/문서/회귀 테스트와 migration note를 같은 흐름에서 갱신한다. DB 구조 변경은 즉시 현재 DB에 섞지 않고, 변경 DB와 현 DB를 같은 원천, 같은 commit, 같은 benchmark corpus로 비교한 뒤 최적안을 문서화한다. 실제 migration은 T-139 결론 뒤 별도 후속 Task로 다시 쪼갠다.

## 2026-06-15 (T-125 후속 Action task 분할)

**작업**: T-125 `blocked / no-go` 결과를 바로 T-119 구현으로 넘기지 않고, 후속 검증과 UI 반영을 T-129~T-137로 세분화해 `docs/tasks.md`에 등록했다. outlier 원인 태깅, C4/C6/C7 회귀 분석, guarded policy simulation, 검증 harness 확장, shadow serving 성능·rollback, v1/v2 노출 계약, Admin UI 정합성 감사, T-125 적재·승격 보류 상태 UI 반영, 최종 gate/ADR-051 재판정으로 나눴다.

**결정**: 실제 파일이 RustFS/source registry에 등록됐다는 사실과 active serving 좌표로 활용 중이라는 사실을 UI에서 분리해야 한다. `T-135`는 실제 활용 파일과 Admin UI 표시의 정합성 감사로, `T-136`은 T-125/T-216 이후의 등록·검증·승격 보류 상태를 Admin UI에 반영하는 구현 작업으로 둔다. T-119는 T-129~T-137, ADR-051 accepted, 사용자 승인 전까지 계속 보류한다.

## 2026-06-15 (T-128 optional 원천 최종 사용 판정)

**작업**: PR #193/#194의 Claude Code clean-slate v2 분석을 확인했다. 두 PR 모두 GitHub conversation comment, review, review thread가 0건이라 별도 comment 반영은 없었고, PR 문서 본문 의견을 T-125 C11 no-go 결과와 합쳐 최종 판정으로 정리했다.

**결정**: `docs/optional-source-usage-decision.md`를 새 source-of-truth로 추가했다. 국가지점번호 좌표는 `core.sppn` 계산값으로 활용하고, `TL_SPPN_MAKAREA`는 zone context로 유지한다. `도로명주소 건물 도형`의 C11 출입구점은 T-125에서 p95/p99/outlier와 C4/C6/C7 회귀가 확인됐으므로 현행 대표 좌표 ranking에 blanket 승격하지 않는다. `상세주소DB`와 `건물군 내 상세주소 동 도형`은 상세주소 typed feature 후보로 두되 호별 좌표처럼 표시하지 않는다. `주소DB`, `건물DB`, `민원행정기관전자지도`, 국가지점번호 grid/center는 기본 주소 좌표 원천이 아니라 검증·별도 기능 후보로 둔다.

**문서**: ADR-054를 accepted로 추가하고, `docs/source-data-accuracy-review.md`와 `docs/backup-restore-source-inventory.md`는 최종 판정 문서를 우선 참조하도록 갱신했다.

## 2026-06-15 (T-125 C11 serving 사전 검증 완료)

**작업**: `scripts/run_t125_c11_serving_preflight.py`를 추가해 T-213 r3 DB에서 C11 `roadaddr_building_shape_bundle` 후보를 staging으로 만들고 기존 `mv_geocode_target` 대표점과 비교했다. `TL_SGCO_RNADR_MST`에는 `BD_MGT_SN`이 없으므로 26자리 `ADR_MNG_NO`를 후보 `bd_mgt_sn`으로 사용했고, C4는 전자지도 polygon의 직접 `bd_mgt_sn`이 아니라 natural key로 비교했다.

**결과**: T-125 gate는 `blocked / no-go`다. 후보 coverage는 matched 6,404,009건, current-only 15,786건, candidate-only 2,156건이다. 거리 impact는 p95 `22.801m`, p99 `54.283m`, 100m 초과 14,433건이며, C3 결측은 3,513,854건에서 15,786건으로 줄었지만 C4 over500 16→68, C6 ERROR 803→3,635, C7 ERROR 6,815→9,896으로 악화됐다.

**후속**: ADR-051은 `proposed` 유지, T-119는 계속 보류한다. Artifact는 `F:\dev\geodata\t125-c11-serving-preflight\20260615-r2\`, 상세는 `docs/t125-c11-serving-preflight-result.md`에 남겼다. 검증 완료 후 `_ktg_t125_*` 작업 테이블은 모두 삭제했다.

## 2026-06-15 (T-106 v1 VWorld geocode/reverse 호환 반영)

**결정**: ADR-053으로 T-106의 호환 수준을 REST v1 geocode/reverse의 VWorld HTTP envelope/key/대소문자 호환으로 확정했다. byte-for-byte VWorld 원응답 동일성은 목표로 두지 않고, 로컬 보강 정보는 기존 ADR-003 원칙대로 `x_extension`에 유지한다.

**수정**: `/v1/address/geocode`와 `/v1/address/reverse` 정상 응답을 `{"response": ...}`로 감싸고, HTTP 직렬화에서 `service.name=address`, `operation=getCoord/getAddress`, 응답 `type` 대문자를 내도록 했다. geocode `simple`/`refine` 생략 규칙과 reverse `simple` 파라미터를 반영했다. v1 geocode/reverse 요청 검증·도메인 에러는 VWorld식 `response.error.level/code/text`로 분기한다.

**검증**: DB 없이 dependency override 기반 v1 HTTP 회귀 테스트를 추가해 envelope, 대문자 type, `simple`, 요청 검증 error object를 고정했다. `openapi.json`, `kor-travel-geo-ui/types/api.gen.ts`, `kor-travel-geo-ui/lib/schemas.gen.ts`를 재생성했다.

**프론트엔드 진단**: React Doctor 재실행 중 기존 source-files UI의 label 접근성 진단과 upload session SSE hook의 prop-change state sync error가 발견되어 함께 정리했다. 최종 React Doctor는 error 0, warning 7(source-files 구조 리팩터 제안) 상태로 통과했다.

## 2026-06-15 (PR #187 리뷰 후속 반영)

**작업**: 머지된 PR #187의 post-merge 리뷰 코멘트를 확인했다. formal review thread는 없고 top-level 상세 리뷰 1건이었으며, blocking은 없었다. Low 후속 2건 중 `_canonical_layer_name`의 dot-delimited 가정은 코드로 반영하고, optional single-file category 상세 validator 부족은 T-127 백로그로 분리했다.

**수정**: `source_member_scan`의 layer token 추출을 dot 전용에서 token boundary 기반으로 넓혀 underscore/hyphen/space 같은 구분자도 허용했다. 구분자 없이 완전히 붙은 vendor 파일명은 계속 full-stem fallback으로 남겨 구조 검증이 missing layer로 실패하게 한다. 공급자 파일명 테스트에 underscore 구분 케이스와 full-stem 오인 방지 assertion을 추가했다.

## 2026-06-15 (T-216/T-126 live acceptance 완료)

**작업**: 사용자가 RustFS를 올린 뒤 T-126 잔여 live acceptance를 실행했다. 기본 `.env`의 `kor_travel_geo`는 T-213 기준 DB가 아니어서, 실행 wrapper에서 DB 이름만 `kor_travel_geo_t213_20260615_r3`로 명시 치환했다. RustFS endpoint `http://127.0.0.1:12101`, bucket `kor-travel-geo` 접근을 확인하고 prefix `kor-travel-geo/t216/20260615-r2`를 사용했다.

**수정**: 실제 optional shape bundle ZIP의 SHP 파일명이 `Total.JUSURB.20260501.TL_...11000.shp` 형태라 기존 `source_member_scan`이 전체 stem을 layer명으로 잡아 구조 검증이 실패했다. scanner가 알려진 layer명을 파일명 내부 token에서 추출하도록 보강했고, `TL_SPBD_ENTRC_DONG`이 `TL_SPBD_ENTRC`로 접히지 않도록 긴 layer명 우선 매칭을 적용했다. runner의 구조 검증 실패 메시지도 part별 이유를 포함하게 했다.

**결과**: `scripts/run_t126_acceptance_followup.py --execute`로 optional source 8개 category/40개 archive를 source registry에 등록했다. base source match set은 `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a`, custom source match set은 `0c7d7ee7-75bf-4a1e-ae0b-015485e73656`이다. C11~C17 run-validation은 `runnable=7`, `skipped=0`, `failed=0`, quarantine 0건이다.

**REST**: 기존 `12501` API는 admin ops 조회가 500이라 수용검증 서버로 쓰지 않았다. WSL 미러에서 T-213 DSN, pool `20/64`, GeoIP gate off, uvicorn worker 1/uvloop 조건으로 임시 API를 `127.0.0.1:12518`에 띄우고 benchmark 후 종료했다. 동일 표본 425 REST case 결과는 error 0, worst c64 p95 `Q4_SEARCH/search_hint=415.022ms`로 T-214 기준 `534.031ms` 이하라 수용했다. `--max-cases-per-sql`을 빠뜨린 1800 case exploratory run은 수용 판정에서 제외하고 artifact만 보존한다.

**검증**: WSL ext4 미러에서 `pytest tests/unit/test_t203b_member_scan.py -q` 4 passed, 전체 `pytest -q` 674 passed/47 skipped, ruff 통과, mypy 통과, import-linter `Layered architecture KEPT`를 확인했다. Artifact는 `F:\dev\geodata\t216-acceptance\20260615-r2\`, 상세는 `docs/t216-live-acceptance.md`.

## 2026-06-15 (T-126 phase ② 수용 후속 준비)

**작업**: T-215에서 남긴 C11~C17 optional source run-validation과 REST c64 tail 후속을 진행했다. `scripts/run_t126_acceptance_followup.py`를 추가해 `F:\dev\geodata\juso\unused\`의 optional 검증 원천 8개 category/40개 archive를 source registry에 등록하고, 기존 active source match set에 optional group을 더한 `custom` match set으로 `run_consistency_validation()`을 실행할 수 있게 했다. rebuild/promote는 하지 않는다.

**수정**: C17 registry 입력을 독립 category처럼 보이던 `navi_full.match_jibun`에서 실제 업로드 category `navi_full` + `member_flag="navi_full.match_jibun"`로 정정했다. `tl_juso_parcel_link`는 source archive가 아니라 active serving DB table이므로 `requires_active_table` metadata로 남겼다. run-validation 정상 입력도 `source_file_group_id`를 응답에 보존하도록 고쳤고, API run-validation은 현재 presence/integrity gate만 실행한다는 범위를 주석/문서로 명확히 했다.

**성능 하네스**: `scripts/benchmark_api_latency.py` artifact schema를 `2`로 올리고 `--server-profile KEY=VALUE`, `--capture-prometheus`를 추가했다. REST c64 수용 기준은 T-214 기준 `REST c64 worst p95=534.031ms`, error 0으로 다시 고정했다.

**검증**: WSL ext4 미러에서 focused unit `24 passed`, changed-file ruff 통과, `mypy src/kortravelgeo scripts/benchmark_api_latency.py scripts/run_t126_acceptance_followup.py` 통과, `lint-imports` 통과를 확인했다. plan 모드도 optional source 8개 category/40개 archive를 확인했다.

**주의**: 현재 세션에는 `KTG_RUSTFS_*`와 `data/rustfs/config.json`이 없고, API 서버 포트 `12501`/`12514`/`12518`도 응답하지 않아 RustFS verifier 포함 live run-validation과 REST c64 live benchmark는 실행하지 않았다. 남은 실행 절차는 `docs/t126-phase2-acceptance-followup.md`에 정리했다.

## 2026-06-15 (T-213 기준 DB 접속 경로 문서화)

**작업**: 다른 에이전트가 T-214/T-215 기준 데이터를 바로 사용할 수 있도록 `docs/t213-data-preservation.md`에 현재 T-213 r3 baseline 접속 정보를 보강했다. PostgreSQL host/port는 `localhost:5432`, DB는 `kor_travel_geo_t213_20260615_r3`, DSN은 `KTG_PG_DSN` template로 기록하고, RustFS endpoint/prefix, 원천 루트, T-213/T-214/T-215 artifact 루트, WSL/bash와 PowerShell 환경변수 예시를 함께 정리했다.

**주의**: PostgreSQL 기준 DB는 raw `pgdata` 파일 경로가 아니라 `KTG_PG_DSN`으로 접근하는 논리 DB로 문서화했다. DB 계정과 password는 로컬 secret이므로 문서에 쓰지 않는다.

## 2026-06-15 (T-215 phase ② 튜닝·최종 검증 평가 완료)

**작업**: T-213 r3 전용 baseline(`kor_travel_geo_t213_20260615_r3`, serving release `54e17e80-312e-46da-a58f-d8b10be37c85`)에서 T-215 preflight, C1~C10 재실행, C11~C17 run-validation, v1/v2 geocode/search/reverse/zipcode smoke, SQL/REST c64 재측정을 수행했다. 검증 artifact는 `F:\dev\geodata\t215-acceptance\20260615-r1\`에 남겼다.

**결과**: Preflight는 DB/release/snapshot/source match set/row count가 모두 일치했다. v1/v2 smoke는 `경기도 용인시 수지구 성복1로 35` 기준으로 geocode/search/reverse/zipcode 모두 HTTP 200/`OK`였다. C1~C10 새 report는 `consistency_87ce6c3f2d574cfca39976a5a8f74f3d`, `severity_max=ERROR`다. C2 32,496건, C4 `over_500m=16`, C6 803건, C7 6,815건은 known data-quality 상태로 남았고, C10은 `tl_juso_text=202605`와 나머지 `202604` 혼합 WARN이다.

**주의**: C11~C17 run-validation은 현 T-213 r3 `serving_recommended` match set에 보강 검증 원천이 없어 7건 모두 `skipped`였고 실패/quarantine은 0건이었다. SQL c64 재측정은 error 0건, worst p95 `Q4_SEARCH/search_fuzzy=308.617ms`였지만, REST c64 sample은 pool `20/64`에서도 error 0건, worst p95 `Q3_FUZZY_GEOCODE/geocode_fuzzy_hint=3631.900ms`로 T-214보다 크게 악화됐다. REST c64 tail과 C11~C17 optional source run-validation은 T-126 후속으로 분리했다. 상세: `docs/t215-phase2-final-acceptance.md`.

## 2026-06-15 (T-214 phase ② 성능평가·벤치 완료)

**작업**: T-213 r3 전용 baseline(`kor_travel_geo_t213_20260615_r3`, RustFS `kor-travel-geo/t213/20260615-rerun3`, serving release `54e17e80-312e-46da-a58f-d8b10be37c85`)을 preflight로 확인한 뒤 T-214 benchmark를 실행했다. T-213 r3 full-load/rebuild-db 로그를 기준 load 벤치로 사용했고, T-047 SQL/REST 하네스, T-035 MV refresh/swap 하네스, source registry deep rehash/multipart synthetic 하네스, 실제 RustFS quick/deep reconcile을 실행했다.

**결과**: artifact는 WSL mirror에서 생성한 뒤 `F:\dev\geodata\t214-benchmark\20260615-r3\`로 복사했다. SQL benchmark는 오류 0건이며 c64 worst p95가 `Q4_SEARCH/search_fuzzy=245.895ms`다. REST sample benchmark도 오류 0건이며 c64 worst p95가 `Q4_SEARCH/search_fuzzy=534.031ms`다. MV는 `concurrent=126.414s`, `swap-rerun=340.128s`로 측정했고 row count는 `mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`를 유지했다.

**주의**: 첫 `swap` 측정은 실제 swap 이후 `ANALYZE mv_geocode_target` 단계에서 DB statement timeout에 걸렸다. relation과 row count를 확인한 뒤 `ANALYZE`를 수동 보정했고, statement timeout을 늘려 `swap-rerun.json`으로 최종 측정했다. 실제 RustFS quick/deep reconcile은 등록 DB file missing 없이 prefix orphan object warning 2건(`object_missing_db`)만 남겼다. 상세 결과는 `docs/t214-phase2-performance-benchmark.md`에 정리했다.

## 2026-06-15 (T-214 baseline 재구성 및 Juso 원천 정리)

**작업**: `F:\dev\python-kraddr-geo\data\juso`와 `F:\dev\python-kraddr-geo\data\juso-incoming-20260614`의 Juso 원천을 `F:\dev\geodata\juso`로 복사한 뒤, T-213/T-214가 직접 쓰는 6개 원천만 루트에 남겼다. 현재 쓰지 않는 파일과 과거 snapshot, 검증 전용 묶음은 삭제하지 않고 `F:\dev\geodata\juso\unused\` 아래 같은 상대 경로로 이동했고, 이동 로그는 `unused\move-log.csv`에 남겼다.

**작업**: `scripts/run_t213_live_pipeline.py`의 기본 데이터 루트를 `/mnt/f/dev/geodata/juso`로 우선 탐색하게 바꾸고, 기준년월이 없는 원천은 `202604`로 갈음하는 정책을 plan/summary에 기록하게 했다. NAVI row count table 이름도 실제 테이블명(`tl_navi_buld_centroid`, `tl_navi_entrc`)으로 보정했다. README, SKILL, AGENTS, 개발환경/워크플로/복구 문서, T-213/T-214 handoff 문서에는 공용 `geodata` 원천과 `unused` 보존 규칙, T-213 baseline 보존 정책을 반영했다.

**실행 결과**: T-214 기준 baseline을 전용 DB `kor_travel_geo_t213_20260615_r3`와 RustFS prefix `kor-travel-geo/t213/20260615-rerun3`에 재실행했다. source match set은 `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a`, active serving release는 `54e17e80-312e-46da-a58f-d8b10be37c85`, dataset snapshot은 `1b354560-52bc-4ec6-8760-55fed63d9e98`, load batch는 `batch_ee0c66494eac490ba927e0a689dfd29a`다.

**검증**: source load 6개, consistency check, MV refresh가 모두 `done`이다. row count는 `tl_juso_text=6,419,795`, `tl_locsum_entrc=6,405,091`, `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`, `tl_spbd_buld_polygon=10,687,732`, `tl_roadaddr_entrc=6,404,697`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`다. `경기도 용인시 수지구 성복1로 35` smoke geocode는 `OK` 후보 1건을 반환했다. summary와 run log는 `F:\dev\geodata\t213-baseline\20260615-rerun3\`에 복사했다.

## 2026-06-15 (T-125 C11 serving 사전 검증 문서 보강)

**작업**: T-119 착수 전 빠뜨리면 안 되는 증거를 `docs/t125-c11-serving-preflight.md`에 별도 gate로 고정했다. 기존 `mv_geocode_target` 대표점 대비 impact, C3/C4/C6/C7 회귀, T-047/T-214 계열 성능 회귀, feature flag rollback, v1/v2 노출 정책을 필수 산출물로 분리하고, 하나라도 없으면 ADR-051 accepted 전환과 T-119 착수를 금지한다고 명시했다.

**반영**: `docs/tasks.md`, `docs/resume.md`, `docs/decisions.md` ADR-051, `docs/t118-phase1-go-no-go.md`, `docs/t123-phase1-acceptance.md`, `CHANGELOG.md`가 새 T-125 gate 문서를 참조한다.

## 2026-06-15 (PR #173 backend CI 계층 위반 수정)

**수정**: GitHub Actions backend check가 `kortravelgeo.infra.epost_server_fetch -> kortravelgeo.loaders` import로 계층 규칙을 위반해 실패했다. T-207 server-fetch 서비스는 epost downloader/validation loader를 직접 재사용해야 하므로 파일을 `kortravelgeo.loaders.epost_server_fetch`로 이동하고 admin router import와 unit test monkeypatch 경로를 갱신했다.

## 2026-06-15 (T-207/PR #172 최종 검증)

**검증**: WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 전체 backend `pytest -q` 657 passed, 47 skipped, 24 warnings를 통과했다. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`도 통과했다.

**검증**: `kor-travel-geo-ui`에서 `npm run lint`, `npm run type-check`, `npm run test` 14 files/63 tests, `npm run build`를 통과했다. `npx react-doctor@latest . --offline --verbose --json`은 `ok=true`이고, T-207 변경으로 생긴 query invalidation/lazy state/unused export/native dialog 경고는 정리했다. 잔여 9개 warning은 기존 `lib/multipart-upload.ts`, `CurrentConfigTab.tsx`, `MatchSetsTab.tsx`, `ReconcileTab.tsx`의 접근성·구조 개선 항목이다.

## 2026-06-15 (T-207 epost server-fetch 완료)

**작업**: PR #172 리뷰 코멘트를 먼저 반영했다. `scripts/run_t213_live_pipeline.py`는 기본 DSN fallback을 제거하고 `--allow-destructive`와 기존 active match set 복구 경로를 추가했으며, 운영 promotion은 `--promote-active-match-set`으로 명시하게 했다. batch consistency/timeout/MV sample 관련 테스트는 문자열 source 검사 대신 fake handler/connection 기반 동작 검증으로 바꿨고, `discover_sido_datasets()`는 malformed 시도 폴더명을 오류 메시지에 포함한다.

**작업**: T-207로 `/v1/admin/source-files/epost-fetch`와 `infra.epost_server_fetch`를 추가했다. 서버는 epost ZIP을 내려받아 사서함/다량배달처 텍스트를 선택하고, T-120 검증 모듈로 검증한 뒤 RustFS source registry에 `single_file`로 등록하고 `pobox_load`/`bulk_load` job을 enqueue한다. `/admin/source-files` 업로드 탭의 `epost 받기` 버튼도 실제 endpoint에 연결했다.

**검증**: focused backend unit/ruff는 통과했다. 전체 backend/frontend 검증은 이어서 실행한다.

## 2026-06-15 (T-213 phase ② 전국 라이브데이터 로딩 완료)

**작업**: `scripts/run_t213_live_pipeline.py`를 추가해 전국 실 원천 6종을 RustFS source registry에 등록하고, `serving_recommended` source match set을 validate/activate한 뒤 rebuild-db source load를 실행했다. destructive 실행은 `--execute`와 `--typed-confirmation "RUN-T213-LIVE <database>"`를 요구하고, force promotion은 별도 사유를 요구하도록 했다.

**실행 결과**: source match set `6eb2b07b-f34f-460a-91ab-a5847a1e979e` 기준 source load 6개 job은 모두 성공했다. 최종 active serving release는 `96e60a10-695c-4a45-ad26-91422eb2f855`, dataset snapshot은 `856537e1-c8f2-44c9-8b8a-c51d0b99c494`다. row count는 `mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`, `tl_sppn_makarea=24,204`다. smoke로 `경기도 용인시 수지구 성복1로 35` geocode가 `OK` 후보를 반환했다.

**복구 및 보강**: 초기 batch root는 consistency case가 기본 5초 `statement_timeout`에 걸리고, fresh rebuild DB에서 `mv_geocode_target` 생성 전 sample point 보강이 실행되며 실패 이력을 남겼다. 이를 보강해 consistency case별 `SET LOCAL statement_timeout = 0`, MV 존재 시에만 sample point 보강, batch consistency ERROR의 promotion gate 위임, `registered` upload session terminal state, 전자지도 multi-sido staging parent 탐색을 추가했다. 패치 후 post-load recovery로 consistency report `consistency_7238f3fb50e347ccb8b3c6808402e656`와 `mv_refresh` job `job_9d3adfe221214bf3aceb69563a86812e`를 완료했다. 상세: `docs/t213-phase2-live-loading.md`.

**검증**: WSL ext4 테스트 미러에서 관련 ruff/focused unit을 통과했고, T-213 live run artifact는 `artifacts/t213-live-proper-20260614T225300Z/t213-live-recovery-summary.json`에 남겼다. 최종 전체 검증은 문서 갱신 뒤 다시 실행한다.

## 2026-06-15 (T-213 proper 선행 전환)

**작업**: 사용자가 “T-213을 먼저 해야 하면 그거부터 진행”이라고 지시해, T-214 성능평가·벤치 착수 전에 T-213 proper를 먼저 닫는 흐름으로 전환했다. PR #165는 세종 단일 slice 검증이므로, Codex 브랜치는 `agent/codex-t213-proper` 기준으로 전국 신규 파이프라인 적재 실행 경로와 안전장치를 먼저 확인한다.

**상태**: T-125는 T-119 승인 전 선행 gate로 유지하고, T-119는 T-125 완료 + ADR-051 accepted + 사용자 승인 전까지 계속 보류한다. T-214는 T-213 proper 산출물과 active serving release 확인 뒤 재개한다.

## 2026-06-15 (T-125 추가 및 T-214 착수)

**작업**: 사용자 지시에 따라 T-119를 바로 구현하지 않고, C11 출입구 후보의 serving 편입 승인 전 사전 검증 task를 T-125로 추가했다. T-125는 기존 `mv_geocode_target` 대표점 대비 impact, C3/C4/C6/C7 회귀, 성능 회귀, feature flag rollback, v1/v2 노출 정책을 ADR-051 accepted 전환 전 증거로 요구한다.

**상태**: PR #165(T-213 부분 세종 live end-to-end 검증)는 머지됐고, Codex가 post-merge 상세 리뷰 코멘트로 runbook destructive DB 동작 안전장치와 Markdown 한글 문서 정책 정리를 후속으로 남겼다. 현재 Codex 브랜치는 `agent/codex-t214-benchmarks`이며, 다음은 T-214 성능평가·벤치 실행 가능 범위를 확인한다.

## 2026-06-15 (T-124 T-110~T-123 리뷰 후속 검증 완료)

**검증**: WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 focused unit 56건, `ruff check .`, `mypy src/kortravelgeo scripts/benchmark_phase1_augment_performance.py scripts/run_phase1_augment_reports.py`, `lint-imports`, 전체 `pytest -q`를 통과했다. 전체 테스트 결과는 651 passed, 47 skipped, 24 warnings다. NTFS worktree에서 `git diff --check`를 통과했고, `codegraph sync`는 already up to date였다.

## 2026-06-15 (T-124 T-110~T-123 Claude 리뷰 재조사 후속 반영)

**작업**: 사용자 추가 지시에 따라 PR #137(T-110), #138(T-111), #140(T-112), #141(T-113), #143(T-114), #144(T-115), #146(T-116), #147(T-117), #148(T-118), #150(T-120), #155(T-121), #160(T-122), #161(T-123)의 Claude review comment를 다시 조사했다. 대상 PR 모두 GraphQL review thread 0건이었고, 남은 내용은 상위 감사 코멘트였다.

**반영**:
- T-110/T-115: 공통 SHP/DBF 파일·ZIP iterator와 C15 민원행정기관 POI reader를 stream 경로로 바꾸고, `.shp.xml` metadata sidecar가 SHP 후보가 되지 않게 했다.
- T-112: C12 road adjacency에 `road_geometry_missing`을 추가해 road key match와 road geometry 결손을 분리했다.
- T-113: 상세주소DB 숫자 필드를 parser 단계에서 검증하고, 비숫자는 `member:line` 문맥의 `LoaderError`로 실패하게 했다.
- T-114: C14 coverage용 row count가 DBF deleted record를 제외하도록 보정했다.
- T-110~T-118 문서에 `measure_key_overlap()`, full key/weak key 차이, C12 tolerance와 geometry 결손, C13 숫자 정규화, C14 row count, C17 sample SQL 해석 경계를 보강했다.

**검증**: 진행 중. WSL ext4 테스트 미러에 동기화한 뒤 focused unit, `ruff`, `mypy`, `lint-imports`, 전체 `pytest -q`를 다시 실행한다.

## 2026-06-15 (T-124 T-120~T-123 Claude 리뷰 후속 반영)

**작업**: PR #150(T-120), #155(T-121), #160(T-122), #161(T-123)의 Claude post-merge review와 inline review thread를 재확인하고 비차단 코멘트를 코드/문서에 반영했다. 네 PR 모두 unresolved inline thread 0건, blocking issue 0건이었다.

**반영**:
- T-120: `epost_validation`의 `empty_file` issue가 정상 디코딩 후 0행일 때만 붙는 흐름임을 주석으로 명시했다.
- T-121: C17 실행 분기를 명시하고, 현재 runner가 고정 staging table 이름을 쓰는 순차 실행 전제임을 주석화했다.
- T-122: `ResourceSampler` 종료 timeout을 보수화하고, `/proc/self/status` RSS 단위가 `kB`가 아니면 값을 버리도록 엄격화했다. benchmark Markdown 표는 컬럼 수 검증 helper로 생성하고, preparation 로그와 opt-in parser 테스트를 보강했다.
- T-123: C12/C16의 `_quote_ident_path`, `_quote_ident`, `_optional_float`, `_jsonb_sample` 중복 구현을 `augment_harness` import 재사용으로 줄였다.
- `docs/tasks.md`와 `docs/resume.md`에 T-124 완료 항목을 추가했다.

**검증**: WSL ext4 테스트 미러에서 focused unit 26건, `ruff check .`, `mypy src/kortravelgeo scripts/benchmark_phase1_augment_performance.py scripts/run_phase1_augment_reports.py`, `lint-imports`, 전체 `pytest -q`를 통과했다. 전체 테스트 결과는 649 passed, 47 skipped, 24 warnings다.

## 2026-06-14 (T-123 phase ① 튜닝·최종 검증 평가)

**작업**: T-122 benchmark를 기준으로 phase ① C11~C17 prototype의 staging 튜닝을 적용하고, warm-cache 전국 재측정과 최종 source별 go/no-go를 남겼다.

**반영**:
- `augment_harness`에 `StagingKeyIndexSpec`, staging key index SQL, `ANALYZE` helper를 추가했다.
- C11/C12/C16 staging table에 반복 조인 key btree index와 `ANALYZE`를 적용했다.
- T-122 `materialized/` cache를 hardlink로 재사용해 cold materialization 비용과 warm-cache case 실행 비용을 분리했다.
- C12는 같은 세션에서 no-index A/B(`artifacts/perf/t123-c12-noindex-live/`)를 실행했고, index 포함이 더 빨라 최종 코드에 유지했다.
- `docs/t123-phase1-acceptance.md`를 추가하고 `docs/tasks.md`, `docs/resume.md`, `docs/decisions.md`, `CHANGELOG.md`를 갱신했다.

**실행 결과**: WSL ext4 테스트 미러 `artifacts/perf/t123-phase1-tuned-live/`에서 C11~C17 전체를 3090.891초에 완료했고 실패 0건이었다. T-122 대비 preparation은 848.988초에서 0.059초로 분리됐고, C11은 1284.931초에서 1244.657초로 줄었다. C11 bundle ↔ 전자지도 full key는 intersection 6,405,305건, left overlap 0.992367, right overlap 0.999943, 거리 p95/max 0.0m다. C12~C17은 모두 validation-only로 확정했다.

**결정**: C11은 조건부 serving 후보로 유지하지만 ADR-051은 accepted로 전환하지 않는다. 기존 `mv_geocode_target` 대표점 대비 impact, C3/C4/C6/C7 회귀, feature flag rollback 검증이 아직 없으므로 T-119는 보류한다.

**검증**: WSL ext4 테스트 미러에서 focused unit test 26건, 관련 파일 `ruff check`, 관련 loader `mypy`를 통과했다. 전체 검증은 PR 전 최종 단계에서 다시 수행한다.

## 2026-06-14 (T-122 phase ① 보강 성능평가·벤치)

**작업**: T-121 전국 실행 runner를 재사용해 C11~C17 보강 검증 harness의 wall-time, runner process RSS, process I/O를 case별로 측정하는 T-122 benchmark script를 추가했다. 원천 materialization 비용은 `preparation` phase로 분리해 case 실행시간과 섞이지 않게 했다.

**반영**:
- `scripts/benchmark_phase1_augment_performance.py`를 추가했다. C11~C17 case 선택, 시도 선택, smoke limit, 전자지도 ZIP materialization, C17 7z materialization, PostgreSQL statement timeout, RSS sampling interval, Windows Git metadata 기록을 지원한다.
- `scripts/run_phase1_augment_reports.py`의 case 실행 함수를 `run_phase1_case()`로 공개 재사용 지점화했다.
- `tests/unit/test_t122_phase1_benchmark.py`로 parser, `/proc` parser, I/O delta, human byte formatter, benchmark JSON/Markdown 출력 계약을 고정했다.
- `docs/t122-phase1-augment-benchmark.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 갱신했다.

**실행 결과**: WSL ext4 테스트 미러 `artifacts/perf/t122-phase1-live/`에서 전체 3961.937초에 완료됐다. `preparation`은 848.988초, materialized cache 약 17GiB, local write 16.0GiB를 기록했다. C11~C17은 모두 실패 0건이며, case별 wall-time은 C11 1284.931초, C12 270.358초, C13 307.343초, C14 378.739초, C15 17.534초, C16 624.866초, C17 229.178초다. Peak RSS는 C12가 2.2GiB로 가장 높았다. 측정 범위는 runner process `/proc/self/status`와 `/proc/self/io`이며 PostgreSQL server I/O는 제외된다.

**검증**: NTFS worktree와 WSL ext4 테스트 미러에서 `pytest tests/unit/test_t122_phase1_benchmark.py tests/unit/test_t121_phase1_runner.py -q`, 관련 파일 `ruff check`, `mypy scripts/benchmark_phase1_augment_performance.py scripts/run_phase1_augment_reports.py`를 통과했다. WSL smoke로 C14 제한 실행 artifact 생성을 확인한 뒤 전국 full run을 완료했다.

## 2026-06-14 (T-121 phase ① 전국 라이브데이터 보강 실행)

**작업**: T-111~T-117 prototype을 fixture가 아니라 `F:\dev\kor-travel-geo\data\juso` 전국 실 원천으로 실행하는 T-121 runner를 추가하고, C11~C17 `AugmentReport`와 `source_yyyymm`을 산출했다. ADR-051은 아직 `proposed` 상태이므로 T-119 serving 좌표 scoring은 포함하지 않았다.

**반영**:
- `scripts/run_phase1_augment_reports.py`를 추가했다. C11~C17 case 선택, 시도 선택, sample limit, C14~C17 smoke limit, 전자지도 ZIP materialization, C17 `match_jibun_*.txt` 7z materialization, PostgreSQL statement timeout, Windows Git metadata 기록을 지원한다.
- `tests/unit/test_t121_phase1_runner.py`로 parser, source plan, 전자지도 materialization, summary JSON/Markdown 계약을 고정했다.
- 실제 `TL_SGCO_RNADR_DONG`에 `MULTIPOLYGON`이 포함되어 있어 C13 polygon staging geometry type을 `Geometry`로 넓혔다.
- C15 staging SQL type validator 계약에 맞춰 `source_x_5179`/`source_y_5179`를 `float8`로 고정했다.
- `docs/t121-phase1-live-augment.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`를 갱신했다.

**실행 결과**: WSL ext4 테스트 미러 `artifacts/augment/t121-live/`에서 전체 4305.836초에 완료됐다. C11~C13은 17개 시도 모두 `used=17`, C14~C17은 전국 단일 묶음 `used=1`, 실패 0건이다. C11 bundle ↔ 전자지도 full key는 intersection 6,405,305건, left overlap 0.992367, 거리 p95/max 0.0m다. C12 road key overlap은 0.999850이고 dangling connection ratio는 0.005790이다. C13 출입구 point containment는 0.964754, C14 formatter parent mismatch는 0건, C15 geocode match ratio는 0.976742다. C16/C17 `bd_mgt_sn` 직접 비교 0% 교집합은 T-123에서 key 계약/파서 차이를 재검토한다.

**검증**: NTFS worktree와 WSL ext4 테스트 미러에서 `pytest tests/unit/test_t121_phase1_runner.py tests/unit/test_c13_detail_dong.py tests/unit/test_c15_civil_service_poi.py -q` 및 관련 파일 `ruff check` 통과. WSL smoke로 세종/제한 실행 C11~C17 전체가 실패 0건임을 확인한 뒤 전국 full run을 완료했다. 최신 `origin/main` rebase 후 최종 WSL 검증은 `pytest -q` → 620 passed, 30 skipped, 24 warnings, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports` 통과다.

## 2026-06-14 (T-120 epost 우편번호 수동 적재·검증)

**작업**: epost 사서함·다량배달처 파일을 DB COPY 전에 검증하는 공통 모듈을 추가했다. T-207 server-fetch/RustFS register 흐름에서 같은 검증을 재사용할 수 있도록 파일 검증과 CLI 출력, 로더 hard gate를 분리했다.

**반영**:
- `src/kortravelgeo/loaders/epost_validation.py`를 추가했다. `utf-8-sig`/`cp949` 인코딩, 한글/영문 컬럼 alias, 행수, 필수 컬럼·값, 5자리 우편번호, `PO`/`PG` 사서함 종류, 사서함 번호 정수, 중복 key sanity를 검증한다.
- `pobox_loader.py`와 `bulk_loader.py`가 검증을 통과한 파일만 COPY하도록 했다. `copy_*_rows()`는 기존 row iterable 경로를 유지하고, 파일 기반 `load_*()` 진입점에서만 검증한다.
- `ktgctl load pobox`, `ktgctl load bulk`, `ktgctl load epost`, 선택 `load all-sidos --pobox/--bulk` 경로가 검증 요약을 출력한 뒤 적재한다.
- `download_epost_zip()`은 공공데이터포털 응답이 직접 ZIP이거나 `fileLocplc` XML인 경우를 모두 처리한다.
- GitHub Actions fresh dependency에서 최신 FastAPI가 lifespan 시작 전 `app.routes`를 flatten하지 않아도 route 계약 테스트가 `app.openapi()["paths"]`로 전체 path를 확인하도록 `tests/unit/test_api_app_contract.py`를 보강했다.
- `docs/t120-epost-postal-validation.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`, `docs/external-apis.md`를 갱신했다.

**검증**: NTFS worktree에서 `pytest tests/unit/test_epost_validation.py tests/unit/test_epost_downloader.py tests/unit/test_cli_contract.py -q` → 16 passed. WSL ext4 테스트 미러에서 `pytest -q` → 513 passed, 30 skipped, 24 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과.

## 2026-06-14 (T-118 phase 1 go/no-go 종합 + serving 편입 ADR 게이트)

**작업**: T-111~T-117 보강 검증 prototype 결과를 종합해 C11~C17의 phase ② registry 입력과 serving 편입 gate를 문서화했다. C11 출입구 계열만 조건부 serving 후보로 남기고, C12~C17은 검증 전용으로 판정했다.

**반영**:
- `docs/t118-phase1-go-no-go.md`를 추가했다.
- C11~C17 source별 판정, `source_yyyymm` evidence 요구, T-206 registry seed 입력, skip 조건, 주요 metric을 정리했다.
- 전자지도 잔여 layer `TL_SPBD_EQB`는 구조 검증 필수 evidence지만 C11~C17 어느 prototype에도 독립 귀속되지 않았으므로 serving 후보가 아니며, 필요하면 C18 또는 C13 확장으로 분리한다고 정리했다.
- `docs/decisions.md`에 ADR-051(proposed)을 추가했다. C11 serving 편입은 전국 metric, 기준월 gate, C3/C4/C6/C7 악화 없음, feature flag 기본 off, v1 호환 노출 정책을 통과하고 ADR이 accepted로 전환된 뒤에만 진행한다.
- `docs/tasks.md`, `docs/resume.md`를 갱신하고 다음 작업을 T-120으로 넘겼다. T-119는 사용자 승인 전까지 보류한다.

**검증**: `git diff --check` 통과. WSL ext4 테스트 미러에서 `pytest -q` → 465 passed, 30 skipped, 24 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports` 통과.

## 2026-06-14 (T-117 C17 내비 지번 member coverage 검증 prototype)

**작업**: `navi_full` archive 내부 optional member인 `match_jibun_*.txt`를 독립 category가 아니라 `navi_full.match_jibun` 검증 member로 다루는 C17 prototype을 구현했다. `tl_juso_parcel_link`와의 PNU/link coverage를 측정하고 좌표 적재나 serving 후보 승격은 하지 않는다.

**반영**:
- `src/kortravelgeo/loaders/c17_navi_jibun_coverage.py`를 추가했다.
- `match_jibun_*.txt` CP949 pipe text에서 `bjd_cd`, `mntn_yn`, 지번 본/부번, `rncode_full`, 건물번호, `bd_mgt_sn`을 streaming parser로 추출한다.
- PNU는 기존 `infra.pnu.build_pnu()`로 조립한다.
- staging table `_ktg_c17_navi_jibun`에 COPY한 뒤 `tl_juso_parcel_link`와 `bd_mgt_sn+pnu`, `pnu+rncode_full+buld_se_cd+buld_mnnm+buld_slno` key coverage를 비교한다.
- `match_jibun_*` member가 없으면 실패가 아니라 `skipped` report로 기록한다.
- 7z는 C17 모듈이 직접 subprocess로 풀지 않고, T-109/T-203 materialization 단계에서 풀린 디렉터리를 입력으로 받는 계약을 유지했다.
- `tests/unit/test_c17_navi_jibun_coverage.py`와 `tests/integration/test_optional_real_postgres_c17_navi_jibun_coverage.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이며, `.7z`만 있으면 WSL `7z`로 `match_jibun_sejong.txt` 한 member만 임시 materialize한다.
- `docs/t117-navi-jibun-coverage.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 465 passed, 30 skipped, 24 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과. 실제 `202604_내비게이션용DB_전체분.7z`에서 `match_jibun_sejong.txt` 한 member를 임시 materialize해 앞 3행 parser smoke를 확인했다.

## 2026-06-14 (T-116 C16 주소DB/건물DB row·key drift 검증 prototype)

**작업**: `주소DB_전체분`과 `건물DB_전체분`을 serving 정본이 아니라 row/key drift 검증 원천으로 다루는 C16 prototype을 구현했다. 좌표 적재 없이 text key만 staging하고, `tl_juso_text`, `tl_juso_parcel_link`, `tl_spbd_buld_polygon`과 distinct key overlap 및 left/right-only sample을 비교한다.

**반영**:
- `src/kortravelgeo/loaders/c16_address_building_drift.py`를 추가했다.
- 주소DB ZIP member 이름이 mojibake로 보이는 문제를 `cp437` bytes → `cp949` 복원으로 처리했다.
- `주소_*.txt`, `부가정보_*.txt`, `지번_*.txt`, `build_*.txt`, `jibun_*.txt`에서 비교에 필요한 key만 streaming parser로 추출한다.
- PNU는 기존 `infra.pnu.build_pnu()`를 사용한다.
- staging table `_ktg_c16_*`에 COPY한 뒤 `tl_juso_text`/`tl_juso_parcel_link`/`tl_spbd_buld_polygon`과 `bd_mgt_sn`, `bd_mgt_sn+pnu`, 건물 natural key, `pnu+road key`를 비교한다.
- `key_drift_sample_sql()`은 `EXCEPT` 기반 `left_only`/`right_only` sample을 산출한다.
- `C16AddressBuildingDriftComparison.metrics()`에 `coordinate_load=False`, `serving_promotion=False`를 고정했다.
- `tests/unit/test_c16_address_building_drift.py`와 `tests/integration/test_optional_real_postgres_c16_address_building_drift.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이다.
- `docs/t116-address-building-drift.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 432 passed, 29 skipped, 24 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과. 실제 ZIP parser smoke로 `202605_주소DB_전체분.zip`/`202605_건물DB_전체분.zip` 각각 17개 시도 member와 road-code member를 확인하고 앞 1행 key parsing을 확인했다.

## 2026-06-14 (T-115 C15 민원행정기관 POI 거리 검증 prototype)

**작업**: `민원행정기관전자지도`를 주소 정본이 아닌 POI 검증 원천으로 다루는 C15 prototype을 구현했다. SHP point와 `도로명주소`를 기존 geocoder exact road lookup 계약으로 얻은 대표점과 비교해 거리 분포와 이상치 sample을 산출한다. 기관명/기관 좌표는 일반 주소 후보나 vworld 호환 응답에 섞지 않는다.

**반영**:
- `src/kortravelgeo/loaders/shape_dbf.py`와 `augment_harness.py`에 DBF field name encoding 선택 인자를 추가했다. 기본값은 `ascii`로 유지하고 C15에서만 `cp949` 한글 field name을 사용한다.
- `src/kortravelgeo/loaders/c15_civil_service_poi.py`를 추가했다. ZIP member 파일명이 mojibake로 보일 수 있어 layer name 대신 단일 `.shp`/`.dbf` suffix를 찾는다.
- C15 staging table `_ktg_c15_civil_service_poi`에 기관 context, 원천 point, 파싱된 도로명주소 key를 COPY한다.
- `civil_service_poi_geocode_distance_sql()`은 `mv_geocode_target`을 batch exact road lookup 조건으로 join하고 `ST_Distance` p50/p95/max, geocode missing, geocode point missing, parse failed, outlier sample을 집계한다.
- `tests/unit/test_c15_civil_service_poi.py`와 `tests/integration/test_optional_real_postgres_c15_civil_service_poi.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이다.
- `docs/t115-civil-service-poi.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 424 passed, 28 skipped, 24 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과. 실제 ZIP parser smoke로 `민원행정기관전자지도_240124.zip` 앞 3행을 읽어 `청운중학교`/`창의문로` 파싱을 확인했다. PostGIS 거리 smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형으로 추가했다.

## 2026-06-14 (T-114 C14 국가지점번호 grid/center 검증 harness)

**작업**: `국가지점번호 도형` SHP/DBF와 `국가지점번호 중심점` TXT를 상시 적재 없이 검증하는 C14 harness를 구현했다. 목적은 `core/sppn.py` parser/formatter 회귀, prefix 중심점 일치, resolution별 grid coverage 확인이며, 10m 좌표 정확도 개선 원천으로 승격하지 않는다.

**반영**:
- `src/kortravelgeo/loaders/c14_national_point_grid.py`를 추가했다.
- 100km/10km/1km/100m grid prefix를 EPSG:5179 bbox/center로 해석하는 `parse_grid_code()`와 formatter parent prefix 검증 helper를 추가했다.
- `TL_SPPN_GRID_100M` 1천만 polygon도 ZIP member 전체를 inflate하지 않도록 C14 전용 SHP/DBF record streaming iterator를 추가했다.
- 중심점 TXT(`prefix|x_5179|y_5179`) parser와 center 좌표 mismatch, formatter parent mismatch, resolution별 row count coverage metric을 추가했다.
- `C14NationalPointGridComparison.metrics()`에 `serving_promotion=False`와 제한 실행 여부를 나타내는 `coverage_count_basis`를 고정했다.
- `tests/unit/test_c14_national_point_grid.py`와 `tests/integration/test_optional_real_c14_national_point_grid.py`를 추가했다. 실제 ZIP smoke는 `KTG_SLOW_REAL_DATA=1` 선택형이다.
- `docs/t114-national-point-grid.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 374 passed, 27 skipped, 19 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports` 통과. `KTG_SLOW_REAL_DATA=1 pytest tests/integration/test_optional_real_c14_national_point_grid.py -q` → 1 passed.

## 2026-06-14 (T-113 C13 상세주소 동 containment 검증 prototype)

**작업**: `건물군 내 상세주소 동 도형` bundle의 상세주소 동 polygon/동 출입구 point와 `상세주소DB_전체분` `adrdc_*.txt`를 연결하는 C13 prototype을 구현했다. TXT에는 좌표가 없으므로 `ST_Covers` containment는 `TL_SGCO_RNADR_DONG` polygon이 같은 `SIG_CD + BUL_MAN_NO`의 `TL_SPBD_ENTRC_DONG` point를 덮는지 측정하고, 상세주소DB는 key overlap과 address-matched coverage context로만 쓴다.

**반영**:
- `src/kortravelgeo/loaders/c13_detail_dong.py`를 추가했다.
- `상세주소DB 활용가이드` 기준 16컬럼 MS949 pipe parser를 추가하고 시도별 `adrdc_*.txt` member 매핑을 고정했다.
- `BD_MGT_SN` ↔ `building_management_no`, 도로명주소 연계키(`SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`) ↔ TXT 도로명주소 key, 동 출입구 `SIG_CD + BUL_MAN_NO` ↔ polygon `SIG_CD + BUL_MAN_NO` overlap을 측정한다.
- polygon/entrance `ST_Covers` coverage와 상세주소DB key가 match된 pair의 coverage를 별도 metric으로 남긴다.
- `tests/unit/test_c13_detail_dong.py`와 `tests/integration/test_optional_real_postgres_c13_detail_dong.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이다.
- `docs/t113-detail-dong-containment.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 365 passed, 26 skipped, 19 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과.

## 2026-06-14 (T-112 C12 건물 도형 connection line 검증 prototype)

**작업**: `도로명주소 건물 도형` bundle의 `TL_SPOT_CNTC` polyline을 전자지도 `TL_SPRD_MANAGE` 도로 관리선과 비교하는 C12 prototype을 구현했다. 이번 작업은 measurement-only이며 운영 C8 SQL, serving 좌표, API 응답은 변경하지 않는다.

**반영**:
- `src/kortravelgeo/loaders/c12_connection_lines.py`를 추가했다.
- bundle `TL_SPOT_CNTC`와 전자지도 `TL_SPRD_MANAGE`를 staging 적재하고, `RDS_SIG_CD + RDS_MAN_NO` ↔ `SIG_CD + RDS_MAN_NO` key overlap을 측정한다.
- key가 match된 connection/road line 간 `ST_Distance` p50/p95/max를 산출한다.
- road key가 없거나, key가 있어도 line 간 최단거리가 tolerance(기본 1m)를 넘는 connection을 dangling으로 집계하고 sample을 남긴다.
- T-040의 connection ↔ bundle entrance 참조 overlap도 C12 payload에 포함한다.
- `tests/unit/test_c12_connection_lines.py`와 `tests/integration/test_optional_real_postgres_c12_connection_lines.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이다.
- `docs/t112-c12-connection-lines.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 359 passed, 25 skipped, 19 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과.

## 2026-06-14 (T-111 C11 출입구 원천 간 거리 검증 prototype)

**작업**: 건물 도형 bundle `TL_SPBD_ENTRC`를 staging에 올려 기존 출입구 원천과 key overlap 및 거리 분포를 측정하는 C11 prototype을 구현했다. 이번 작업은 measurement-only이며 serving 좌표 ranking이나 API 응답은 변경하지 않는다.

**반영**:
- `src/kortravelgeo/loaders/augment_harness.py`에 staging/운영 테이블 간 key overlap 측정 helper(`KeyOverlapMeasurement`, `key_overlap_sql`, `measure_key_overlap`)를 추가했다.
- `src/kortravelgeo/loaders/c11_entrance_sources.py`를 추가했다. bundle/electronic `TL_SPBD_ENTRC`를 staging 적재하고 `ST_Distance` p50/p95/max와 key overlap을 산출한다.
- bundle ↔ 전자지도는 `ENTRANCE_KEY_FIELDS` full key(`SIG_CD`, `BUL_MAN_NO`, `ENT_MAN_NO`, `EQB_MAN_SN`)로 비교한다.
- bundle ↔ `tl_locsum_entrc` / `tl_roadaddr_entrc`는 운영 테이블이 `BUL_MAN_NO`/`EQB_MAN_SN`을 보존하지 않으므로 `sig_cd + ent_man_no` weak key로 측정하고, 결과에 `key_contract`/`note`를 남긴다.
- `tests/unit/test_c11_entrance_sources.py`와 `tests/integration/test_optional_real_postgres_c11_entrance_sources.py`를 추가했다. 실제 PostGIS smoke는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형이다.
- `docs/t111-c11-entrance-sources.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 329 passed, 24 skipped, 14 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과.

## 2026-06-14 (T-110 보강 검증 공통 harness)

**작업**: Codex 담당 phase ① 첫 작업인 T-110을 구현했다. 특정 보강 원천의 결론을 넣지 않고, T-111~T-117 prototype이 공유할 시도별 순회·SHP geometry·staging·PostGIS 측정 기반만 추가했다.

**반영**:
- `src/kortravelgeo/loaders/augment_harness.py` 신규 추가.
- 17개 시도 `SidoSourceGroup` discovery, `AugmentReport`/`AugmentGroupResult`/`AugmentGroupPayload` 집계 모델을 추가했다.
- SHP body parser가 `Point`, `PolyLine`, `Polygon` record를 읽고 DBF row와 맞춘 `ShapeFeature` iterator를 제공한다. ZIP 내부 layer도 직접 읽을 수 있다.
- PostGIS staging table 생성 SQL, `COPY FROM STDIN` helper, key join 기반 `ST_Distance`/`ST_Covers` 측정 helper를 추가했다.
- `tests/unit/test_augment_harness.py`로 synthetic SHP/DBF parser, 시도 group discovery, report 집계, SQL 계약을 검증한다.
- `tests/integration/test_optional_real_postgres_augment_harness.py`는 `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN`이 있을 때만 실제 PostGIS COPY/측정을 smoke 검증한다.
- 전체 테스트를 위해 `tests/integration/test_real_roadaddr_entrance_files.py`가 현재 원천 배치인 `도로명주소 출입구 정보/<YYYYMM>/*.zip`도 찾도록 보정했다.
- `docs/t110-augment-harness.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**검증**: WSL ext4 테스트 미러에서 `pytest -q` → 325 passed, 23 skipped, 14 warnings. `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 통과. Windows CodeGraph `sync`/`status`도 up-to-date 확인.

## 2026-06-14 (PR #131 — 각 phase 끝에 라이브 적재·벤치·튜닝·최종검증 task 추가)

**작업**: 사용자 요청으로 phase ①·②의 마지막에 "전국 라이브데이터 실행/로딩 → 성능평가·벤치 → 튜닝·최종 검증 평가"를 task로 추가했다. 기존 T-118(prototype go/no-go)·T-210(fixture 통합·기능 검증)과 중복되지 않도록, 새 task는 fixture가 아닌 **전국 production 규모 실데이터** 실행과 벤치·튜닝·최종 acceptance로 범위를 구분했다.

**추가**:
- phase ①: T-121(전국 라이브데이터 보강 실행) → T-122(보강 성능평가·벤치) → T-123(튜닝·최종 검증 평가, T-118 go/no-go 최종 확정).
- phase ②: T-213(전국 라이브데이터 로딩 — T-109 신규 파이프라인으로 full load, T-027 행수와 동치 확인) → T-214(성능평가·벤치, T-047/T-035 harness) → T-215(튜닝·최종 검증 평가 — geocode/reverse 정확도·v1/v2 회귀·C1~C17 정합성, N150/Odroid 실측은 T-063 연계, T-109 전체 acceptance).
- ADR-050 #8 범위를 `T-200~T-215`로, resume.md를 `T-110~T-123`/`T-200~T-215`로 동기화.

**검증**: 문서/백로그-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 Task 재점검 — T-212 추가)

**작업**: PR #131 최신 conversation/review/thread를 다시 읽고(`review_threads` 0건), `docs/tasks.md`의 T-110~T-120 / T-200~T-211 / T-105·T-106을 PR 리뷰 항목과 교차 점검했다. `f3c4c93`에서 잔여 L 4건과 T-211 관측성은 이미 반영되어 있었지만, 리뷰 초반부터 반복된 RustFS 무기한 보존·용량 정책은 T-211 metric만으로는 닫히지 않는 별도 운영 정책/관리 표면으로 판단했다.

**반영**:
- 신규 **T-212**를 추가했다. scope는 RustFS 원천 archive 보존·정리 정책 ADR + 관리 표면이다.
- 기본 원칙은 등록 완료 원천 archive 자동 삭제 금지, 사용자 수동 admin UI 삭제, destructive_admin typed confirmation, audit/metric/UI 경고 유지로 고정했다.
- capacity threshold, archive tier, `soft_deleted`/`quarantined` retention, 미등록 stored object SLA, bulk hard-delete/restore, 삭제 전 manifest/export 확인을 T-212 산출물로 묶었다.
- ADR-050과 resume의 phase ② 범위를 `T-200~T-212`로 동기화했다.

**검증**: 문서/백로그-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 L 폴리시 + Task 완전성 보강)

**작업**: (1) head `4142570` 재리뷰의 잔여 L 4건을 닫고, (2) T-110~T-120 / T-200~T-211 / T-105·T-106 백로그를 4축(phase② 설계 커버리지·phase①/ADR·cross-cutting glue·의존성/시퀀싱) 멀티에이전트 + 적대 검증으로 점검해 확정 gap을 task에 반영했다. 설계 자체는 머지 가능 상태이고, 이번 변경은 전부 문서/백로그 정합이다.

**L 폴리시(4)**:
- `recompute_group_aggregates` 계약표 입력 예시에 `child_soft_delete`/`child_hard_delete` 트리거를 추가해 인접 prose 호출자 목록과 일치시켰다.
- upload-session 목록 API 재개 상태 예시에 `failed_storage_state`를 넣어 slot 재업로드 복구 흐름을 목록에서 찾을 수 있게 했다.
- T-204에 RustFS bucket 전체 손실/prefix 대량 손상 시 전수 `source_file_unavailable`+active `integrity_alert`/비-active `validated` `invalid` 전파를 명시했다.
- `validator_version_change` 재검증 트리거를 T-203(recompute) / T-206(run-validation)에 명시했다.

**Task 보강(확정 gap, 적대 검증 통과)**:
- T-200: full-prefix rename은 breaking change이므로 `CHANGELOG.md`(BREAKING)+migration-guide(전체 ID 매핑표·admin route 변경·재생성 안내)를 산출물로 포함.
- T-201: `/v1/admin/uploads` 폐기로 깨지는 공개 `AsyncAddressClient` upload-set 메서드와 `ktgctl load full-set` CLI 제거를 Python 라이브러리(ADR-039)·CLI breaking change로 명시.
- T-202: 신규 source 관리 액션의 audit `event_type` 집합 정의 + `actor_type` CHECK가 `system:<job_kind>`를 수용하는지 확인.
- T-203: upload-session SSE events endpoint(`source_upload.progress`·polling fallback)를 명시.
- T-209: 의존을 `T-201~T-208`로 확장하고 "epost 받기" 버튼+fetch SSE 상태(T-207), 현재 구성 탭 복원 파생 표시(T-208)를 scope에 추가.
- T-210: 의존을 `T-205·T-206·T-207·T-208·T-209`로 보정하고 백엔드 fixture 27 + 백엔드 openapi.json/api.gen.ts drift, 장비 비종속 성능(T-063 분리)으로 경계 명확화.
- **신규 T-211**(source registry 관측성): upload/reconcile/janitor/저장소 용량 prometheus metric + admin UI 용량 카드(의존: T-203·T-204·T-209).
- T-106: wire 100% 채택 시 `x_extension.*` 비표준 필드 처리 정책을 RFC에 포함.
- T-118: 미사용 전자지도 layer `TL_SPBD_EQB` 검증 대상화 여부 판정 포함.

**적대 검증으로 기각(보강 안 함)**: legacy DB backfill(ADR-049 #18로 read-only fallback이 의도된 동작), 신규 ktgctl source 명령(설계가 API+UI로만 routing), phase① 문서 정합 단일 owner(표준 워크플로가 소유), T-208↔T-206 의존(도메인 불일치).

**검증**: 문서/백로그-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 리뷰 재반영 — 누락 시나리오 정밀화)

**작업**: PR #131 최신 리뷰에서 지적된 운영 시나리오 누락을 `docs/t109-backup-source-upload-management.md`·ADR-049·`docs/tasks.md`·`docs/resume.md`에 재반영했다. 문서 방향은 호환성/최소수정보다 확장성·완성도·일관성·성능을 우선하고, 외부 인터페이스 변경은 구현 task에서 OpenAPI/문서/프론트 타입 동기화까지 포함하도록 고정했다.

**반영**:
- RustFS multipart DB/storage 불일치 경로를 `failed_storage_state`로 명시하고, resume 시 RustFS `ListParts` 또는 호환 API로 multipart upload id 존재를 먼저 확인하도록 했다.
- janitor는 PostgreSQL advisory lock 기반 admin service/CLI periodic job으로 두고, 미완 multipart abort와 session 만료 전이만 자동 처리하며 저장 완료 object는 자동 삭제하지 않는 경계로 고정했다.
- active match set의 `integrity_alert` 해제는 `POST /validate` active validate-in-place로만 확정하고, rollback은 source match set one-active invariant 안에서 current retire + target active restore + quick reconcile 재계산을 수행하도록 정리했다.
- `forced_promotion=true`는 consistency ERROR 승격 차단만 우회하며, source archive integrity gate·unavailable group·selected match set `integrity_alert=true`는 우회할 수 없다고 명시했다.
- epost 수동 server-fetch의 fetch 실패, ZIP 구조 불일치, 기준월 mismatch를 별도 session/report 상태로 드러내고 핵심 rebuild와 분리했다.
- `restored_from_backup` stub의 `manifest.group_sha256`은 신뢰값이 아니라 비교 대상이며, storage SHA-256/size와 group hash를 재계산하고 구조 validator가 통과한 뒤에만 `available`로 전이하게 했다.
- 통합 fixture 시나리오를 27개로 확장하고 T-210 범위를 맞췄다.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 최종 정합성 sweep — 최적안 반영)

**작업**: head ab38693에 대해 정합성 sweep(상태머신 + t109↔ADR-049/050↔tasks.md 교차)을 한 번 더 돌려, 확정된 7건(0 기각) 중 doc-정합 항목을 각각 최적안으로 반영했다. 직전 M-A 옵션2 전파 이후 단일 출처(recompute 계약·ADR·테스트)에 restored_from_backup 복구 경로가 일부 누락돼 있던 것을 통일했다.

**반영**:
- recompute_group_aggregates 상향 전파 계약(L345)에 `restored_from_backup → revalidatable`(선-hash 산출)과 **이 전이의 소유자(=recompute, restore 같은 transaction)**를 명시. 요약(L1932)·구현 순서 4단계(L1929)도 동일하게 보강.
- 통합 테스트 #23(L2057)을 정본 시퀀스(group/file `missing→validating→available`, match set `restored_from_backup→revalidatable→validate→validated`, 선-hash)로 정정.
- ADR-049 결정12를 "invalid는 비-active 중 `validated`만(pre-hash 제외), revalidatable은 invalid·restored_from_backup(선-hash 후)"로 본문/결정14와 정합화.
- tasks.md T-204 `issue_type` 개수 11→**12**, 약식 `group_incomplete`→`source_file_group_incomplete`로 정본 표와 일치.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인. H/블로커 0건, 잔여는 운영 hardening(구현 PR 이관)뿐.

## 2026-06-14 (PR #131 코멘트 반영 — M-A 옵션2 전파 / M-B / L-A 마무리)

**작업**: PR #131 코멘트(issuecomment, head b85e0d5 리뷰)의 M-A/M-B/L-A를 `docs/t109-backup-source-upload-management.md`·`docs/tasks.md`에 반영했다. M-A 옵션 2(restored_from_backup→revalidatable 진입 전 hash 선산출)를 택했으면서 일부 문구가 "비-active=invalid"로 일반화돼 남아 있던 것을 전 문서에 통일했다.

**반영**:
- **M-A 전파**: `state='invalid'` 전이를 "비-active **중 `validated`만**, `draft`/`restored_from_backup` 같은 pre-hash 상태는 유지"로 모든 산문·커버리지 표·테스트·구현순서·tasks.md T-205까지 통일(L343/345/788/1516/1548/1580/1931/2042/2045 + tasks L33). pre-hash(NULL hash) 상태가 hash NOT NULL을 요구하는 invalid로 가서 CHECK 충돌 나던 문제 제거.
- **M-B**: `source_set_hash` 일반 lifecycle 문단(validate에서 산출)에 "단, `restored_from_backup`은 revalidatable 진입 전 canonical hash 선산출(옵션 2), validate에서 재검산·확정" 예외를 명시.
- **L-A**: 커버리지 표 'active match set 활성화' 행의 "active 0건 창"을 본문과 같이 "외부 관찰 가능한 active gap/unique 위반 없음(내부 순간 상태 무관)"으로 통일.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (T-109 후속 작업 분해 — T-110~/T-200~ 등록 + ADR-050 + T-105/T-106)

**작업**: PR #131 문서·코드를 다시 정독한 결과로 후속 구현 task를 잘게 나눠 `docs/tasks.md`에 등록하고 ADR-050으로 순서·번호 체계를 고정했다. 4영역(v1 vworld 호환 / v2 audit / T-109 적재·백업 구현 / 원천 보강) 병렬 정독 + 누락 critic을 거쳐 작성했다.

**반영**:
- 작업 순서 = ① 데이터 원천 보강·검증(**T-110~T-120**) → ② 데이터 적재/백업 구현·검증(**T-200~T-210**) → (최하위) **T-105 v2 재audit** · **T-106 v1 vworld 100% 호환**. T-105/T-106은 ID는 낮지만 순위 최하위. T-109(이 PR)는 ②의 설계 문서이며 구현을 T-200대로 분할.
- phase ① prototype은 ops registry 없이 로컬 디스크 경로로 독립 수행(역의존 금지), C11~C17은 phase ①에서 prototype·phase ②(T-206)에서 DB case registry 정식화. 보강 자료 serving 편입(T-119)은 별도 ADR 게이트(T-118) 승인 후에만.
- critic이 짚은 누락(prototype↔registry seed bridge, pobox/bulk 공유 검증 모듈, v1 NOT_FOUND status spike, fresh init-db drift 게이트)을 해당 task에 흡수.
- `docs/tasks.md` 대기 섹션 재구성 + `docs/decisions.md` ADR-050 추가 + `docs/resume.md` 갱신.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인. (PR까지만 진행 — 구현 착수는 안 함.)

## 2026-06-14 (PR #131 신규 코멘트 반영 — M-A 옵션2 / L-A / L-B)

**작업**: PR #131 코멘트(issuecomment-4700672694)의 M-A(사용자 지시: 옵션 2)·L-A·L-B를 `docs/t109-backup-source-upload-management.md`·`docs/decisions.md`에 반영했다.

**반영**:
- **M-A (옵션 2)**: `restored_from_backup → revalidatable` 전이가 `source_set_hash` CHECK(`revalidatable`은 hash NOT NULL 요구)와 충돌하던 문제를, **revalidatable 진입 전 canonical hash 산출을 선행 조건**으로 두어 해소했다. revalidatable 정의/전이 규칙/복원 절차 step 9/커버리지 표/ADR-049 결정 14를 모두 "hash 산출 후 전이"로 통일. 더불어 NULL-hash pre-hash 상태(`draft`/`restored_from_backup`)는 hash를 요구하는 `invalid`로 가지 않도록 invalid 전이 대상을 `validated`로 한정(같은 CHECK 충돌 제거). DDL CHECK 자체는 변경 불필요(NULL 허용은 draft/restored_from_backup뿐, 옵션 2와 정합).
- **L-A**: activate atomic swap 문구를 "advisory lock + 단일 transaction, retire→activate 순서, **외부 관찰 가능한 active gap/unique 위반** 금지(transaction 내부 순간 상태는 무관)"로 완화.
- **L-B**: `duplicate_object` 보호 문구의 모호한 "integrity_alert=false active source"를 "active match set이 참조하는 object(integrity_alert 무관) + draft/validated 참조 정본"으로 명확화.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 재리뷰 M 3건 문서 정합 반영)

**작업**: head 189729e 재리뷰에서 남은 Medium 3건(전부 문서 정합)을 `docs/t109-backup-source-upload-management.md`·`docs/decisions.md`에 반영했다. H/블로커는 없었고 직전 잔여는 거의 다 닫힌 상태였다.

**반영**:
- **M-A**: `restored_from_backup → revalidatable → validated` 전이를 match set 상태 전이 규칙 본문에 정식 추가하고, `revalidatable` 정의를 "`invalid` 또는 `restored_from_backup`에서 복구"로 확장했다(정본 규칙 vs restore 절차/ADR 불일치 해소).
- **M-B**: ADR-049 결정 14와 커버리지 표의 압축 화살표(`validating→passed/warning→available→revalidatable→validated`)가 group state·validation_state·match set state 3개 머신을 한 체인에 섞던 것을 group/file 머신과 match set 머신 2단계로 분리 표기했다.
- **M-C**: `last_deep_verified_at` 컬럼만 있고 정기 강제 deep 정책이 없던 것을, "경과 object는 quick에서도 강제 deep(또는 rolling deep)"으로 명문화했다(same-size/etag 변조 안전망). reconcile 절·커버리지 표에 반영.

**남김**: Low 잔여(group/file state 전이 그래프, 용량 임계 1차 동작, transient 재시도, validator_version 하향 전파, env case_def seed drift, portable match-set export, forced_promotion batch terminal state 등)는 운영 hardening이라 T-200대 구현 PR/후속 ADR로 이관 권장.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 잔여 운영 시나리오 재반영)

**작업**: PR #131 conversation comment를 다시 확인했다. 최신 신규 코멘트는 `IC_kwDOSW_crs8AAAABGCx8WQ`, `IC_kwDOSW_crs8AAAABGCyhBA`, `IC_kwDOSW_crs8AAAABGCzORQ`였고, review thread는 0건이었다. 원격의 `d9ae209`, `999fac3`를 fast-forward로 받은 뒤 잔여 M/L 시나리오를 문서에 추가 반영했다.

**반영**:
- ADR-049의 옛 표현(active match set이 object 결손 시 `invalid`)을 `state='active'` 유지 + `integrity_alert=true`로 정정했다.
- `soft_deleted` source group/file을 `restore` action으로 되살리는 절차와 RustFS head/hash 검증, `validating -> available` 전이를 추가했다.
- upload session 중복 생성 `409`, register 전 완료 slot `replace`, `expires_at`/`registration_deadline_at` 기본 정책, `registration_expired` issue, janitor 동작을 추가했다.
- restore hot-swap 직후 source quick reconcile과 `restored_from_backup` stub의 `unknown -> validating -> available -> revalidatable -> validated` 순서를 명시했다.
- `recompute_group_aggregates()`가 하향 invalid/alert 전파뿐 아니라 복구 시 `revalidatable`/alert 해제 후보 전파도 담당하도록 구현 지침과 테스트 계획을 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (T-109 시나리오 재검 H1 정정 — active match set integrity_alert 분리)

**작업**: 시나리오 재검에서 발견된 H1 자기모순(active match set이 `invalid`로 전환된다는 규칙 ↔ one-active 슬롯 유지가 양립 불가; one-active index가 `WHERE state='active'`라 state를 invalid로 바꾸면 슬롯이 빔)을 `docs/t109-backup-source-upload-management.md`에 정정했다.

**반영**:
- `ops.source_match_sets`에 `integrity_alert BOOLEAN`/`integrity_alert_at`/`integrity_alert_detail`을 추가해 원천 무결성 결손을 `state`와 분리했다.
- 상태 전이 규칙을 active/비-active로 분기: **active**는 결손 시 `state='active'` 유지 + `integrity_alert=true`(슬롯·serving 유지, 재구성만 불가), **비-active**(draft/validated/restored_from_backup)만 `state='invalid'`. 복구 시 active는 validate 성공으로 `integrity_alert=false`, 비-active는 `invalid→revalidatable→validate→validated`.
- 이 구분이 reconcile/rebuild 게이트/run-validation 등 group이 missing/quarantined가 되는 모든 경로에 동일 적용됨을 명문화. group 집계 규칙·state 표·커버리지 표·구현 순서·테스트(backend/통합)도 일관되게 갱신.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (T-109 추가 결정 2건 — 자동탐지 제거 / epost 수동 server-fetch)

**작업**: 사용자 결정 2건을 `docs/t109-backup-source-upload-management.md`에 반영했다.

**반영**:
- **자동탐지(`guess_source_kind`) 제거**: "충돌 지점 #1"을 "호환 유지" migration에서 **자동탐지 기능 제거 + 명시 category 업로드 단일화**로 변경했다. source kind는 추정하지 않고 사용자가 고른 category에서 결정론적으로 전개한다. 기존 `/v1/admin/uploads` upload set 흐름은 폐기하고 `/v1/admin/source-files/upload-sessions`로 단일화(admin breaking change, OpenAPI/DTO/CLI/changelog 명시). 요구사항 매트릭스 #1도 갱신했다. 서비스 전이라 호환 alias를 쌓지 않는다.
- **epost 우편번호 자료 수동 server-fetch**: `epost_pobox_full`/`epost_bulk_full`을 "epost 받기" 클릭 → 서버측 다운로드 → RustFS register → `pobox_load`/`bulk_load`로 DB 반영 → 우편번호 검증, 의 별도 수동 흐름으로 정리했다("epost 우편번호 자료" 절 신설). 우편번호는 보조 자료라 `source_match_set` 핵심 rebuild에는 넣지 않고 독립 적재한다. 이 server-fetch는 "자동 다운로드 제외"의 명시적 예외(사용자 클릭 트리거 전용, 자동·스케줄 없음)임을 범위 절에 명시했다.

**검증**: 문서-only 변경. `git diff --check`로 공백 오류 확인.

## 2026-06-14 (PR #131 시나리오 누락 집중 리뷰 반영)

**작업**: PR #131의 최신 conversation comment `IC_kwDOSW_crs8AAAABGCujRg`를 확인했다. review thread는 여전히 0건이고, 새 코멘트는 head `281bc82` 기준 end-to-end 운영 시나리오 누락 집중 리뷰였다.

**반영**:
- `docs/t109-backup-source-upload-management.md`에 진행 중 upload session 목록/재개 API와 UI "재개 가능한 업로드"를 추가했다.
- RustFS object가 registry 등록 대기 중인 정상 상태를 `pending_registration`으로 분리하고, `registration_deadline_at` 전에는 deletion 후보가 아니라고 명시했다.
- match set state에 `revalidatable`을 추가하고, `activate` atomic swap, active match set invalid의 의미(serving 장애가 아니라 재구성 가능성 결손), invalid 복구 전이를 문서화했다.
- `rebuild-db`에 전역 advisory lock, stale running job 실패 마감, staging 재초기화, consistency ERROR 승격 차단, `forced_promotion=true` 강제 승격 감사 규칙을 추가했다.
- 백업 복원 후 `restored_from_backup` match set은 manifest item별 `missing` stub group/file을 생성하고, source object availability 확인 전에는 rebuild 입력으로 활성화하지 않는 lifecycle을 추가했다.
- ADR-049, `docs/tasks.md`, `docs/resume.md`, 테스트 계획을 새 시나리오 계약에 맞춰 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 추가 코멘트 재확인 — T-109 시나리오 누락 검토)

**작업**: PR #131의 최신 conversation comment와 review thread 상태를 다시 확인했다. unresolved review thread는 없고, 원격 head `281bc82`의 rebuild 적재 전 무결성 게이트 반영이 최신 추가 코멘트의 핵심이었다. 이 반영을 기준으로 T-109 설계에서 운영 시나리오 누락이 있는지 다시 검토했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`에 "운영 시나리오 커버리지 점검" 표를 추가했다. 업로드 세션 생성, multipart 중단/재개, registry insert 실패, multi-part 누락, RustFS 직접 변경, match set 활성화, rebuild, run-validation, 백업/복원, current source `알수없음`, admin role gate, active 참조 hard-delete 차단까지 구현자가 놓치기 쉬운 분기를 한 표에 묶었다.
- `run-validation`도 optional 자료가 존재하면 materialize 직후와 validator 실행 직전 registry hash/size를 대조하고, mismatch는 `skipped`가 아니라 `failed/source_integrity_mismatch`로 기록하도록 명시했다.
- 백업 복원 후 reconstructed match set은 read-only이며, RustFS source archive 존재와 hash를 확인하기 전까지 rebuild 입력으로 바로 활성화할 수 없다고 보강했다.
- ADR-049에 `rebuild-db`/`run-validation` 사용 직전 무결성 게이트를 확정 결정으로 추가했다.
- `docs/tasks.md`와 `docs/resume.md`에 이번 시나리오 커버리지 검토 결과를 반영했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 잔여 finding 반영 — rebuild 적재 전 무결성 게이트)

**작업**: PR #131 head `94188b0` 검토 결과 직전 forward-looking 리뷰(H1~H5, M1~M7, L1~L6)는 거의 모두 반영돼 있었고, 한 가지 남은 finding을 보강했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`의 `rebuild-db` 처리 흐름에 **적재 전 무결성 게이트**(3단계)를 추가했다. 업로드(`register`)와 rebuild 사이 시간차 동안 RustFS object가 교체·손상될 수 있으므로, 다운로드한 archive의 SHA-256/size를 registry `ops.source_files.sha256`/`group_sha256`와 적재 직전 재대조하고, 불일치 시 rebuild 중단 + `quarantined`/`invalid` 전환한다. reconciliation 정기 full 재해시와 별개로 rebuild가 자체 보장한다.
- 같은 원칙을 `run-validation`에도 적용(불일치 시 검증 입력을 `skipped`가 아니라 `failed`로 기록)하도록 명시했다.
- 통합 테스트 목록에 "object 교체 후 rebuild → 무결성 게이트가 mismatch를 잡아 적재 중단" 케이스를 추가했다.

**배경**: 업로드/매칭/적재 3단계가 비연속(업로드만 하고 나중에 적재)인 운영 모델에서, 적재 직전 무결성 재대조가 없으면 시간차 동안 변조된 object가 그대로 적재될 수 있다는 리뷰 지적을 반영한 것이다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 추가 리뷰 반영 — T-109 구현 지침 보강)

**작업**: PR #131 head `3e223a4` 기준 추가 리뷰 코멘트의 H1~H5, M1~M7, L1~L8을 `docs/t109-backup-source-upload-management.md`에 반영했다.

**반영**:
- fresh `ktgctl init-db`가 Alembic head와 drift 나지 않도록 `infra/sql.py` `SCHEMA_SQL`/`INDEX_SQL`, `sql/ddl/001_schema.sql`, Alembic을 함께 갱신하라는 구현 지침과 테스트를 추가했다.
- C11+ case registry schema를 기존 `ConsistencyCaseDefinition` DTO에서 seed 가능한 컬럼으로 재정렬하고 `ops.consistency_case_inputs` link table을 추가했다.
- `user_yyyymm`은 group 단일 정본으로 두고 child/item 중복 기준월을 제거했다.
- `sido_file_set` 고정 모델을 `multi_part` + `part_kind`/`part_key`로 일반화했다.
- upload session/part 진행 상태를 `ops.source_upload_sessions`/`ops.source_upload_session_parts`로 영속화하고 orphaned multipart reconciliation을 추가했다.
- admin role gate의 신원 source를 trusted proxy header 기반 `RequestContext`로 구체화했다.
- RustFS reconciliation은 정기 `quick` scan과 손상 의심/수동 `deep` scan으로 나누고, register 단계의 중복 본문 재읽기를 줄이도록 정리했다.
- rebuild-db 흐름은 download/materialize 병렬·파이프라인과 DB COPY 직렬 유지로 구분했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (ADR-049 — T-109 구현 방향 확정)

**작업**: 사용자 결정에 따라 T-109의 미결정 선택지를 확정하고 문서에 반영했다. 호환성·최소수정보다 확장성, 완성도, 일관성, 성능을 우선하는 방향으로 고정했다.

**반영**:
- `docs/decisions.md`에 ADR-049를 추가했다.
- C11+ case metadata는 DB registry 기반 동적 catalog로 확정했다.
- match set과 운영 snapshot 연결은 `ops.dataset_snapshots.source_match_set_id` FK로 확정했다.
- source file 검증 상태는 `state`와 `validation_state` 분리로 확정했다.
- upload/register 흐름은 storage-first로 확정하되, upload session 생성 시 `user_yyyymm`은 반드시 사용자가 직접 입력·확정한 값으로 받는다. UI는 추정값 또는 현재 날짜 기준 `YYYYMM`을 입력 필드의 사전 입력값으로만 제안하고, 값이 없으면 백엔드가 세션 생성을 거부한다.
- admin role gate, full-prefix `ops` ID rename, `ops.source_file_groups`, multipart/resumable upload, RustFS full object rehash를 구현 기준으로 확정했다.
- `docs/t109-backup-source-upload-management.md`, `docs/tasks.md`, `docs/resume.md`를 ADR-049 기준으로 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (PR #131 리뷰 반영 — T-109 source group 모델 보강)

**작업**: PR #131 리뷰 코멘트의 M1~M12와 L1~L11을 `docs/t109-backup-source-upload-management.md`에 반영했다. SHP 3종(`electronic_map_full`, `roadaddr_entrance_full`, `zone_shape_full`)은 묶음 ZIP이 아니라 시도별 개별 ZIP 17개를 하나의 group으로 관리하는 모델로 확정했다.

**반영**:
- `ops.source_file_groups`를 match set 참조 단위로 추가하고, `sido_file_set` category는 group 하나 아래 child `ops.source_files` 17행을 보존하도록 정리했다.
- 전자지도 구조 검증은 11개 layer 필수, serving load는 현행 9개 layer로 분리했다.
- C11+ case CHECK 완화, RustFS client 확장, upload session 상태 매핑, SSE event schema, destructive admin action 권한/감사, 운영 용량 관리, 백업 manifest group 구조를 문서에 추가했다.
- 권고안 선택지가 있는 항목은 장단점 표로 남기고, 최종 결정이 필요한 항목을 후속 ADR 후보로 분리했다.
- `docs/tasks.md`와 `docs/resume.md`의 T-109 대기/재개 설명도 `source_file_group` 모델 기준으로 갱신했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (백업 원천 파일 업로드·매칭·검증 관리 고도화 설계)

**작업**: 백업/리스토어 고도화의 원천 파일 관리 흐름을 구현 전에 문서화했다. 사용자 요구사항에 따라 파일 업로드는 category별 명시 slot으로 나누고, 기준년월은 사용자가 직접 확정하며, 정상 업로드 파일 metadata는 DB registry에서 관리하고, RustFS object와 DB row의 정합성 검증/복구를 admin UI에서 처리하는 방향으로 설계했다.

**반영**:
- `docs/t109-backup-source-upload-management.md`를 추가했다.
- `docs/tasks.md`에 T-109 구현 대기 항목을 등록했다.
- `docs/resume.md`에 문서화 완료와 구현 대기 상태를 추가했다.
- `docs/backup-restore-source-inventory.md`에서 T-109 설계 문서를 참조하게 했다.

**핵심 결정/주의**:
- 사용자 요청의 기본 category 목록은 맞지만, `도로명주소 한글_전체분`은 내부적으로 `juso`와 `parcel_link` 두 source kind를 만들고, `도로명주소 출입구 정보`와 `구역의도형`은 현행 코드에서는 optional이므로 `serving_minimal`과 `serving_recommended` profile을 분리하도록 제안했다.
- `건물군 내 상세주소 동 도형`, `도로명주소 건물 도형`, `국가지점번호 도형/중심점`, `민원행정기관전자지도`는 match set의 optional 검증/보강 자료로 관리하고 C11+ 검증 케이스를 추가하는 방향으로 정리했다.
- incremental 업데이트 파일 업로드는 T-109 범위에서 명시적으로 제외했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (미사용 원천 데이터 정확도 개선 검토)

**작업**: `F:\dev\kor-travel-geo\data\juso` 현재 배치에서 기본 full-load가 쓰지 않거나 선택/조건부로만 쓰는 원천을 대상으로, 직접 정확도 개선 가능성·검증용 가치·도입 위험을 문서화했다.

**반영**:
- `docs/source-data-accuracy-review.md`를 추가했다.
- 국가지점번호 도형/중심점은 현 10m 국가지점번호 parser보다 더 정밀한 좌표 원천은 아니지만, 100m 이하 prefix 검증·formatter regression·grid overlay에는 가치가 있음을 정리했다.
- `도로명주소 건물 도형`은 출입구 point/연결선 검증과 후보 scoring 개선에는 가치가 있지만 `TL_SPBD_BULD` 대체재가 아니므로 별도 analysis table부터 시작해야 한다고 정리했다.
- `건물군 내 상세주소 동 도형`과 `상세주소DB`는 일반 주소 geocode가 아니라 상세주소 기능/검증 후보로 분리했다.
- `주소DB`, `건물DB`, `민원행정기관전자지도`, 과거 snapshot, 전자지도 내부 미사용 layer, 내비 `match_jibun_*`의 활용 가능성과 검증용 가치를 함께 정리했다.

**검증**:
- PowerShell/Python ZIP·DBF header 스캔과 WSL `7z` 조회로 파일 구조, record count, 중심점 분포를 확인했다.

## 2026-06-14 (원본 디렉터리 사용/미사용 구분)

**작업**: `F:\dev\kor-travel-geo\data\juso` 현재 배치 기준으로 full-load 사용, 선택/조건부 사용, 기본 서빙 load 미사용 파일을 구분해 백업/리스토어 원천 인벤토리에 추가했다.

**반영**:
- `202605_도로명주소 한글_전체분.zip`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분.7z`, `도로명주소 전자지도\202604\<시도>.zip`을 기본 full-load 사용 원천으로 정리했다.
- `도로명주소 출입구 정보\202604\<시도>.zip`과 `구역의도형\202603\<시도>.zip`을 선택/조건부 사용 원천으로 분리했다.
- 상세주소DB, 주소DB, 건물DB, 도로명주소 건물 도형, 건물군 내 상세주소 동 도형, 국가지점번호 grid/중심점, 민원행정기관전자지도는 현행 기본 서빙 load에서 쓰지 않는 원천으로 명시했다.

**검증**:
- 문서-only 변경. `git diff --check`로 공백 오류를 확인한다.

## 2026-06-14 (로컬 원본 파일 재스캔과 전자지도 ZIP 확인)

**작업**: `F:\dev\kor-travel-geo\data\juso`에 추가 정리된 원본 파일을 다시 스캔해, full-load 필수 원천과 선택 원천의 압축파일 기준 위치와 기준년월 추출 가능성을 갱신했다.

**반영**:
- `도로명주소 전자지도\202604\<시도>.zip` 17개 안에 serving 대상 9개 SHP layer의 `.shp/.shx/.dbf` sidecar가 모두 있음을 확인하고 문서화했다.
- `TL_SPRD_MANAGE`, `TL_SPRD_INTRVL`, `TL_SPRD_RW`, `TL_SPBD_BULD`의 원본이 `도로명주소 전자지도\202604\<시도>.zip`임을 명시했다.
- `도로명주소 출입구 정보\202604`의 내부 파일은 `RNENTDATA_2605_*`라서 내부 파일명 기준월은 `202605`임을 주의사항으로 남겼다.

**검증**:
- PowerShell/.NET ZIP 리더와 WSL `7z` 목록 조회로 압축파일 내부 member 수를 확인했다.

## 2026-06-14 (백업/리스토어 원천 데이터 인벤토리 문서화)

**작업**: 백업/리스토어 로직 고도화를 위해 현재 로더가 사용하는 파일 원천, 외부 API 소스, 파생 MV/accelerator, manifest 권장 필드를 별도 문서로 정리했다.

**반영**:
- `docs/backup-restore-source-inventory.md`를 추가했다.
- full-load 필수 source kind(`juso`, `parcel_link`, `locsum`, `navi`, `shp`)와 선택 source kind(`roadaddr_entrance`, `sppn_makarea`, `pobox`, `bulk`)의 파일 패턴과 적재 테이블을 정리했다.
- VWorld/Juso는 조회 폴백, epost는 오프라인 ZIP 원천 생성 API, RustFS는 source provider가 아니라 upload set 저장소라는 경계를 명시했다.

**검증**:
- 문서-only 변경. 별도 테스트는 실행하지 않았다.

## 2026-06-13 (로컬·Docker API/UI 포트 1250x 통일)

**작업**: 사용자 지시에 따라 로컬 단독 실행 포트를 Docker 실행·`kor-travel-docker-manager` scrape target과 같은 `12501`/`12505`로 맞췄다.

**반영**:
- FastAPI 기본 실행 포트와 API Dockerfile `PORT`/`EXPOSE`를 `12501`로 변경했다.
- `kor-travel-geo-ui` 기본 실행 포트, UI Dockerfile `PORT`/`EXPOSE`, Playwright 기본 `baseURL`, UI proxy 기본 `KTG_API_INTERNAL_URL`을 `12505`/`12501` 기준으로 변경했다.
- `scripts/docker_app.sh`, `scripts/deploy_app.py`, `scripts/benchmark_api_latency.py`의 기본 포트를 `12501`/`12505`로 변경했다.
- `docs/ports.md`, `docs/dev-environment.md`, README, UI README, API reference, `docs/resume.md`를 현재 실행 기준으로 갱신하고 ADR-048을 추가했다. ADR-046은 superseded로 남겼다.
- 주변 서비스 포트도 `kor-travel-docker-manager`의 `docs/ports.md`, `AGENTS.md`, `docker-compose.yml`을 기준으로 맞췄다. PostgreSQL `5432`, RustFS API/console `12101`/`12105`, Grafana/cAdvisor/Prometheus `12205`/`12301`/`12401`, concierge `12601`/`12602`/`12605`, map `12701`/`12702`/`12705`, Pinvi `12801`/`12805`, manager `12901`/`12905`를 `docs/ports.md`에 정리했다.
- RustFS 관련 테스트 fixture의 예시 endpoint도 이전 `9003`에서 manager 기준 `12101`로 변경했다.

**검증**:
- Windows/NTFS: `python -m pytest tests/unit/test_deploy_app.py tests/unit/test_rustfs_uploads.py -q` → `orjson` 미설치로 `test_rustfs_uploads.py` 수집 실패. WSL ext4 미러 가상환경 검증을 기준으로 삼았다.
- Windows/NTFS: `python -m ruff check scripts/deploy_app.py scripts/benchmark_api_latency.py tests/unit/test_deploy_app.py` → pass
- Windows/NTFS: `git diff --check` → pass
- WSL ext4 mirror: `.venv/bin/python -m pytest -q` → 298 passed, 25 skipped
- WSL ext4 mirror: `.venv/bin/python -m ruff check .` → pass
- WSL ext4 mirror: `.venv/bin/python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `.venv/bin/lint-imports` → Layered architecture kept
- WSL ext4 mirror: `.venv/bin/python -m pytest tests/unit/test_deploy_app.py tests/unit/test_rustfs_uploads.py -q` → 13 passed
- WSL ext4 mirror: `.venv/bin/python -m ruff check scripts/deploy_app.py scripts/benchmark_api_latency.py tests/unit/test_deploy_app.py` → pass
- WSL ext4 mirror `kor-travel-geo-ui`: `npm run lint`, `npm run test`, `npm run build` → pass
- WSL ext4 mirror `kor-travel-geo-ui`: `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0
- 실제 서버: API `http://127.0.0.1:12501/v1/healthz` → `{"status":"ok"}`
- 실제 서버: UI `http://127.0.0.1:12505/debug/geocode` → HTTP 200
- 실제 서버: UI proxy `http://127.0.0.1:12505/api/proxy/v1/healthz` → `{"status":"ok"}`
- CodeGraph: `codegraph sync`, `codegraph status` → `disk I/O error`로 실패

## 2026-06-13 (T-108 운영 배포 자동화)

**작업**: 사용자 지시에 따라 `pinvi`의 T-108을 이 저장소 작업 항목으로 가져오고, API/UI 운영 배포 자동화 표면을 구현했다.

**반영**:
- `docs/tasks.md` 완료 섹션에 T-108을 등록하고, `docs/t108-deploy-automation.md`에 `pinvi` 원문을 보존했다.
- `scripts/deploy_app.py`를 추가했다. `plan`은 build/deploy 계획 JSON·Markdown을 만들고, `build`는 API/UI `docker buildx build` 멀티플랫폼 명령을 실행하며, `deploy`는 N150/Odroid 같은 원격 노드에 SSH로 API/UI 컨테이너를 배포한다.
- 원격 배포는 노드의 `--env-file`을 사용해 `KTG_PG_DSN`, `KTG_RUSTFS_*`, `KTG_VWORLD_API_KEY`를 주입하며 secret 값을 명령행에 펼치지 않는다.
- PostgreSQL/RustFS 생명주기는 이 저장소에서 관리하지 않으며, 사용자 추가 지시에 따라 streaming replication은 이번 범위에서 제외했다.
- `docs/t108-deploy-automation.md`, `docs/resume.md`, `CHANGELOG.md`를 갱신했다.

**검증**:
- Windows/NTFS: `python -m pytest tests/unit/test_deploy_app.py -q` → 6 passed
- Windows/NTFS: `python -m ruff check scripts/deploy_app.py tests/unit/test_deploy_app.py` → pass
- Windows/NTFS: `python scripts/deploy_app.py plan --tag test --output-dir .tmp\t108-plan` → plan 생성 확인
- Windows/NTFS: `git diff --check` → pass
- WSL ext4 mirror: `python -m pytest -q` → 298 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept
- WSL ext4 mirror: `python scripts/deploy_app.py plan --tag test --output-dir /tmp/ktg-t108-plan` → JSON/Markdown 생성 확인

## 2026-06-13 (Prometheus 상세 계측 범위 확장)

**작업**: 사용자 요청에 맞춰 API, Next.js admin UI, provider/load batch job 단계, DB query별 성능 측정을 추가했다.

**반영**:
- SQLAlchemy event hook 기반 DB query counter/duration histogram을 추가하고, query 원문 대신 operation과 fingerprint를 label로 사용한다.
- load job 전체 duration과 stage별 duration histogram을 추가했다.
- `kor-travel-geo-ui`에 `/api/metrics` Prometheus endpoint, `/api/metrics/web-vitals` 수집 endpoint, Web Vitals reporter, Next.js route handler/proxy upstream duration 계측을 추가했다.
- `kor-travel-docker-manager` Prometheus scrape target을 `kor-travel-geo-api:12501/metrics`, `kor-travel-geo-ui:12505/api/metrics` 기준으로 맞췄다.

**검증**:
- WSL ext4 mirror: `.venv/bin/python -m pytest -q` → 292 passed, 25 skipped
- WSL ext4 mirror: `.venv/bin/python -m ruff check .` → pass
- WSL ext4 mirror: `.venv/bin/python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `.venv/bin/lint-imports` → Layered architecture kept
- WSL ext4 mirror `kor-travel-geo-ui`: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` 통과
- WSL ext4 mirror `kor-travel-geo-ui`: `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0

## 2026-06-13 (Prometheus 성능 모니터링 보강)

**작업**: `kor-travel-docker-manager`의 관측 스택 포트 정책을 확인해 `kor-travel-geo` API `/metrics`의 성능 메트릭을 보강했다. Prometheus는 앱이 능동 연결하지 않고 외부 scraper가 `/metrics`를 가져가는 pull 구조로 유지한다. Docker manager 기준 Prometheus/Grafana/cAdvisor host 포트는 `12401`/`12205`/`12301`이고, compose 내부 API scrape target은 `kor-travel-geo-api:12501/metrics`다.

**반영**:
- `kor_travel_geo_api_requests_total`, `kor_travel_geo_api_slow_requests_total`, `kor_travel_geo_api_requests_in_progress`를 추가했다.
- SQLAlchemy pool 상태 gauge `kor_travel_geo_pg_pool_size`, `kor_travel_geo_pg_pool_checked_in`, `kor_travel_geo_pg_pool_checked_out`, `kor_travel_geo_pg_pool_overflow`를 추가했다.
- `/metrics` 요청 시 cache/load job gauge와 함께 DB pool gauge를 갱신한다.
- `README.md`, `.env.example`, `docs/architecture.md`, `docs/ports.md`, `CHANGELOG.md`에 Prometheus/Grafana 포트와 pull 방식 scrape target을 문서화했다.

**검증**:
- WSL ext4 mirror: `python -m pytest -q` → 290 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept

## 2026-06-13 06:20 (T-077 `kor-travel-geo` 식별자 전환 구현)

**작업**: 사용자 확정값에 맞춰 프로젝트 식별자를 `kor-travel-geo` 계열로 통일했다. Python import root는 `kortravelgeo`, 권장 alias는 `import kortravelgeo as ktg`, CLI는 `ktgctl`, 환경변수 prefix는 `KTG_*`, PostgreSQL 기본 DB명은 `kor_travel_geo`, RustFS bucket/prefix 기본값은 `kor-travel-geo`다.

**반영**:
- backend package를 `src/kortravelgeo/`로 옮기고 전체 import, import-linter, mypy, Alembic, OpenAPI export, Docker/uvicorn entrypoint를 갱신했다.
- `pyproject.toml` 배포명은 `kor-travel-geo`, console script는 `ktgctl`로 고정했다.
- `kortravelgeo.__init__`에서 `AsyncAddressClient`, 주요 v2 DTO, `Point`, `ZipSource`, `RegionHint`를 공개해 `import kortravelgeo as ktg` 사용을 고정했다.
- 환경변수는 `KTG_*`로 통일하고 `.env.example`, Settings, Docker 실행 스크립트, UI proxy/runtime config, 문서 예시를 갱신했다.
- PostgreSQL 서비스 DB를 `kor_travel_geo`로 rename하고, Docker API/UI를 새 기본 DB명과 RustFS `kor-travel-geo` 기본값으로 재기동했다.
- API request duration Prometheus histogram과 `KTG_API_PERFORMANCE_LOGGING_ENABLED` opt-in 성능 로그를 추가했다. 로그는 route template/method/status/elapsed_ms만 기록하고 query string과 주소 입력값은 남기지 않는다.
- `kor-travel-geo-ui` package로 UI 경로를 옮기고 누락된 `scripts/`, `tests/`, `types/` 파일을 복구했다. React Doctor 지적에 따라 Query 결과 객체 전체 구독을 제거하고 `vitest`를 `4.1.8` 계열로 갱신했다.
- `docs/t077-kor-travel-geo-rename.md`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`, ADR-047을 갱신했다.

**검증**:
- 이전 이름 계열 내용 검색 2회 → 0건
- 이전 이름 계열 파일/디렉터리명 검색 2회 → 0건
- 잘못된 CLI 실행 예시 검색 2회 → 0건
- WSL ext4 mirror: `python -m pytest -q` → 289 passed, 25 skipped
- WSL ext4 mirror: `python -m ruff check .` → pass
- WSL ext4 mirror: `python -m mypy src/kortravelgeo` → pass
- WSL ext4 mirror: `lint-imports` → Layered architecture kept
- WSL ext4 mirror UI: `npm run gen:types`, `lint`, `type-check`, `test`, `build` → pass
- WSL ext4 mirror UI: `npx react-doctor@latest . --offline --verbose --json` → score 100, diagnostics 0
- Docker: `scripts/docker_app.sh build && scripts/docker_app.sh up` → API `12201`, UI `12205`
- Smoke: `GET /v1/healthz` → `ok`; `/v2/geocode` 인사동 → `OK` 후보 10건; `/v2/reverse` 인사동 좌표 → `OK` 후보 10건; UI runtime VWorld key non-empty; API/UI restart policy `unless-stopped`

## 2026-06-12 09:55 (T-077 배포명·임포트명 전환 Task 문서화)

**작업**: 사용자 지시에 따라 Python 배포명 `kor-travel-geo`, import root `kortravelgeo`, 권장 alias `import kortravelgeo as ktg` 전환을 후속 Task로 정리했다.

**반영**:
- `docs/tasks.md`의 대기 항목에 T-077을 추가했다.
- `docs/t077-kor-travel-geo-rename.md`를 추가해 목표 식별자, 범위, 범위 밖, 호환성 원칙, 구현 체크리스트, 검증 기준, 남은 결정을 정리했다.
- 현재 코드와 실행 문서는 아직 `kor-travel-geo`/`kortravelgeo` 기준으로 유지한다. 실제 rename은 후속 구현 PR에서 원자적으로 처리한다.

**검증**:
- 문서-only 변경으로 `git diff --check`를 실행한다.

## 2026-06-12 09:20 (로컬 고정 포트 재정의와 Docker 재기동)

**작업**: 사용자 지시에 따라 PostgreSQL `5432`, RustFS API `12101`, 이 저장소 API `12201`, Web UI `12205`를 현재 고정 포트로 정리했다.

**반영**:
- `scripts/docker_app.sh`의 API/UI host/container 기본 포트를 `12201`/`12205`로 변경했다.
- API/UI Dockerfile의 내부 `PORT`/`EXPOSE`를 각각 `12201`/`12205`로 변경했다.
- `.env.example`, UI proxy 기본값, Playwright 기본 base URL, API reference, README, 현재 운영 문서를 새 포트 기준으로 갱신했다.
- `/admin/settings` RustFS endpoint placeholder를 `http://127.0.0.1:12101`로 변경했다.
- ADR-046을 추가하고 ADR-042의 `9001`/`9002` 결정은 superseded 처리했다.

**검증**:
- `bash -n scripts/docker_app.sh && bash -n scripts/fullload_test.sh`
- `scripts/docker_app.sh build` — API image build와 UI `next build`/TypeScript 통과
- `scripts/docker_app.sh up` — API `12201`, UI `12205`로 재생성
- Docker port/status: PostgreSQL `5432` healthy, RustFS API `12101` healthy, API `12201`, UI `12205`, API/UI restart policy `unless-stopped`
- `GET http://<legacy-api-host>:12201/v1/healthz` → `ok`
- `POST http://<legacy-api-host>:12201/v2/geocode` `"서울특별시 종로구 인사동"` → `OK`, 후보 10건
- `POST http://<legacy-api-host>:12201/v2/reverse` 인사동 좌표(`126.986`, `37.574`, 반경 200m) → `OK`, 후보 10건
- `GET http://<legacy-ui-host>:12205/debug/geocode` → HTTP 200
- `GET http://<legacy-ui-host>:12205/api/runtime-config` → VWorld key non-empty
- `npm run test -- tests/unit/runtime-config.test.ts` → 5 passed
- API image 안에서 `python -m pytest tests/unit/test_settings.py -q` → 5 passed
- API image 안에서 `python -m ruff check alembic/versions/0013_t061_text_search_mv.py scripts/benchmark_api_latency.py src/kortravelgeo/settings.py` → pass

## 2026-06-12 07:45 (WSL 재설치 후 주소 DB 복원과 API/UI 재시작 정책)

**작업**: WSL 재설치 뒤 빈 `kor_travel_geo` DB로 API만 기동되어 다른 에이전트의 reverse/geocode 보강이 모두 결측 처리될 위험을 해소했다.

**반영**:
- `/mnt/f/dev/kor-travel-geo/artifacts/perf/t047-operational-impact-20260528/pgdump-dir.tar.zst` 백업을 임시 DB `kor_travel_geo_restore_t047_20260612`에 복원했다.
- 복원 DB를 Alembic head(`0015_t075_region_radius_parts`)까지 올린 뒤 smoke test를 통과시켜 현재 `kor_travel_geo`로 승격했다. 기존 빈 DB는 `kor_travel_geo_empty_20260612_073529` 이름으로 보존했다.
- `scripts/docker_app.sh`의 API/UI 컨테이너에 기본 Docker restart policy `unless-stopped`를 적용했다. 필요하면 `KTG_DOCKER_RESTART_POLICY=no`로 끌 수 있다.
- `alembic/versions/0013_t061_text_search_mv.py`가 최신 `TEXT_SEARCH_MV_SQL` 상수를 참조해 과거 revision 복원 DB에서 깨지던 문제를 고쳤다. `0013`은 T-061 당시의 MV 정의를 자체 보관하고, `0014`가 T-065 컬럼 추가 후 최신 MV를 재생성한다.

**검증**:
- `bash -n scripts/docker_app.sh`
- `scripts/docker_app.sh build-api`
- 복원 DB에서 `alembic upgrade head` 통과
- DB row count: `tl_juso_text=6,416,637`, `mv_geocode_target=6,416,637`, `mv_geocode_text_search=6,416,637`, `region_radius_parts=54,316`
- API 컨테이너 `restart=unless-stopped`, UI 컨테이너 `restart=unless-stopped`
- `GET /v1/healthz` → `{"status":"ok"}`
- `POST /v2/reverse` 인사동 좌표(`126.986,37.574`, 반경 200m) → `OK`, 후보 반환
- `POST /v2/geocode` `"서울특별시 종로구 인사동"` → `OK`, 후보 반환

**참고**:
- 이번 복원은 최신 full-load가 아니라 T-047 시점 백업을 최신 schema로 올린 운영 복구다. T-073 이후 최신 daily/국가지점번호 재측정 DB가 필요하면 별도 최신 백업 또는 full-load를 다시 적용한다.

## 2026-06-10 21:45 (PostgreSQL/RustFS 구동 책임 제거)

**작업**: 사용자 지시에 따라 이 저장소에서 PostgreSQL/PostGIS와 RustFS의 직접 구동·정지·재시작 책임을 제거했다. 이제 이 프로젝트는 이미 동작 중인 DB와 bucket에 접속해 사용하며, 필요한 접속 정보는 `.env`, 환경변수, 또는 admin UI 설정 파일에 저장한다.

**반영**:
- `docker-compose.yml`을 삭제했다.
- `scripts/docker_app.sh`에서 RustFS 구동/정지/로그 명령을 제거하고, API/UI 컨테이너에 `KTG_PG_DSN`, `KTG_RUSTFS_*` 접속 설정을 주입하는 역할만 남겼다.
- README, AGENTS, SKILL, 개발 환경/포트/복구/작업 재개 문서를 "이미 동작 중인 DB와 bucket 접속 설정" 기준으로 갱신했다.
- ADR-045를 추가하고 ADR-044의 RustFS 구동 책임 내용을 superseded 처리했다.

**검증**:
- `bash -n scripts/docker_app.sh`
- `scripts/docker_app.sh help`

## 2026-06-03 09:16 (RustFS 업로드 저장소와 접속 설정 표준)

**작업**: 업로드 파일을 로컬 디렉터리 대신 RustFS(S3 호환)에 저장할 수 있는 옵션을 추가했다. 당시 포함됐던 RustFS 직접 구동 책임은 2026-06-10 ADR-045로 폐기됐고, 현재 기준은 이미 동작 중인 bucket 접속 설정만 저장하는 것이다.

**반영**:
- `rustfs://<bucket>/<prefix>/...` URI와 `storage_kind="local" | "rustfs"`를 upload set manifest/DTO/API에 추가했다.
- `/v1/admin/storage/rustfs/config`, `/check`, `/import-prefix`, `/sync-local` API를 추가했다. secret은 설정 조회 응답에 원문으로 노출하지 않는다.
- `/admin/settings`에서 RustFS 사용 여부, endpoint, bucket, prefix, region, access/secret key, retention을 설정하고 연결 확인을 실행할 수 있게 했다.
- `/admin/load`에서 업로드 저장소를 선택하고, RustFS prefix import와 기존 로컬 파일 RustFS sync를 실행할 수 있게 했다.
- `kor-travel-geo`/`python-krtour-map`/`tripmate` prefix 분리, 무기한 보존 기본값, Chrome/Firefox Playwright e2e 원칙을 문서화했다.

**검증**:
- ext4 테스트 미러에서 backend `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`를 통과했다. pytest는 `303 passed, 7 skipped`다.
- ext4 테스트 미러에서 frontend `scripts/frontend_check.sh --install`을 통과했다. `gen:types`, lint, type-check, Vitest 42개, build가 모두 성공했다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- `scripts/docker_app.sh build`로 API/UI image를 다시 빌드했고, API build에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- 실제 API + RustFS 접속 테스트에서 `/data/juso/도로명주소 전자지도/서울특별시/11000/TL_SCCO_LI.shp`와 `/data/juso/202604_사서함주소DB_전체분.zip`을 RustFS로 sync하고 prefix import를 확인했다. 직접 `PUT /v1/admin/uploads/{id}/files` RustFS 업로드도 `state=uploaded`로 확인했다.
- Windows Playwright Docker UI `http://<legacy-ui-host>:9002`: Chromium 전체 e2e 16 passed, Firefox 전체 e2e 16 passed. 메뉴 반복 이동 테스트는 `This page couldn`, `Reload to try again`, `_rsc` client routing 요청 부재를 확인하고, VWorld 지도 테스트는 실제 WMTS 타일과 MapLibre canvas를 확인한다.

**발견**:
- RustFS는 여러 프로젝트가 공유할 수 있으므로 이 저장소는 구동 책임을 갖지 않고 bucket/prefix 접속 설정만 유지하는 편이 안전하다.

## 2026-06-03 09:15 (antigravity-readme-cleanup)

**작업**: README.md의 가독성과 레이아웃을 GFM 스타일에 맞추어 정돈하였고, docs/agent-guide.md에 포함된 절대경로에서 특정 로컬 사용자명(digit)을 제거하여 개인정보를 마스킹했습니다. 또한 tripmate 등의 특정 프로젝트명 언급 여부를 조사하여 해당 명칭이 저장소에 없음을 확인했습니다.

**반영**:
- `README.md`의 현재 상태(Status Note) 문단을 GFM 리스트 형태로 개조하여 가독성을 향상시켰습니다.
- `README.md` 개발 환경 경로 안내 예시의 텍스트 줄바꿈 정렬 어긋남을 수정했습니다.
- `docs/agent-guide.md`에서 로컬 윈도우 사용자가 노출되던 절대경로 `Users/digit`을 `Users/<user>`로 일반화하여 마스킹했습니다.
- 저장소 전체에서 `tripmate`를 대소문자 구분 없이 검색하였으며, 사용 흔적이 전혀 발견되지 않음을 검증 및 보고합니다.

**검증**:
- 변경사항에 대해 `git diff`를 실행하여 텍스트 포맷과 경로 수정 결과가 안전함을 확인했습니다.
- 변경된 파일은 마크다운(.md) 문서 파일들로, 백엔드 및 프론트엔드의 실행 로직에는 영향을 주지 않습니다.

## 2026-06-03 01:30 (admin UI 메뉴 이동 Next 전역 오류 화면 보정)

**작업**: 좌측 메뉴를 클릭하다가 Chrome/Firefox 모두에서 Next 기본 전역 오류 화면(`This page couldn’t load`, `Reload to try again, or go back.`)으로 떨어지는 현상을 재현·보정했다.

**반영**:
- 좌측 메뉴와 Consistency report 목록의 internal link를 `DocumentNavLink`로 교체했다. `next/link`는 유지하되 `prefetch={false}`와 명시적 document navigation을 사용해 Next App Router client transition/RSC fetch 실패 화면으로 새지 않게 했다.
- 긴 좌측 메뉴가 데스크톱에서 viewport 아래로 밀리는 문제를 막기 위해 sidebar에 `100dvh` 높이와 내부 스크롤을 적용했다.
- VWorld 타일 요청이 페이지 이동 중 브라우저에 의해 취소될 때(`ERR_ABORTED`, `NS_BINDING_ABORTED`) 지도 불안정 overlay 카운트와 warning 로그에 반영하지 않도록 했다.
- 좌측 메뉴 반복 이동 e2e를 추가했다. 이 테스트는 메뉴 15개를 4회 순회하며 Next 전역 오류 문구, page error, 비정상 request failure, `_rsc` client routing 요청 부재를 확인한다.

**검증**:
- `scripts/docker_app.sh build-ui && scripts/docker_app.sh up-ui`로 UI image를 다시 빌드하고 `http://<legacy-ui-host>:9002` 컨테이너를 교체했다.
- Windows Playwright Chromium/Firefox: `tests/e2e/navigation.spec.ts` → 각 1 passed.
- Windows Playwright Chromium/Firefox: `tests/e2e/vworld-map.spec.ts` → 각 2 passed.
- ext4 테스트 미러 Linux Node에서 `npm run lint`, `npm run type-check`, `npm run test`를 통과했다. unit test는 11 files / 42 tests 통과다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.

**발견**:
- 해당 문구는 앱 코드가 아니라 Next 16 기본 `global-error` 화면에서 나온다. 메뉴 전환 중 발생하는 client routing/RSC fetch 실패 화면을 피하려면 내부 운영 UI에서는 안정적인 document navigation이 더 적합하다.

## 2026-06-02 23:58 (`/v2/regions/within-radius` DB 튜닝)

**작업**: 행정구역 반경조회가 큰 polygon을 레벨별로 직접 훑으며 tail latency가 커지는 문제를 줄이기 위해 `region_radius_parts` serving accelerator를 추가했다.

**반영**:
- `region_radius_parts` 테이블과 Alembic `0015_t075_region_radius_parts` migration을 추가했다. `tl_scco_ctprvn/sig/emd`를 `ST_Subdivide(geom, 256)`으로 쪼개고 `level`, `code`, parent code, `part_no`, `geom`을 보관한다.
- `GeometryRepository.regions_within_radius()`는 레벨별 3회 query loop 대신 단일 SQL을 실행한다. 입력점은 한 번만 EPSG:5179로 변환하고, 후보 검색은 `region_radius_parts.geom` GiST index + `ST_DWithin`을 사용한다.
- `contains` 관계는 accelerator 조각이 아니라 원본 `tl_scco_ctprvn/sig/emd`의 `ST_Covers`로 코드 기준 계산한다.
- 시군구 후보는 반경 안의 시도 parent code로, 읍면동 후보는 반경 안의 시군구 parent code로 좁힌다.
- `load shp`, `load shp-all`, `load all-sidos`, `refresh mv` 경로가 accelerator를 다시 채우도록 했다.
- ADR-043, `docs/data-model.md`, v2 API reference, CHANGELOG, resume, task tracker를 갱신했다.

**검증**:
- ext4 테스트 미러에서 `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`를 통과했다. pytest는 `297 passed, 7 skipped`다.
- Docker API image build에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- 실제 T-027 최종 DB는 Alembic table이 없던 운영 적재 DB라 `alembic stamp 0014_t065_navi_name_search` 후 `alembic upgrade head`로 `0015`만 적용했다.
- 실제 DB accelerator row count는 `sido=10,607`, `sigungu=14,686`, `emd=29,023`이고 GiST/parent index 3개와 PK를 확인했다.
- `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo pytest tests/integration/test_optional_real_postgres_regions.py -q` → `1 passed`. 이 테스트는 accelerator 결과와 원본 `tl_scco_*` 직접 `ST_DWithin` 결과를 비교한다.
- `scripts/docker_app.sh up`으로 API `9001`, UI `9002`를 새 이미지로 다시 올렸다. `/v1/healthz`, `/debug/geocode`, `/api/runtime-config`가 200을 반환했고 VWorld 키는 길이만 확인했다.
- REST benchmark 40회 반복:
  - `seoul_3km`: p50 `13.10ms → 13.68ms`, p95 `22.00ms → 20.89ms`, count 동일(`sido=1`, `sigungu=6`, `emd=190`).
  - `seoul_20km`: p50 `39.09ms → 22.80ms`, p95 `122.05ms → 28.61ms`, count 동일(`sido=3`, `sigungu=49`, `emd=645`).
  - `busan_10km`: p50 `38.75ms → 12.28ms`, p95 `45.80ms → 14.89ms`, count 동일(`sido=2`, `sigungu=17`, `emd=138`).

**발견**:
- 기존 T-027 최종 DB는 schema objects는 최신이지만 `alembic_version` table이 없었다. 운영 적재 DB에 migration을 적용할 때는 기존 schema level을 확인한 뒤 stamp 후 upgrade해야 한다.

## 2026-06-02 21:49 (Docker 실행 스크립트, 9001/9002 포트 원칙, Firefox VWorld 지도 보정)

**작업**: API/UI Docker 이미지를 GDAL 버전 매칭 상태로 빌드·실행하는 표준 스크립트를 추가하고, 로컬 API/UI 포트 원칙을 `9001`/`9002`로 갱신했다. Firefox에서 VWorld 지도가 보이지 않는 원인을 확인해 `vworld://` custom protocol fallback을 쓰지 않도록 보정했다.

**반영**:
- `docker/api.Dockerfile`과 `kor-travel-geo-ui/Dockerfile`을 추가·갱신해 API는 `9001`, UI는 `9002`로 실행한다. API image build 중 `gdal-config --version`과 Python `gdal` wheel 버전을 맞추고 불일치 시 실패한다.
- `scripts/docker_app.sh`를 추가해 `build-api`/`build-ui`/`build`/`up-api`/`up-ui`/`up`/`down`/`status`/`logs`/`cli`/`load`/`load-full-set`을 제공한다. 기본 실행은 Docker bridge network이며, `.env`/`kor-travel-geo-ui/.env.local`의 VWorld 키를 컨테이너 환경변수로 주입하되 키 값은 출력하지 않는다.
- `scripts/docker_app.sh up` 계열은 API `9001`, UI `9002` host 포트를 점유한 기존 Docker 컨테이너와 listen 프로세스를 종료한 뒤 새 컨테이너를 올린다.
- Firefox에서 `maplibre-vworld`의 `unsupportedTileFallback`이 타일 URL을 `vworld://...`로 바꾸면 CORS `not http`로 차단되는 것을 확인했다. `CoordinateMap`은 해당 fallback prop을 전달하지 않고 HTTPS WMTS를 직접 사용한다.
- `vworld-map.spec.ts`는 Firefox에서 `/debug/geocode` 반복 진입, runtime VWorld 키, 실제 WMTS tile fetch, MapLibre canvas, 지도 스크린샷 색상 다양성, `vworld://`/CORS 콘솔 오류 부재를 검증한다.
- README, `kor-travel-geo-ui/README.md`, `docs/ports.md`, `docs/dev-environment.md`, `docs/agent-workflow.md`, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/decisions.md`, `docs/resume.md`, API reference 예시를 새 포트 원칙으로 갱신했다.

**검증**:
- ext4 테스트 미러에서 `bash -n scripts/docker_app.sh`, `scripts/docker_app.sh --help`, `kor-travel-geo-ui` `npm run type-check`, `npm run lint`, `npm run test`, `npm run build`를 통과했다. unit test는 11 files / 42 tests 통과다.
- React Doctor `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- `scripts/docker_app.sh build`로 API/UI 이미지를 빌드했고, API build/runtime에서 `libgdal=3.10.3`, `python_gdal=GDAL 3.10.3, released 2025/04/01`를 확인했다.
- `scripts/docker_app.sh up`으로 API `http://<legacy-api-host>:9001`, UI `http://<legacy-ui-host>:9002`를 올렸다. `/v1/healthz`, `/debug/geocode`, `/api/runtime-config`가 200을 반환했고 VWorld 키는 길이만 확인했다.
- `/debug/geocode` 20회 반복 HTTP load에서 `This page couldn`와 `지도 타일 로딩이 불안정합니다` 문자열이 나오지 않았다.
- UI proxy `POST /api/proxy/v2/geocode` 실제 DB smoke가 `status=OK`, 후보 1건을 반환했다.
- Windows Firefox Playwright: `PLAYWRIGHT_BASE_URL=http://<legacy-ui-host>:9002`, `PLAYWRIGHT_BROWSER=firefox`, `tests/e2e/vworld-map.spec.ts` → 2 passed.
- Python `ruff`는 ext4 미러에 Python dev venv가 없어 실행하지 못했다. 이번 Python 변경(`scripts/benchmark_api_latency.py`)은 기본 URL 문자열 변경이며 `python3 -m compileall -q scripts/benchmark_api_latency.py`는 통과했다.

## 2026-06-02 23:20 (PR #114~#115 리뷰 감사와 실제 DB 테스트 보강)

**작업**: PR #114부터 최신 PR #115까지 conversation comment, review body, inline review thread를 모두 확인하고, 사용자 지시에 맞춰 PR #114 기능의 실제 PostgreSQL 회귀 테스트를 추가했다.

**반영**:
- `docs/postmerge-review-fixups-pr114-pr115.md`에 PR별 리뷰 표면 확인 결과를 기록했다. 두 PR 모두 conversation comment 0건, review body 0건, review thread 0건이었다.
- `tests/integration/test_optional_real_postgres_regions.py`를 추가했다. `KTG_TEST_PG_DSN`이 설정된 실제 DB에서 `tl_scco_emd`의 `ST_PointOnSurface` 좌표를 사용해 `AsyncAddressClient.regions_within_radius()`가 `sido`/`sigungu`/`emd` contains 후보를 반환하는지 검증한다.
- `docs/resume.md`, `docs/tasks.md`에 이번 감사와 테스트 보강 상태를 반영했다.

**검증**:
- ext4 테스트 미러에서 `python -m pytest tests/integration/test_optional_real_postgres_regions.py -q` → `1 skipped`.
- `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo`로 T-027 최종 DB 대상 새 테스트 실행 → `1 passed`.
- `python -m ruff check .`, `python -m mypy src/kortravelgeo`, `lint-imports`, `python -m pytest -q` → 통과(`294 passed, 9 skipped`).

**발견**:
- PR #114와 PR #115는 GitHub의 세 리뷰 표면 모두에 남은 코멘트가 없었다.

## 2026-06-02 22:05 (세션 실행 실수 복기와 재발 방지 런북 보강)

**작업**: 이번 세션에서 반복된 CLI 접근, npm 서버 파라미터, WSL/Windows 실행 분리, 환경 설정, 서버 정리 실수를 복기해 문서화했다. 같은 명령을 여러 번 반복하지 않도록 실패 유형별 전환 규칙을 추가했다.

**반영**:
- `docs/agent-failure-patterns.md`에 `gh --repo` 사용, WSL Linux Node 초기화, npm script 인자 `--` 전달, Windows Playwright env var 전달, CodeGraph sync/status 순서, generated `next-env.d.ts` 복구, long-running server PID 종료, 반복 시도 제한 규칙을 추가했다.
- `docs/agent-workflow.md`에 WSL production UI 서버 실행, Windows Playwright 접속, VWorld runtime config 확인, 서버 종료, GitHub CLI, CodeGraph 표준 명령을 붙여넣기 가능한 형태로 추가했다.
- `docs/dev-environment.md`, `docs/resume.md`, `CHANGELOG.md`에 같은 운영 기준을 요약 반영했다.

**검증**:
- 문서-only 변경이다. `git.exe diff --check`로 whitespace를 확인한다.

**발견**:
- `gh`는 GitHub API 도구지만 로컬 repository context를 생략하면 WSL에서 Windows Git metadata를 읽으려 한다. PR 조회·머지에는 `--repo digitie/kor-travel-geo`를 붙이는 것이 안정적이다.
- Next.js 서버 인자는 npm script 구분자 `--` 뒤에 둬야 하며, 실제 지도 e2e는 WSL `next start --hostname 0.0.0.0` 서버에 Windows Playwright를 붙이는 방식이 가장 재현성이 높았다.

## 2026-06-02 21:10 (`/v2/regions/within-radius`와 VWorld 지도 실키 검증)

**작업**: `krtourmap` ADR-045 방향에 맞춰 POI 좌표 기준 반경 `n km` 안에 포함되는 시도·시군구·읍면동을 반환하는 v2 API와 Python client 함수를 추가하고, admin/debug UI에서 해당 함수를 직접 디버깅할 수 있게 했다. VWorld 지도 키는 Python API `.env`의 `KTG_VWORLD_API_KEY`를 우선 읽도록 바꿨고, 확보한 키로 실제 MapLibre/VWorld WMTS 로딩을 검증했다.

**반영**:
- `RegionsWithinRadiusInput`/`Response` DTO, `AsyncAddressClient.regions_within_radius()`, `POST /v2/regions/within-radius`, PostGIS raw SQL repository 함수를 추가했다.
- SQL은 입력 POI를 EPSG:5179로 한 번만 변환하고, `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`의 원본 geometry에 `ST_DWithin`/`ST_Covers`를 적용해 index 사용 방향을 유지했다.
- `/debug/geocode`에 `RegionsWithinRadiusDebugger`를 추가했다. 폼은 React Hook Form/Zod, 요청은 TanStack Query mutation, 마지막 초안/결과는 Zustand store, UI primitive는 shadcn/ui source component로 구성했다.
- `kor-travel-geo-ui` runtime config가 프로세스 환경 또는 저장소 루트 `.env`의 `KTG_VWORLD_API_KEY`를 먼저 읽고, 없을 때만 `NEXT_PUBLIC_VWORLD_API_KEY`를 사용하도록 했다.
- `openapi.json`, frontend generated type/schema, v2 API reference, frontend/backend 문서, CHANGELOG, resume를 갱신했다. 프론트엔드 실행은 WSL Linux Node/npm, Playwright 실행과 브라우저는 Windows로 분리한다는 정책도 문서에 보강했다.
- MapLibre 자체는 `maplibre-vworld` package 경계를 유지하고, 별도 지도 fallback 구현을 만들지 않는다고 문서 경계를 정리했다.

**검증**:
- Backend ext4 mirror: `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `TMPDIR=/tmp TMP=/tmp TEMP=/tmp pytest -q` → `294 passed, 8 skipped`.
- Frontend ext4 mirror: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.
- React Doctor: `npx react-doctor@latest . --offline --verbose --json` → score `100`, warning `0`.
- Windows Playwright: WSL production UI 서버(`next start --hostname 0.0.0.0 --port 13090`)를 대상으로 `PLAYWRIGHT_BASE_URL=http://<WSL_IP>:13090 npx playwright test --config playwright.config.ts --project chromium --workers 1` → `14 passed`.
- 실제 지도 테스트: `vworld-map.spec.ts`가 runtime config에서 Python `.env` VWorld 키가 비어 있지 않음을 확인하고, `/debug/geocode`의 MapLibre canvas와 `https://api.vworld.kr/req/wmts/1.0.0/` 타일 응답을 확인했다. 키 값 자체는 로그에 남기지 않았다.

**발견**:
- Windows `cmd.exe`에서 WSL 서버 대상 e2e를 실행할 때는 `cmd.exe /V:ON /C "set PLAYWRIGHT_BASE_URL=http://<WSL_IP>:<PORT>&& npx playwright test ..."` 형태가 안정적이었다.
- CodeGraph MCP 도구는 현재 세션에 노출되지 않아 CLI `codegraph sync/status/impact`로 UI 영향 범위를 임시 확인했다.

## 2026-06-01 19:52 (`/admin` 기본 라우트와 React Doctor 후속 규칙)

**작업**: `/admin/` 진입 시 404가 나오지 않도록 기본 admin 라우트를 추가하고, 모든 프론트엔드 작업 뒤 React Doctor를 실행해 경고를 수정·재실행하는 규칙을 문서화했다.

**반영**:
- `kor-travel-geo-ui/app/admin/page.tsx`를 추가해 `/admin` 기본 진입을 `/debug/geocode`로 redirect한다.
- `AGENTS.md`, `SKILL.md`, `docs/frontend-package.md`, `docs/resume.md`, `kor-travel-geo-ui/README.md`, `kor-travel-geo-ui/SKILL.md`에 React Doctor 실행·수정·재실행 규칙을 추가했다.
- 루트 `CHANGELOG.md`와 `kor-travel-geo-ui/CHANGELOG.md`에 사용자 가시 변경을 기록했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-admin-redirect`에서 `npx react-doctor@latest . --offline --verbose --json` → score 100, warning 0.
- 같은 mirror에서 `scripts/frontend_check.sh` → `gen:types`, `lint`, `type-check`, unit test 37개, `next build` 통과.
- `next start --port 13089` 후 `curl -i http://<temporary-ui-host>:13089/admin` → `307 Temporary Redirect`, `location: /debug/geocode` 확인. `/admin/`은 Next.js canonical `308` 뒤 `/admin`으로 이동한다.

**발견**:
- 기존 공용 ext4 미러에는 root 소유 `node_modules/.vite`와 `.next` 생성물이 남아 있어 Vitest/Next build write가 막혔다. 검증은 새 mirror에서 `npm ci`부터 다시 실행해 통과시켰다.

## 2026-06-01 13:25 (반복 실패 패턴 원인 정리와 재발 방지 문서화)

**작업**: 이번 세션에서 반복된 에이전트 작업 실패 패턴을 원인별로 정리하고, 다음 세션이 같은 함정을 다시 밟지 않도록 운영 문서를 보강했다.

**반영**:
- `docs/agent-failure-patterns.md`를 추가해 NTFS worktree의 WSL `git` 실패, `exec_command`의 `CreateProcess ... os error 2`, NTFS 경로에서 `apply_patch` 실패, inline rewrite escape 손상을 각각 증상/원인/재발 방지/표준 대응으로 정리했다.
- `docs/agent-guide.md`, `docs/dev-environment.md`, `SKILL.md`에 새 문서 링크와 핵심 우회 원칙을 추가했다.
- `docs/resume.md`와 `CHANGELOG.md`에 이번 문서화 상태를 반영했다.

**발견**:
- NTFS worktree의 Git metadata는 정책상 Windows 경로를 유지하므로 WSL `git` 실패는 버그가 아니라 설계 결과다. 같은 증상이 보이면 즉시 Windows `git.exe -C F:/...`로 전환하는 것이 정답이다.
- `CreateProcess ... os error 2`는 저장소 파일 문제보다 Codex 명령 런처의 quoting/heredoc/workdir 처리 한계일 가능성이 높았다. 단순 명령(`sed`, `rg`, `cd ... && npm run ...`)은 안정적으로 재현됐다.
- NTFS 파일을 inline script로 편집할 때 `\n`, regex backslash, Windows path가 쉽게 손상돼, fallback edit 뒤 재열기와 lint/type-check가 필수다.

**다음**:
- 같은 패턴이 다시 보이면 먼저 `docs/agent-failure-patterns.md` 절차를 적용하고, 새 변종이면 이 문서에 추가한다.

## 2026-06-01 12:50 (React Doctor 잔여 경고 0건 마무리)

**작업**: admin 구조 분해 이후 남아 있던 debug/common React Doctor 경고를 모두 정리했다.

**반영**:
- `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`에서 prop JSX를 static fallback/skeleton으로 고정하고 click handler 이름을 구체화했다.
- `kor-travel-geo-ui/components/debug/GeocodeDebugger.tsx`는 `useReducer`로 state를 묶고, `NormalizeDebugger`는 `normalizeFormSchema`를 실제 입력 검증에 연결했다.
- `kor-travel-geo-ui/app/page.tsx`, `app/debug/*/page.tsx`에 page metadata를 추가했다.
- `kor-travel-geo-ui/lib/sido.ts`는 regex matcher + escape helper로 정리했고, `lib/schemas.ts`, `lib/consistency.ts`, `tests/unit/schemas.test.ts`를 정리해 dead-code 경고를 줄였다.
- `kor-travel-geo-ui/scripts/gen-types.mjs`는 `openapi-typescript` CLI 경로 호출 대신 Node API import 방식으로 정리했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 다시 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `96 → 100`, warning `15 → 0`이 됐다.

## 2026-06-01 10:55 (React Doctor admin 구조 분해 마무리)

**작업**: 남아 있던 admin React Doctor 구조 경고를 마저 정리하고, ext4 테스트 미러에서 전체 frontend 검증을 다시 수행했다.

**반영**:
- `kor-travel-geo-ui/components/admin/LoadConsole.tsx`를 workflow/controller + upload/review/jobs/dialog 섹션으로 분리하고 UI state를 `useReducer`로 묶었다.
- `kor-travel-geo-ui/components/admin/BackupsPanel.tsx`를 controller hook과 backup/restore/jobs/artifacts 패널로 나눠 giant component 경고를 제거했다.
- `kor-travel-geo-ui/components/admin/ConsistencyPanel.tsx`를 query/controller hook과 reports/workbench/layout 섹션으로 분리해 admin 쪽 마지막 `no-giant-component` 경고를 제거했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 다시 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `95 → 96`, warning `19 → 15`로 감소했고 admin 관련 경고는 0건이 됐다. 남은 항목은 debug page metadata, `CoordinateMap`, `GeocodeDebugger`, dead-code 계열이다.

## 2026-06-01 08:45 (React Doctor 기반 admin UI 정리)

**작업**: `react-doctor`를 다시 실행하고 admin UI 경고 중 동작/구조상 바로 고칠 수 있는 항목을 수정했다.

**반영**:
- `kor-travel-geo-ui/lib/vworld-key.tsx`를 TanStack Query 기반 runtime-config 로딩으로 바꿔 `fetch` in `useEffect`를 제거했다.
- `/admin/settings`는 prop 동기화 effect와 derived `useState`를 없애고 브라우저 override 입력 흐름을 draft 값으로 재구성했다.
- `/admin/consistency`는 invalid case 보정을 effect/setState 대신 렌더 시점 파생 선택으로 바꾸고, stale sample selection이 bulk action에 남지 않도록 정리했다.
- `/admin/load`는 병렬 업로드 + multi-XHR cancel, semantic `<dialog>`, lazy ref init, proxy `cache: "no-store"`로 정리했다.
- `/admin/ops`, `/admin/backups`는 관련 state를 묶어 `useState` 남용 경고를 줄였고, `tests/unit/vworld-key.test.tsx`는 QueryClientProvider fixture를 추가했다.

**검증**:
- fresh ext4 mirror `/home/digitie/dev/kor-travel-geo-codex-test-reactdoctor`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`를 통과했다.
- `npx react-doctor@latest . --offline --verbose --json` 재실행 결과 score `90 → 95`, warning `59 → 19`로 감소했다. 남은 항목은 주로 giant component, debug page metadata, dead-code 계열 경고다.

## 2026-06-01 02:40 (T-027/T-047 국가지점번호 포함 재적재와 튜닝 재측정)

**작업**: 사용자 지시에 따라 새 Docker DB `kor-travel-geo-t027-retune`(port `15435`)에서 T-027 전체 적재를 다시 수행하고, 국가지점번호(`tl_sppn_makarea`)를 포함한 T-047 SQL benchmark를 재측정했다. 기존 T-027 최종 DB(port `15434`)는 보존했다.

**반영**:
- `scripts/benchmark_query_performance.py`가 Q11 `sppn_geocode`와 `sppn_reverse`를 모두 측정하도록 보강했다.
- `/v2/reverse` 변환 경로가 v1 `x_extension.sppn_makarea`를 `CandidateV2(match_kind="sppn")` 후보로 승격하도록 했다.
- `scripts/fullload_test.sh` smoke를 최신 v2 Python client 계약(`candidates`, `reverse()`)에 맞췄다.
- `docs/t027-t047-sppn-retune-20260601.md`에 full-load, 전체 daily 적용, 정합성 변화, benchmark 전후 차이, 데이터 보강 의견을 상세 기록했다.

**검증**:
- full-load: `tl_juso_text=6,416,642`, `tl_sppn_makarea=24,204`, `mv_geocode_target=6,416,642`까지 적재 완료. 초기 script는 구형 smoke 계약 때문에 exit 1이었지만 적재는 완료됐고, smoke script를 고친 뒤 수동 smoke를 통과했다.
- daily: 20260402~20260506 daily ZIP 35개를 추가 적용했다. 실제 daily 데이터가 충분해 synthetic delta는 만들지 않았다. 최종 `mv_geocode_target=6,418,735`, `mv_geocode_text_search=6,418,735`.
- consistency: 최종 report `consistency_770acd176f564141abadf95de0009773`, `severity_max=ERROR`. C1/C2/C3은 개선됐고 C4/C6/C7/C8은 기준월 혼합과 direct 출입구 변화 영향으로 증가했다.
- T-047: `t047-retune-standard-20260601-012814`, 2,000 case, 18,000 measurement, error 0. Q11 c64 p95는 `sppn_geocode=90.22ms`, `sppn_reverse=87.45ms`.
- unit smoke: `pytest tests/unit/test_query_performance_benchmark.py tests/unit/test_cli_contract.py tests/unit/test_v2_api.py tests/unit/test_sppn_core.py -q` → 37 passed.

## 2026-05-31 22:44 (VWorld 최신 wrapper 동기화와 PR #108 문서 기준 반영)

**작업**: 사용자 지시에 따라 로컬 git secret 파일에서 VWorld 키 존재 여부만 확인하고, PR #108의 당시 인프라 설정 파일 `./data/*` 기본 볼륨 기준이 현재 코드에 이미 반영되어 있음을 확인했다. `maplibre-vworld-js` upstream `main` 최신 commit `2f8ef8c59f2ff6d6360a16db038841473ea1dc41`과 package version `0.1.2`를 확인한 뒤 `kor-travel-geo-ui` dependency/lockfile을 갱신했다.

**반영**:
- `kor-travel-geo-ui/components/vworld/CoordinateMap.tsx`를 직접 `maplibregl.Map` lifecycle 소유 방식에서 upstream `VWorldMap`/`Marker`/`useMap`/`useMapLoaded`를 감싸는 domain wrapper로 전환했다.
- `kor-travel-geo-ui/lib/vworld.ts`의 `getVWorldRasterStyle`, `redactVWorldTileUrl` local alias를 제거하고 upstream 이름인 `getVWorldStyle()`, `redactVWorldUrl()`로 호출자를 옮겼다.
- `README.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/external-apis.md`, `docs/frontend-package.md`, `docs/resume.md`, `kor-travel-geo-ui/README.md`, `kor-travel-geo-ui/CHANGELOG.md`에 최신 SHA, npm registry 미출시 상태, `VWorldMap` wrapper 전환을 반영했다.
- CodeGraph MCP는 현재 세션 도구로 노출되지 않아 CLI `codegraph sync/status/impact`로 `CoordinateMap.tsx` 영향도를 확인했다.

**검증**:
- ext4 테스트 미러: `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q` → 통과.
- Docker Node(ext4 mirror): `npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build` → 통과.
- T-027 최종 DB pgdata(`/home/digitie/kor-travel-geo-data/pgdata-final-20260529`)를 유지한 채 `kor-travel-geo-t027-final` DB 컨테이너를 재기동했고, API를 `0.0.0.0:8888`로 다시 띄웠다.
- 기존 UI 컨테이너를 내리고 `docker build --no-cache -t kor-travel-geo-ui:vworld-pr108 ./kor-travel-geo-ui`로 클린 빌드한 뒤 `kor-travel-geo-ui-vworld-pr108`을 `13088` 포트에 재기동했다.
- `/v1/healthz`, UI proxy `/api/proxy/v1/healthz`, `/debug/geocode`, `/api/runtime-config` VWorld key 주입, `/v2/geocode`, `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse` smoke를 확인했다.

## 2026-05-31 19:35 (Windows Git 기준과 T-027 DB 재사용 고정)

**작업**: 사용자 지시에 따라 WSL 테스트 미러에서 실행하더라도 Git metadata는 Windows Git과 Windows repo 경로를 기준으로 읽도록 정리했고, PostgreSQL 검증 DB는 새 클린 DB가 아니라 T-027 최종 적재 DB를 재사용하도록 복구했다.

**반영**:
- `scripts/benchmark_api_latency.py`, `scripts/benchmark_query_performance.py`, `scripts/capture_deployment_envelope.py`가 `KTG_GIT_REPO` 또는 ext4 미러 이름에서 `F:/dev/kor-travel-geo-*` 경로를 만들고 Windows `git.exe`로 branch/commit을 수집하도록 바꿨다.
- NTFS worktree의 `.git`/`gitdir` 포인터를 Windows Git 기준 `F:/dev/...`로 되돌렸다. WSL `git` 편의를 위해 `/mnt/f/...`로 바꾸지 않는 규칙을 문서화했다.
- `AGENTS.md`, README, `SKILL.md`, `docs/dev-environment.md`, `docs/agent-guide.md`, `docs/resume.md`에 Windows Git 기준과 T-027 DB 재사용 원칙을 추가했다.
- `kor-travel-geo-codex-clean` DB 컨테이너를 내리고, T-027 최종 pgdata(`/home/digitie/kor-travel-geo-data/pgdata-final-20260529`)를 쓰는 `kor-travel-geo-t027-final` DB를 port `15434`로 다시 올렸다.

**검증**:
- Windows Git: `git.exe -C F:/dev/kor-travel-geo-codex status --short --branch`가 `agent/codex-idle` worktree와 현재 변경 파일을 정상 표시했다.
- ext4 미러에서 세 스크립트의 Git helper가 모두 `agent/codex-idle`을 반환했다.
- T-027 DB row count: `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204`.
- `git.exe -C F:/dev/kor-travel-geo-codex diff --check` → 통과.

## 2026-05-31 14:10 (NTFS main repo와 에이전트 worktree 전환)

**작업**: 사용자 지시에 따라 Git source of truth를 NTFS main repo로 두고, 테스트는 WSL ext4 미러에서 수행하는 정책으로 전환했다.

**반영**:
- NTFS `/mnt/f/dev/kor-travel-geo`를 main repo 기준으로 두고 `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity` worktree를 생성했다.
- 각 worktree에 `.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json`, `backend/.env.local`, `web/.env.local`을 복사했다. secret 값은 출력하지 않았다.
- `kor-travel-geo-ui/.env.local`의 `KTG_API_INTERNAL_URL`은 당시 공식 API 포트 `8888`에 맞춰 placeholder host로 정리했다.
- 세 worktree에서 `codegraph init -i`와 `codegraph status`를 실행했다. NTFS `/mnt` 경로에서는 CodeGraph live watch가 비활성화되므로 이후 branch 전환·pull·merge 뒤 수동 `codegraph sync`가 필요하다.
- `.claude/`를 `.gitignore`에 추가하고, `AGENTS.md`, `SKILL.md`, README, 개발 환경/아키텍처/에이전트 가이드, ADR-041, resume, tasks를 갱신했다.

**검증**:
- `git worktree list`에서 `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity` 등록을 확인했다.
- 세 NTFS worktree의 `git status --short --branch`가 각각 `agent/*-idle...origin/main` clean 상태임을 확인했다.
- 세 NTFS worktree에서 `codegraph sync` → already up to date, `codegraph status` → 249 files, 4,042 nodes, 9,841 edges, `Index is up to date`를 확인했다.
- `rg`로 현재 운영 문서의 예전 ext4 source-of-truth 문구를 점검했다. 남은 `geo-*`/ext4 중심 문구는 superseded ADR-034와 과거 journal/검증 로그로 확인했다.
- `git diff --check` → 통과.

## 2026-05-31 11:40 (API 공식 포트 8888 전환)

**작업**: 사용자 지시에 따라 PC/WSL 개발 환경의 FastAPI 공식 host 포트를 `8000`에서 `8888`로 조정했다.

**반영**:
- README, `docs/ports.md`, `docs/dev-environment.md`, ADR-040의 공식 API 포트를 `8888`로 갱신했다.
- `KTG_API_INTERNAL_URL` 예시와 `kor-travel-geo-ui` 프록시 기본 backend URL을 당시 공식 API 포트 `8888` 기준 placeholder host로 바꿨다.
- API reference curl 예시와 REST latency benchmark 기본 `--base-url`도 `8888`로 맞췄다.

**검증**:
- `npm run type-check` → 통과
- `npm run test` → `36 passed`
- `npm run build` → 통과
- `python -m ruff check scripts/benchmark_api_latency.py` → 통과
- `git diff --check` → 통과
- `curl http://<legacy-api-host>:8888/v1/healthz` → `{"status":"ok"}`
- `curl http://<legacy-ui-host>:13088/api/proxy/v1/healthz` → `{"status":"ok"}`

## 2026-05-31 08:15 (PR #97~#102 리뷰 감사, C1~C10 가로 탭, 포트 공식화)

**작업**: PR #97부터 최신 PR #102까지 상세 리뷰 표면을 확인하고, `/admin/consistency`의 C1~C10 case 선택 UX와 로컬 포트 정책을 정리했다.

**반영**:
- `gh pr view`와 GraphQL `reviewThreads`로 PR #97~#102를 확인했고 unresolved review thread는 전부 0건이었다. PR #98은 #97과 중복되어 close된 상태라 별도 반영 대상이 없었다. 상세 기록은 `docs/postmerge-review-fixups-pr97-pr102.md`에 남겼다.
- `/admin/consistency`의 세로 case rail을 `role=tablist` 기반 가로 스크롤 탭으로 바꿨다. C1~C10은 표본 분석 영역 위에서 좌우 스크롤로 선택하며, 선택 case는 `aria-selected`와 `tabpanel`로 연결된다.
- consistency unit/e2e mock을 C1~C10 전체로 확장하고, C10 탭 존재와 선택 탭 상태를 회귀 테스트로 고정했다.
- 공식 로컬 포트를 PostgreSQL `15434`, FastAPI `8000`, UI `13088`로 문서화했다. `.env.example`, 당시 인프라 설정 파일, README, `kor-travel-geo-ui/README.md`, `docs/ports.md`, `docs/dev-environment.md`, ADR-040을 갱신했다.
- Playwright e2e는 Windows Node/브라우저에서만 실행한다고 문서화했다. WSL에서는 반복적으로 `libasound.so.2` 누락이 발생하므로 `npm run test:e2e`를 실행하지 않는다.

**검증**:
- `npm run lint` → 통과
- `npm run type-check` → 통과
- `npm run test -- consistency-panel` → `3 passed`
- `npm run test` → `36 passed`
- `npm run build` → 통과
- `git diff --check` → 통과
- 공식 UI 포트 `13088` dev server에서 `/admin/consistency` HTML에 `case-tab-list`가 포함됨을 확인했다.
- WSL Playwright는 `libasound.so.2` 누락으로 실패했다. 이 경로는 더 이상 검증 루틴으로 쓰지 않는다.

## 2026-05-31 01:10 (에이전트별 MCP 설정 추가)

**작업**: Claude Code, GPT Codex, Antigravity 에이전트의 로컬 설정 파일에 `playwright` 및 `sequential-thinking` MCP 서버를 추가했다.

**반영**:
- `.codex/config.toml`에 `playwright` 및 `sequential-thinking` MCP 서버 구성을 TOML 형식으로 반영했다.
- `claude.json`과 `antigravity.json`을 새로 생성하여 해당 MCP 구성을 JSON 형식으로 반영했다.
- 생성/변경된 3가지 설정 파일을 git staging 영역에 등록했다.

## 2026-05-30 11:45 (T-067 v2 geocode point+geometry overlay)

**작업**: `/v2/geocode`와 디버그 UI에서 기존 대표점(`point`)을 유지하면서 행정구역/도로/건물 도형을 함께 확인할 수 있도록 보강했다.

**반영**:
- `GeocodeV2Input.include_geometry`와 `CandidateV2.geometry`/`GeometryV2`를 추가했다. 기본값은 `false`이며, 디버그 UI는 기본으로 `true`를 보낸다.
- 건물 주소는 기존 geocode 후보의 `point`를 그대로 유지하고 `tl_spbd_buld_polygon` polygon을 추가한다. `bd_mgt_sn` 직접 lookup이 실패하면 `rncode_full + bjd_cd + 건물번호` natural key로 도형을 찾는다.
- 상세번호 없는 도로명 입력은 district fallback 전에 `tl_sprd_manage` 도로 line 후보를 먼저 반환한다.
- 행정구역 후보는 `tl_scco_ctprvn/sig/emd/li` 도형을 후보에 붙인다.
- `/debug/geocode`와 `/debug/reverse`는 응답 JSON을 입력 아래에 두고, 지도 패널을 크게 분리했다. `CoordinateMap`은 point marker와 GeoJSON overlay를 동시에 표시하며, viewport는 `bbox`와 `point`를 함께 포함한다.

**실제 DB 확인**:
- `성복동` → `match_kind=region`, point `(127.05932949615165, 37.319558336433374)`, `geometry=region/MultiPolygon`
- `성복1로` → `match_kind=road`, point `(127.0610437873178, 37.32091740399021)`, `geometry=road/MultiLineString`
- `성복1로 35` → 기존 point `(127.07430262108355, 37.31347098160811)` 유지, `geometry=building/MultiPolygon`

**검증**:
- `pytest tests/unit/test_v2_api.py -q` → `10 passed`
- `ruff check ...` → 통과
- `mypy --strict src/kortravelgeo/dto/v2.py src/kortravelgeo/core/protocols.py src/kortravelgeo/core/v2.py src/kortravelgeo/infra/geometry_repo.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/v2.py` → 통과
- `npm run gen:types`, `npm run lint`, `npm run type-check`, `npm run test` → 통과

## 2026-05-30 10:10 (T-066 Consistency 탭 진입 프리즈 완화)

**작업**: `/admin/consistency` 진입 시 브라우저 탭이 멈추는 현상을 우선 확인하고, 초기 렌더에서 무거운 지도 컴포넌트가 자동 로드되지 않도록 수정했다.

**반영**:
- 백엔드 consistency list/detail/sample/summary API는 Docker DB 기준 모두 정상 응답함을 확인했다.
- 기존 UI는 sample을 고르기 전에도 첫 `point` 샘플을 자동으로 지도에 넣어 `LazyCoordinateMap`과 MapLibre/VWorld 타일 요청을 즉시 시작했다.
- `selectedSampleId`가 없으면 `selectedSample=null`로 유지하고, sample 선택 전에는 지도 대신 가벼운 placeholder를 표시한다.
- `tests/unit/consistency-panel.test.tsx`를 추가해 샘플 목록 로드만으로는 `LazyCoordinateMap`이 호출되지 않고, 사용자가 sample을 클릭한 뒤에만 지도 컴포넌트가 로드되는지 고정했다.

**검증**:
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test -- consistency-panel consistency` → `2 passed`, `4 tests`
- WSL Playwright headless Chromium은 `libasound.so.2` 누락으로 실행하지 못했다. 최종 브라우저 회귀는 사용자가 지정한 Windows Playwright 환경에서 확인한다.

## 2026-05-30 08:45 (T-065 내비게이션용DB 시군구용건물명 검색 반영)

**작업**: `내비게이션용DB_전체분/match_build_*.txt`의 `시군구용건물명`을 적재·정규화하고 검색 후보에 반영했다.

**반영**:
- 실제 202604 전국 파일에서 `시군구용건물명`이 20번째 컬럼(`row[19]`)임을 확인했다. non-empty row는 `773,407 / 10,721,310`, distinct 값은 `77,790`개였다.
- `tl_navi_buld_centroid`에 `sigungu_buld_nm`과 generated column `sigungu_buld_nm_nrm`을 추가하고, loader COPY/upsert 경로에 연결했다.
- `mv_geocode_target`과 `mv_geocode_text_search`가 `sigungu_buld_nm_nrm`을 포함하도록 확장했다.
- `/v2/search` exact preflight와 broad trigram fallback에서 `sigungu_buld_nm_nrm`을 점수화한다.
- 실제 검증 중 shadow swap 후 `ANALYZE` transaction이 기본 statement timeout에 걸려, `shadow_swap_mv()`의 후속 ANALYZE transaction에도 `SET LOCAL statement_timeout = 0`을 추가했다.
- 두 번째 검증에서는 release metadata 기록 중 `SELECT max(source_yyyymm) FROM tl_navi_buld_centroid`가 기본 statement timeout에 걸려, `record_mv_refresh_release()`에도 운영 작업용 `SET LOCAL statement_timeout = 0`을 추가했다.

**실제 DB 검증**:
- Docker DB `localhost:15434`에 새 컬럼을 적용하고 NAVI를 재적재했다. 결과는 `tl_navi_buld_centroid=10,687,317`, `tl_navi_entrc=12,830`, 소요 `457초`.
- `mv_geocode_target`/`mv_geocode_text_search`를 새 컬럼 포함 상태로 재생성했다. 수동 `SET statement_timeout=0` 후 `ANALYZE`는 `12초`에 완료됐다.
- timeout 보강 뒤 release metadata 기록 경로를 직접 재호출해 active release `7b3455b6-e682-4d16-92f7-65fcad33e219` 생성을 확인했다.
- 변경 전 `NOT_FOUND`였던 `/v2/search` `엄마집`, `sig_cd=26110`은 부산광역시 중구 영주로 58 후보를 반환했다. 20회 API 측정 p50 `6.03ms`, p95 `7.42ms`.
- 변경 전 `NOT_FOUND`였던 `/v2/search` `P-101동`, `sig_cd=26110`은 부산광역시 중구 초량상로 13 등 후보 4건을 반환했다. 20회 API 측정 p50 `16.53ms`, p95 `20.12ms`.

**검증**:
- `pytest tests/unit/test_navi_loader.py tests/unit/test_infra_repo_sql.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_alembic_migrations.py -q` → `34 passed`
- `pytest tests/integration/test_real_juso_text_loaders.py::test_actual_navi_files_load_building_centroid_and_entrance_rows -q` → `1 passed`
- `ruff check ...` → 통과
- Docker UI proxy `/api/proxy/v2/search` `엄마집`, `sig_cd=26110` → `OK`

## 2026-05-30 02:20 (상위 주소 geocode 후보와 내비 검색 후속 문서화)

**작업**: 별도 geocode 경로를 만들지 않고, 상세번호 없는 상위 주소 입력을 기존 `/v2/geocode` 후보 흐름 안에서 처리하도록 보강했다.

**반영**:
- `/v2/geocode`에서 도로명/지번 parser가 번호 부재로 실패하면 같은 입력을 `search(type="district")` 후보로 승격한다.
- `district` 검색은 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li` polygon을 사용하고 대표점은 `ST_PointOnSurface`로 계산한다.
- 실제 Docker DB에서 `수지구` 입력의 첫 후보가 `용인시 수지구(sig_cd=41465)`와 대표점 `(127.08875165616607, 37.3327969096687)`를 반환함을 확인했다.
- 사용자 지시에 따라 `내비게이션용DB_전체분`의 `시군구용건물명` 컬럼을 후속 T-065 검색 보강으로 등록하고, 적재/정규화/검색 helper MV/성능 기록 요구사항을 문서화했다.

**검증**:
- `pytest tests/unit/test_infra_repo_sql.py tests/unit/test_v2_api.py -q` → `27 passed`
- `/v2/geocode` `{"road_address":"수지구"}` smoke `OK`
- `/v2/search` `{"query":"수지구","type":"district"}` smoke `OK`

## 2026-05-30 01:40 (외부 API fallback 인증키 오류 명시화)

**작업**: `fallback="api"` 요청에서 외부 API fallback이 실패할 때 인증키/설정 문제와 단순 미검색이 구분되도록 보강했다.

**반영**:
- 백엔드 fallback은 `KTG_VWORLD_API_KEY` 또는 `KTG_JUSO_API_KEY`를 사용한다. UI 지도용 `NEXT_PUBLIC_VWORLD_API_KEY`만 있으면 fallback 키로 보지 않는다.
- `fallback="api"`인데 provider 키가 하나도 없으면 `E0503` 설정 오류와 함께 필요한 환경변수 hint를 반환한다.
- VWorld `INVALID_KEY`, Juso `E0001`/KEY 오류는 `E0501` 외부 API 인증 오류로 명시해 반환한다.
- 로컬 `.env`에는 사용자 제공 VWorld 키를 `KTG_VWORLD_API_KEY`로 추가하고 권한을 `600`으로 조정했다. `.env`는 gitignore 대상이라 커밋하지 않는다.

**검증**:
- 키 없음 상태 `/v2/geocode fallback=api` → HTTP 500, `E0503`, `KTG_VWORLD_API_KEY` hint 확인
- 잘못된 VWorld 키 상태 `/v2/geocode fallback=api` → HTTP 502, `E0501`, `VWorld API authentication failed`, `INVALID_KEY` hint 확인
- 사용자 제공 키로 `ExternalGeocodeClient` live VWorld geocode `OK`
- `pytest tests/unit/test_external_api.py -q` → `6 passed`

## 2026-05-30 00:55 (단독 구 이름 도로명주소 조회 보정)

**작업**: `수지구 성복1로 35`처럼 시군구가 복합명(`용인시 수지구`)으로 저장되어 있지만 사용자가 단독 구 이름만 입력한 도로명주소 조회를 보정했다.

**반영**:
- 기본 도로명 exact lookup은 기존처럼 `sgg_nm = :sgg` 조건을 유지한다.
- 정확 조회가 실패하고 입력 시군구가 공백 없는 단독 `구` 이름일 때만 별도 suffix retry를 1회 수행한다.
- suffix retry는 선행 와일드카드 `LIKE`를 쓰지 않고, `rn_nrm`/건물번호 exact 조건으로 후보를 좁힌 뒤 `right(sgg_nm, char_length(:sgg_suffix))`를 적용한다.

**검증**:
- `수지구 성복1로 35`, `용인시 수지구 성복1로 35`, `경기도 용인시 수지구 성복1로 35`, `성복1로 35` 모두 실제 Docker DB에서 `OK` 확인
- fallback query `EXPLAIN (ANALYZE, BUFFERS)` → `idx_mv_rn_nrm_exact` index scan, execution time 약 0.49ms
- `ruff check src/kortravelgeo/infra/geocode_repo.py tests/unit/test_infra_repo_sql.py`
- `pytest tests/unit/test_infra_repo_sql.py tests/unit/test_core_geocoder.py -q` → `23 passed`

## 2026-05-30 00:15 (VWorld 인증키 런타임 설정 UI)

**작업**: VWorld 인증키를 `.env`에서 런타임으로 읽고, UI에서 저장·수정할 수 있도록 보강했다.

**반영**:
- `/api/runtime-config`가 서버 런타임의 `NEXT_PUBLIC_VWORLD_API_KEY`를 `no-store` JSON으로 반환한다.
- `VWorldKeyProvider`가 `.env` 기본값을 읽고, 브라우저 localStorage override가 있으면 그 값을 우선 적용한다.
- `/admin/settings`에서 인증키 입력, 저장, `.env` 기본값 복원을 지원한다.
- `CoordinateMap`은 기존 build-time `process.env` 직접 참조 대신 provider의 런타임 키를 사용한다.

**검증**:
- `npm run lint`
- `npm run type-check`
- `npm run test` → `33 passed`
- `npm run build`
- `docker build -t kor-travel-geo-ui:debug-v2 ./kor-travel-geo-ui`
- Docker UI `/api/runtime-config` → 사용자 제공 VWorld 키 반환 확인
- Docker UI `/api/proxy/v2/geocode` smoke `OK`
- Windows Playwright: `8 passed`

## 2026-05-29 23:20 (디버그 UI v2 REST 전환과 Windows Playwright e2e)

**작업**: 디버그 UI의 geocode/reverse 화면이 v2 REST API를 직접 사용하는지 재확인하고, v1 기반 호출을 v2 요청 body 중심으로 전환했다.

**반영**:
- `/debug/geocode`는 `/v2/geocode`에 `road_address` 또는 `jibun_address`, `fallback`, `limit`을 POST한다.
- `/debug/reverse`는 `/v2/reverse`에 `lon`, `lat`, `crs`, `include_region`, `include_zipcode`, `radius_m`을 POST한다.
- 프론트엔드 proxy와 `backendPath()`가 `/v1/*`와 `/v2/*`를 모두 보존하되, non-versioned path는 기존처럼 `/v1`로 보낸다.
- `kor-travel-geo-ui` Dockerfile을 추가하고, Docker 이미지 실행 runbook을 README에 보강했다.
- Playwright e2e 6개를 추가해 도로명/지번 geocode body, 빈 주소 차단, reverse 기본 body, reverse 입력 변경, 범위 밖 좌표 차단을 검증한다.

**검증**:
- `npm run lint`
- `npm run type-check`
- `npm run test` → `30 passed`
- Windows Playwright: `6 passed`
- `npm run build`
- `docker build -t kor-travel-geo-ui:debug-v2 ./kor-travel-geo-ui`
- Docker UI `http://<legacy-ui-host>:13088`에서 `/api/proxy/v2/geocode`, `/api/proxy/v2/reverse` POST smoke `OK`

**후속**:
- 실제 백엔드와 연결한 UI e2e는 Docker UI + Windows Playwright 조합을 기준으로 실행한다.

## 2026-05-29 21:37 (Python 라이브러리 API v2 단일화)

**작업**: 사용자 요청에 따라 Python 라이브러리 주소 조회 API에서 v1-style 공개 메서드를 제거하고 v2 후보 schema를 접미사 없는 기본 메서드로 승격했다.

**반영**:
- `AsyncAddressClient.geocode()`, `reverse()`, `search()`가 각각 `GeocodeV2Response`, `ReverseV2Response`, `SearchV2Response`를 반환한다.
- 공개 Python API에서 `geocode_v2()`, `reverse_v2()`, `search_v2()`, `reverse_geocode()`를 제거했다.
- REST `/v1/*` 라우터는 내부 `_geocode_v1`, `_reverse_geocode_v1`, `_search_v1` adapter를 호출해 vworld 호환 응답을 유지한다.
- REST `/v2/*` 라우터는 접미사 없는 Python 메서드를 호출한다.
- ADR-039, README, API reference, backend/reverse/external API 문서를 갱신했다.

**검증 예정**:
- v2/client 단위 테스트, v1/v2 라우터 contract 테스트, ruff/mypy/lint-imports를 실행한다.

**후속**:
- 기존 Python 사용자가 vworld 호환 DTO를 직접 기대하는 경우 REST `/v1/*` 또는 별도 migration 문서를 안내한다.

## 2026-05-29 18:45 (PR #69~#86 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 T-027 PR merge 뒤 PR #69부터 최신 PR #86까지 conversation/review/latestReview/reviewThreads를 다시 확인했다.

**반영**:
- PR #69~#86 모두 merged 상태, conversation comment 0건, GraphQL review thread 0건임을 확인했다.
- PR #84 사후 리뷰를 반영해 GeoIP gate가 admission control보다 바깥에서 먼저 실행되도록 middleware 설치 순서를 바꿨다.
- `classify_ip()`의 `testclient` 호스트명 특별 허용을 제거해 잘못된 client host는 `invalid_client_ip`로 deny되게 했다.
- `X-Forwarded-For` 항목이 `1.2.3.4:port` 또는 `[IPv6]:port` 형태여도 마지막 untrusted client IP를 추출하도록 보강했다.
- `docs/postmerge-review-fixups-pr69-pr86.md`와 `docs/t054-korea-only-geoip.md`에 반영/보류 항목을 정리했다.

**검증**:
- `ruff check src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py tests/unit/test_geoip_gate.py`
- `pytest tests/unit/test_geoip_gate.py tests/unit/test_api_admission_control.py tests/unit/test_api_app_contract.py -q` → `14 passed`
- `mypy --no-incremental src/kortravelgeo/api/app.py src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py`

**후속**:
- v2 `distance_m`/confidence/precision, C1~C10 전수 export, callback receiver 예제, release ledger repair, table 단위 shared lock은 후속 후보로 유지한다.

## 2026-05-29 18:05 (T-027 최종 실 데이터 클린 재적재 검증)

**작업**: 남은 튜닝/증분/보조 로더 작업을 모두 반영한 최신 코드로 실제 전국 데이터를 빈 Docker PostGIS DB에 처음부터 다시 적재했다.

**반영**:
- `scripts/fullload_test.sh`에 선택 `DAILY_JUSO_ZIP`/`DAILY_YYYYMM` phase를 추가해 full snapshot 뒤 실제 daily MST/LNBR delta를 함께 검증할 수 있게 했다.
- 새 compose project `kor-travel-geo-t027-final`, port `15434`, 전용 `pgdata-final-20260529`로 기존 DB와 분리해 클린 로드를 실행했다.
- 전체 3,963초, `mv_geocode_target=6,416,642`, `mv_geocode_text_search=6,416,642`, `tl_sppn_makarea=24,204`, active serving release `faa1f42b-f5b9-4ef0-af0b-1a422d938ed3`를 확인했다.
- `20260401_dailyjusukrdata.zip`은 `daily-juso` 422건 처리/upsert 242/delete 180, `daily-parcel-links` 204건 처리/upsert 74/delete 82로 적용됐다.
- C1~C10은 `severity_max=ERROR`이며 C2/C4/C6/C7은 기존 실제 원천 품질 이슈로 남았다. C2/C4/C6/C7 data-quality CSV 8개와 DB size snapshot을 남겼다.

**검증**:
- `PLAN_ONLY=1` preflight 통과
- `bash scripts/fullload_test.sh` → exit status 0, wall clock 1:06:02
- `ktgctl validate consistency --scope full` → `consistency_163e89acfb4a41e0a8c19599c2faa678`
- smoke: geocode/reverse/search/zipcode `OK`
- `ktgctl validate data-quality-samples --cases C2,C4,C6,C7 --limit 20` → CSV 8개 생성

**후속**:
- 즉시 실행 가능한 대기 task는 없다.
- N150/Odroid 실제 장비가 준비되면 T-063 실측을 진행한다.

## 2026-05-29 16:20 (T-055 N150/Odroid 운영 환경 비교 준비)

**작업**: 실제 N150/Odroid 장비 도착 전 수행 가능한 측정 준비를 완료했다.

**반영**:
- `scripts/capture_deployment_envelope.py`를 추가해 OS/CPU/메모리/NVMe/Docker/GDAL/PostgreSQL/fio/sysbench/zstd 정보를 `system-envelope.json`과 `system-envelope.md`로 캡처한다.
- 기본 실행은 부하가 낮은 시스템 정보만 수집하고, `fio`/`sysbench`는 `--run-probes`를 명시한 경우에만 실행하게 했다.
- T-027 full-load, T-047 SQL benchmark, REST e2e benchmark, MV refresh/swap benchmark를 같은 `artifacts/perf/n150-vs-odroid-*` 구조로 남기는 runbook을 `docs/t055-deployment-n150-odroid.md`에 고정했다.
- 실제 장비 실측은 하드웨어가 있어야 의미가 있으므로 T-063으로 보류하고, 다음 실행 가능 작업을 T-027 최종 클린 적재 검증으로 정리했다.

**검증**:
- `ruff check scripts/capture_deployment_envelope.py tests/unit/test_capture_deployment_envelope.py`
- `pytest tests/unit/test_capture_deployment_envelope.py -q` → `5 passed`
- `python scripts/capture_deployment_envelope.py --env-label wsl-smoke --data-dir data --output-dir /tmp/kortravel-t055-envelope-smoke`
- `ruff check .`
- `pytest -q` → `273 passed, 8 skipped`
- `mypy --no-incremental src/kortravelgeo`
- `lint-imports`

**후속**:
- PR merge 후 T-027 최종 실 데이터 클린 적재 검증으로 이어간다.
- N150/Odroid 장비가 준비되면 T-063에서 T-055 runbook으로 최소 3회 반복 실측한다.

## 2026-05-29 15:35 (T-054 한국 IP GeoIP gate)

**작업**: 외부 공용 IP에서 호출되는 REST API를 대한민국 IP로 제한하는 1차 middleware를 구현했다.

**반영**:
- `infra.geoip`에 IP/CIDR 분류, MaxMind country reader, trusted proxy `X-Forwarded-For` 처리, open path 판정을 추가했다.
- FastAPI middleware가 `/v1/healthz`, `/metrics`를 제외한 REST 표면에서 내부/loopback은 허용하고 공용 IP는 country `KR`만 허용한다.
- strict/permissive/off mode, allow/deny CIDR, trusted proxy, audit 설정을 `Settings`와 `.env.example`에 추가했다.
- deny 응답은 `E0403/403`이며, `geoip.denied` audit event에는 IP 원문을 payload에 넣지 않고 `AdminRepository`의 hash 경로를 사용한다.
- `ktgctl geoip check <ip>` 진단 명령과 단위/middleware 테스트를 추가했다.

**검증**:
- `ruff check src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py src/kortravelgeo/api/app.py src/kortravelgeo/cli/main.py src/kortravelgeo/settings.py tests/unit/test_geoip_gate.py tests/unit/test_settings.py`
- `pytest tests/unit/test_geoip_gate.py tests/unit/test_settings.py tests/unit/test_api_app_contract.py -q` → `14 passed`
- `mypy --no-incremental src/kortravelgeo/infra/geoip.py src/kortravelgeo/api/middleware/geoip_gate.py src/kortravelgeo/api/app.py src/kortravelgeo/cli/main.py src/kortravelgeo/settings.py`
- CLI smoke: `ktgctl geoip check 8.8.8.8` → `geoip_db_unavailable` deny
- `ruff check .`, `pytest -q` → `268 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-055 N150/Odroid 실측 준비로 이어간다.

## 2026-05-29 14:45 (PR #69~#82 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #82 merge 뒤 PR #69부터 최신 PR #82까지 formal review와 review thread를 다시 확인했다.

**반영**:
- 모든 대상 PR의 GraphQL `reviewThreads.totalCount`는 0이었다.
- PR #81 리뷰에서 발견된 실제 런타임 버그를 수정했다. `replace_current` restore의 `maintenance_window.authorize` audit event가 `ops.audit_events.actor_type` CHECK에 없는 `job`을 쓰지 않도록 `system`으로 바꿨다.
- table stats scheduler 호출부에 `skip_if_locked=True`를 명시해 scheduler는 lock 충돌 시 조용히 skip하고, 수동 capture만 `409 E0409`로 실패한다는 의도를 고정했다.
- 상세 리뷰별 반영/보류 표는 `docs/postmerge-review-fixups-pr69-pr82.md`에 정리했다.

**검증**:
- `ruff check src/kortravelgeo/infra/backup.py src/kortravelgeo/api/app.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q` → `22 passed`
- `mypy --no-incremental src/kortravelgeo/infra/backup.py src/kortravelgeo/api/app.py`
- `ruff check .`, `pytest -q` → `261 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-054 한국 IP 외부 접근 차단으로 이어간다.

## 2026-05-29 13:45 (T-059 CLI/Job 동시 실행 보호 표준화)

**작업**: PostgreSQL advisory lock 기반 cross-process 실행 보호를 CLI와 API job handler에 표준 적용했다.

**반영**:
- `src/kortravelgeo/infra/concurrency.py`를 추가해 `AdvisoryLockNamespace`, `AdvisoryLockKey`, `ConcurrentExecutionError(E0409/409)`, `cross_process_lock()`을 제공한다.
- 주요 CLI 운영 명령(`init-db`, `load *`, `refresh mv`, `validate consistency`, `uploads cleanup`, `backup create`, `restore create`)이 명령별/path별/target별 lock key를 잡고 중복 실행 시 exit code 2로 fail-fast한다.
- FastAPI `JobQueue` 기본 handler도 같은 lock key를 잡도록 등록해 CLI와 API job이 같은 자원을 동시에 만지는 것을 막는다.
- PR #82 리뷰 후속으로 미사용 `wait` 경로와 혼동 가능한 `OPS_TABLE_STATS` enum 멤버를 제거하고, API queue의 lock 충돌은 `lock_conflict` progress event 후 `failed`로 닫는다고 문서화했다.
- 실제 Docker PostgreSQL에서 같은 `MV_REFRESH` key를 두 connection으로 잡아 두 번째 connection이 `E0409/409`로 막히는 smoke를 확인했다.
- CLI 단독 실행을 `load_jobs` row로 노출하는 운영 가시화는 후속으로 남겼다.

**검증**:
- `ruff check src/kortravelgeo/infra/concurrency.py src/kortravelgeo/cli/main.py src/kortravelgeo/api/app.py tests/unit/test_concurrency.py tests/unit/test_api_app_contract.py`
- `pytest tests/unit/test_api_app_contract.py tests/unit/test_concurrency.py -q` → `6 passed`
- `pytest tests/unit/test_concurrency.py tests/unit/test_client_submit_load_batch.py tests/unit/test_backup_restore.py -q` → `23 passed`
- Docker PostgreSQL smoke: 같은 `MV_REFRESH` key의 두 번째 connection이 `E0409/409`로 차단됨
- `ruff check .`, `pytest -q` → `261 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-054 한국 IP 외부 접근 차단으로 이어간다.

## 2026-05-29 12:35 (PR #69~#80 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 현재 작업 PR #80 merge 뒤 PR #69부터 최신 PR #80까지 상세 리뷰와 review thread를 다시 확인했다.

**반영**:
- PR #69~#75는 기존 `docs/postmerge-review-fixups-pr69-pr75.md`와 PR #76 반영 상태를 재확인했다.
- 모든 대상 PR의 GraphQL `reviewThreads.totalCount`는 0이었다.
- PR #77 후속으로 수동 table stats capture가 scheduler lock 충돌을 `[]` 성공처럼 반환하지 않고 `409 E0409`로 보고하도록 했다. scheduler만 기존처럼 `skip_if_locked=True`로 조용히 건너뛴다.
- PR #78 후속으로 `replace_current` restore가 active maintenance window를 통과할 때 `ops.audit_events(action='maintenance_window.authorize')`를 남기게 했다. window는 기간 gate로 유지하며 자동 소비하지 않는다고 문서화했다.
- PR #79와 #80은 머지 전 반영된 리뷰 후속이 main에 포함됐음을 재확인했다.

**검증**:
- `ruff check src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q` → `22 passed`
- `mypy --no-incremental src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py`
- `ruff check .`, `pytest -q` → `257 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`

**후속**:
- 이 PR merge 후 T-059 CLI/Job 동시 실행 보호 표준화로 이어간다.

## 2026-05-29 11:40 (PR #80 리뷰 후속 — restore hot-swap plan 보강)

**작업**: PR #80 formal review에서 나온 restore hot-swap plan의 edge case를 반영했다.

**반영**:
- 자동 `previous_alias` 생성 시 `datetime.now(UTC)`를 한 번만 고정해 DB 존재 확인과 반환 plan이 같은 alias를 보도록 했다.
- `existing_databases=None`은 미확인, 빈 set은 실제 확인 결과 0건으로 구분해 missing DB blocker를 보고한다.
- 현재 DB 이름이 긴 경우 `_previous_YYYYMMDD_HHMMSS` suffix를 보존하고 prefix를 잘라 PostgreSQL 63자 identifier 제한을 지킨다.
- managed/hardened cluster에서 `postgres` DB 접속이 제한될 수 있으므로 `maintenance_database`를 API/CLI 요청으로 지정할 수 있게 했다.

**검증**:
- `scripts/export_openapi.py`, `kor-travel-geo-ui npm run gen:types`
- `ruff check src/kortravelgeo/dto/admin.py src/kortravelgeo/infra/hotswap.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/admin.py src/kortravelgeo/cli/main.py tests/unit/test_restore_hotswap.py`
- `pytest tests/unit/test_restore_hotswap.py tests/unit/test_dto_search_zipcode_pobox_admin.py tests/unit/test_openapi_export.py -q` → `13 passed`
- `mypy --no-incremental src/kortravelgeo/infra/hotswap.py src/kortravelgeo/dto/admin.py src/kortravelgeo/client.py src/kortravelgeo/api/routers/admin.py src/kortravelgeo/cli/main.py`
- CLI smoke: `ktgctl serving hot-swap-plan --restore-db kor_travel_geo_restore_missing --maintenance-db postgres`
- `ruff check .`, `pytest -q` → `257 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`
- `kor-travel-geo-ui` Linux npm gate: `lint`, `type-check`, `test`, `build`

**후속**:
- PR #80 CI 완료 후 5분 대기, 리뷰 재확인, merge를 진행한다.

## 2026-05-29 11:05 (T-058 restore hot-swap plan/preflight)

**작업**: T-058의 restore hot-swap 패턴을 실제 rename 실행 전 plan/preflight 표면으로 구현했다.

**반영**:
- `RestoreHotSwapPlanRequest`/`RestoreHotSwapPlan` DTO를 추가했다.
- `infra/hotswap.py`에서 current DB, restore DB, previous alias, maintenance DB, typed confirmation, rollback confirmation, blocker, SQL/steps를 산출한다.
- `/v1/admin/restores/hot-swap-plan` API와 `AsyncAddressClient.restore_hot_swap_plan()`을 추가했다.
- `ktgctl serving hot-swap-plan` CLI를 추가했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입을 갱신했다.
- 실제 `ALTER DATABASE ... RENAME` 실행은 ops metadata 위치와 worker별 engine refresh/rollback round-trip 검증이 더 필요해 후속 실행 표면으로 분리하고, T-058 문서에 명시했다.

**검증 예정**:
- hot-swap plan 단위 테스트, DTO/API/OpenAPI drift, backend/frontend gate를 실행한 뒤 PR을 올린다.

**후속**:
- 이 PR merge 후 T-059 CLI/Job 동시 실행 보호 표준화로 이어간다.

## 2026-05-29 09:45 (T-050 운영 hardening 7차 — 실제 PostgreSQL 제약 통합 테스트)

**작업**: T-050 마지막 항목인 실제 PostgreSQL FK/trigger/partial unique integration test를 추가했다.

**반영**:
- `tests/integration/test_optional_real_postgres_ops_constraints.py`를 추가했다.
- `KTG_TEST_PG_DSN`이 없으면 skip하고, 설정되면 `SCHEMA_SQL`/`INDEX_SQL`을 실제 DB에 적용한 뒤 운영 메타데이터 제약을 검증한다.
- `ops.audit_events.job_id` FK가 감사 이벤트가 붙은 `load_jobs` 삭제를 막는지 확인한다.
- `ops.audit_events` append-only trigger가 `UPDATE`와 `DELETE`를 모두 막는지 확인한다.
- `ops.serving_releases` active partial unique index가 active release 1건만 허용하고 pending release는 허용하는지 확인한다.
- `ops.table_stats_snapshots.snapshot_id` FK가 잘못된 dataset snapshot 참조를 막고 유효한 참조는 허용하는지 확인한다.
- PR #79 리뷰 Low 제안에 따라 DSN 대상 DB 이름 guard와 필수 extension package 사전 skip을 추가했다.
- T-050/resume/tasks/CHANGELOG 문서를 T-050 완료 상태로 갱신했다.

**검증**:
- `ruff check tests/integration/test_optional_real_postgres_ops_constraints.py`
- DSN 미설정: `pytest tests/integration/test_optional_real_postgres_ops_constraints.py -q` → `1 skipped`
- 실제 Docker PostgreSQL 별도 DB `kor_travel_geo_t050_ops_constraints`: `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t050_ops_constraints pytest tests/integration/test_optional_real_postgres_ops_constraints.py -q` → `1 passed`
- 테스트 완료 후 별도 DB를 삭제했다.

**후속**:
- 이 PR merge 후 T-058 restore hot-swap으로 이어간다.

## 2026-05-29 09:15 (T-050 운영 hardening 6차 — destructive confirmation flow)

**작업**: T-050 남은 항목 중 destructive confirmation flow를 기존 `db_restore` 위험 경로에 연결했다.

**반영**:
- `AdminRepository.require_active_maintenance_window()`를 추가해 active window, 유효 기간, confirmation hash를 함께 확인한다.
- `db_restore`의 `replace_current` 모드는 `target_dsn`을 받지 않고 target DB 이름이 현재 설정 DB 이름과 같아야 하며, 확인 문구 `RESTORE <현재 DB 이름>`이 일치해야 하고, 같은 확인 문구 hash를 가진 active `restore` maintenance window가 있어야 한다.
- 잘못된 target DB로 `replace_current`를 지정해 빈 DB preflight를 우회하는 경로를 차단했다.
- T-046/T-050/T-058/backend/frontend/resume/tasks/CHANGELOG 문서를 갱신했다.

**검증 예정**:
- backup/restore 단위 테스트와 ops metadata source contract를 실행한 뒤 전체 backend gate를 확인한다.

**후속**:
- 이 PR merge 후 실제 PostgreSQL FK/trigger/partial unique integration test로 T-050을 마무리한다.

## 2026-05-29 08:25 (T-050 운영 hardening 5차 — table stats 주기 capture)

**작업**: T-050 남은 항목 중 `ops.table_stats_snapshots` 주기 capture를 구현했다.

**반영**:
- `KTG_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES`, `KTG_OPS_TABLE_STATS_CAPTURE_LIMIT`, `KTG_OPS_TABLE_STATS_CAPTURE_ON_STARTUP` 설정을 추가했다.
- FastAPI lifespan에서 interval이 1 이상일 때만 background task를 띄워 `AdminRepository.capture_table_stats_snapshots()`를 주기 실행한다.
- 여러 API worker의 동시 capture 중복을 줄이기 위해 `pg_try_advisory_xact_lock(0x4B4700A0)`을 capture transaction 앞에 추가했다.
- 수동/주기 capture에서 `snapshot_id`를 생략하면 현재 active serving release의 `snapshot_id`에 자동 연결한다.
- 연결 방식은 각 row의 `stats.snapshot_link`에 `explicit`, `active_serving_release`, `unlinked`로 남긴다.
- T-050/T-049/backend/frontend/data-model/resume/tasks/CHANGELOG 문서를 갱신했다.

**검증 예정**:
- backend targeted gate와 전체 backend gate를 실행한 뒤 PR을 열어 CI 완료 후 5분 대기/리뷰 확인/머지한다.

**후속**:
- 이 PR merge 후 T-050 destructive confirmation flow 통합으로 이어간다.

## 2026-05-29 07:20 (PR #69~#75 post-merge 리뷰 audit/fixup)

**작업**: 사용자 지시에 따라 PR #69부터 최신 PR #75까지 conversation/review/latestReview/reviewThreads를 재확인하고, formal review에서 바로 반영 가능한 항목을 코드와 문서로 보강했다.

**반영**:
- `kor-travel-geo-ui/package-lock.json`의 `maplibre-vworld` resolved URL을 `git+https`로 맞췄다.
- `AsyncAddressClient.list_consistency_case_samples()`가 표본 결과가 있을 때는 report 존재 확인 쿼리를 추가 실행하지 않도록 줄였다.
- `SizeProgressProbe`가 directory size sample을 interval 안에서 캐시해 backup/restore hot path의 반복 `rglob/stat` 부하를 줄였다.
- `mv_refresh`의 load-batch ERROR gate를 swap 이전으로 옮기고, release hook의 post-swap gate raise와 `mv_geocode_target` 중복 count를 제거했다.
- T-053 표본/전수 범위, callback retry 멱등성, helper MV raw refresh 금지, T-055 helper sizing, T-050 release ledger transaction 경계를 문서화했다.
- 상세 리뷰별 반영/보류 표는 `docs/postmerge-review-fixups-pr69-pr75.md`에 정리했다.

**검증 예정**:
- backend 전체 gate와 frontend gate를 실행한 뒤 PR을 열어 CI 완료 후 5분 대기/리뷰 확인/머지한다.

**후속**:
- 이 PR merge 후 T-050 `ops.table_stats_snapshots` 주기 capture로 이어간다.

## 2026-05-29 06:27 (T-050 운영 hardening 4차 — snapshot/release hook)

**작업**: full-load/MV refresh/restore 성공 지점을 `ops.dataset_snapshots`와 `ops.serving_releases`에 자동 연결하는 hook을 추가했다.

**반영**:
- `mv_refresh` 성공 후 active serving release와 released dataset snapshot을 기록한다.
- full-load batch에서 온 refresh는 root `source_set`과 최신 consistency gate를 연결하고, 단독 refresh는 `manual_rebuild` release로 기록한다.
- 새 active release 생성 전 기존 active release는 `superseded`로 전환한다.
- restore 성공 후에는 hot-swap 전 단계의 `validated` snapshot과 `pending` restore release 후보를 만들고 restore artifact manifest에 `snapshot_id`/`release_id`를 연결한다.
- `docs/t050-ops-hardening.md`, backend/frontend 문서, resume/tasks/CHANGELOG를 갱신했다.
- 사용자 최신 지시에 따라 이 PR merge 후 다음 작업은 PR #69부터 최신 PR까지 review audit/fixup을 먼저 진행한다.

**검증**:
- 대상 `ruff check src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/api/app.py src/kortravelgeo/infra/backup.py src/kortravelgeo/cli/main.py tests/unit/test_ops_metadata.py`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/api/app.py src/kortravelgeo/infra/backup.py src/kortravelgeo/cli/main.py`
- 대상 `pytest tests/unit/test_backup_restore.py tests/unit/test_ops_metadata.py tests/unit/test_infra_repo_sql.py -q`
- `lint-imports`

**후속**:
- T-050 4차 PR merge 후 PR #69부터 최신 PR까지 review audit/fixup을 진행한다.
- 이후 `ops.table_stats_snapshots` 주기 capture로 이어간다.

## 2026-05-29 05:17 (T-050 운영 hardening 3차 — backup/restore sub-progress)

**작업**: backup/restore의 대용량 단계가 멈춘 것처럼 보이지 않도록 file/archive size 기반 sub-progress를 추가했다.

**반영**:
- `SizeProgressProbe`와 byte formatter를 추가해 진행 중인 파일 또는 디렉터리 크기를 주기적으로 샘플링한다.
- `pg_dump` 실행 중 dump 디렉터리 크기를 `log_tail`에 남기고, dump checksum 생성 구간을 `0.65~0.70` progress로 분리했다.
- `tar.zst` archive 생성 전에 입력 크기를 계산하고, `.part` archive 파일 성장량을 보조 진행률로 기록한다.
- archive SHA256 계산 중 읽은 byte/전체 byte를 기록한다.
- restore extract 구간에서 extract 디렉터리 성장량을 archive 크기와 함께 기록하고, `pg_restore` 시작 메시지에는 dump 디렉터리 총량을 포함한다.
- `docs/t050-ops-hardening.md`, `docs/t046-db-backup-restore.md`, resume/tasks/CHANGELOG를 갱신했다.

**검증**:
- 대상 `ruff check src/kortravelgeo/infra/backup.py tests/unit/test_backup_restore.py`
- 대상 `pytest tests/unit/test_backup_restore.py -q`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/backup.py`

**후속**:
- PR merge 후 T-050 4차로 full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성을 진행한다.

## 2026-05-29 04:29 (T-050 운영 hardening 2차 — backup/restore callback)

**작업**: T-046 backup/restore callback을 1회 단순 전송에서 HMAC 서명, retry/backoff, replay 판별 가능한 전송 계약으로 보강했다.

**반영**:
- `KTG_BACKUP_CALLBACK_MAX_ATTEMPTS`, `KTG_BACKUP_CALLBACK_BACKOFF_MS`, `KTG_BACKUP_CALLBACK_SECRET` 설정을 추가했다.
- callback payload는 `callback_id`, `timestamp`, `attempt`, `max_attempts`를 포함하고, compact JSON byte를 기준으로 HMAC-SHA256 서명한다.
- header는 `x-kor-travel-geo-event`, `x-kor-travel-geo-callback-id`, `x-kor-travel-geo-timestamp`, `x-kor-travel-geo-signature`를 보낸다.
- 각 retry attempt마다 새 `callback_id`를 발급하고, delivery 결과를 `ops.artifacts.callback_state`와 `manifest.callback_delivery`에 기록한다.
- callback 실패는 backup/restore artifact 자체의 성공/실패를 뒤집지 않는다.
- `docs/t050-ops-hardening.md`와 `docs/t046-db-backup-restore.md`에 실제 payload/header/운영 기록 방식을 갱신했다.

**검증**:
- 대상 `ruff check`
- 대상 `pytest tests/unit/test_backup_restore.py tests/unit/test_settings.py -q`
- 대상 `mypy --no-incremental src/kortravelgeo/infra/backup.py src/kortravelgeo/settings.py`

**후속**:
- PR merge 후 T-050 3차로 backup/restore file/archive size 기반 sub-progress를 진행한다.

## 2026-05-29 03:35 (T-050 운영 hardening 1차 — upload set cleanup)

**작업**: T-050을 여러 PR로 나누기로 하고, 첫 단위로 upload set cleanup TTL과 실행 중 job 참조 보호를 구현했다.

**반영**:
- `kortravelgeo.infra.uploads.cleanup_upload_sets()`를 추가했다. `loader_data_dir/uploads/upload_*`를 스캔하고 TTL이 지난 upload set을 삭제한다.
- `load_jobs.state IN ('queued','running')` payload에서 `upload_set_id` 또는 upload set 경로가 발견되면 삭제하지 않는다.
- manifest가 깨졌거나 없는 `upload_*` 디렉터리는 orphan으로 보되 TTL과 active grace가 모두 지난 경우에만 삭제한다.
- `AsyncAddressClient.cleanup_upload_sets()`와 `ktgctl uploads cleanup` CLI를 추가했다.
- 기본 설정 `KTG_UPLOAD_SET_TTL_DAYS=30`, `KTG_UPLOAD_SET_ACTIVE_GRACE_MINUTES=360`을 추가했다.
- `docs/t050-ops-hardening.md`에 T-050 전체 분할 순서와 1차 cleanup 운영 규칙을 정리했다.

**검증 예정**:
- `tests/unit/test_source_set_plan.py`, `tests/unit/test_settings.py`, `tests/unit/test_infra_repo_sql.py` targeted test 후 전체 backend gate를 실행한다.

**후속**:
- PR merge 후 T-050 2차로 backup/restore callback HMAC, retry/backoff, replay protection을 진행한다.

## 2026-05-29 02:30 (T-061 Q3 fuzzy slim text-search 구조)

**작업**: `mv_geocode_target`에서 재생성 가능한 read-only helper MV `mv_geocode_text_search`를 추가하고, Q3 fuzzy geocode와 Q4 broad search fallback 후보 추출에 연결했다.

**반영**:
- `alembic/versions/0013_t061_text_search_mv.py`와 `TEXT_SEARCH_MV_SQL`을 추가했다.
- `GeocodeRepository.fuzzy_roads()`는 helper MV에서 candidate를 먼저 뽑고 `bd_mgt_sn`으로 `mv_geocode_target`에 join한다.
- `SearchRepository.search()`는 Q4 exact preflight를 기존 target index 경로로 유지하고, exact가 없을 때 broad fallback만 helper MV를 사용한다.
- shadow swap은 `mv_geocode_target_next`와 `mv_geocode_text_search_next`를 함께 만들고 같은 rename window에서 교체한다.
- backup materialized-view 제외 옵션은 `mv_geocode_target`과 `mv_geocode_text_search` data를 함께 제외한다.
- `scripts/benchmark_query_performance.py`와 `scripts/benchmark_mv_refresh.py`가 helper MV row/size와 refresh/swap cost를 기록하도록 보강했다.

**실측**:
- T-057 corpus 기준 Q3 fuzzy c64 p95는 359.25ms → 227.57ms, `sig_cd` hint는 193.36ms → 182.27ms, wide는 255.36ms → 200.69ms.
- helper MV는 6,416,637행, heap 854MiB, index 1,572MiB, total 2,426MiB.
- helper-only rebuild는 채택 DDL 기준 82.77초.
- helper 포함 shadow swap은 497.54초, helper text-search build/index phase는 약 85.37초, rename/drop/index rename lock window는 약 1.06초.
- 실제 DB semantic parity test는 `tests/integration/test_optional_real_postgres_text_search.py`로 통과했다.

**검증**:
- targeted unit/ruff, 실제 DB parity test, T-057 corpus before/after benchmark, generated `search_fuzzy` benchmark, helper 포함 shadow swap benchmark.

**후속**:
- T-061 PR merge 후 사용자 최신 순서에 따라 T-050 운영 hardening을 진행한다.

## 2026-05-28 23:58 (T-053 Admin UI C1~C10 상세 분석/수동 판정 콘솔)

**작업**: 사용자 재확인 의도를 먼저 문서에 구체화한 뒤 C1~C10 sample 분석/판정용 backend API와 admin UI를 구현했다.

**반영**:
- `docs/t053-admin-ui-ops-statistics.md`에 C1~C10 기준 설명, 지도 overlay, table 비교, 단건/bulk 승인·거절·보류, recheck, v1/v2 API 경계를 정리했다.
- `ops.consistency_case_samples` DDL/Alembic을 추가하고 `run_all_cases()`가 report JSONB 요약과 sample row를 함께 저장하도록 바꿨다. 기존 report는 sample 조회 시 lazy backfill한다.
- `/v1/admin/consistency/case-definitions`, sample list/summary, 단건·bulk decision, recheck, CSV export API와 `AsyncAddressClient` 메서드를 추가했다.
- `/admin/consistency/[report_id]` 상세 화면을 추가하고 TanStack Query, TanStack Table, Zustand, `maplibre-vworld-js` wrapper 기반 지도 preview를 연결했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입을 갱신했고, Zustand/query helper 테스트를 추가했다.

**검증**:
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`
- `scripts/export_openapi.py --check --output openapi.json`
- `kor-travel-geo-ui`: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build`

**후속**:
- T-053 PR merge 후 사용자 최신 지시에 따라 T-061 Q3 fuzzy slim text-search 구조를 먼저 진행한다.

## 2026-05-28 22:39 (PR #69 리뷰 반영 — v2 candidate distance/precision 보강)

**작업**: PR #69 formal review의 provider 비교 코멘트를 T-052 PR에 바로 반영했다.

**반영**:
- `CandidateV2.distance_m`을 first-class 필드로 추가하고 reverse 변환에서 `metadata.distance_m`와 함께 채운다.
- reverse v2 `confidence`를 고정 `1.0`에서 `1 - distance_m / radius_m` 기반 근접도 점수로 바꿨다.
- `CandidateV2.point_precision` enum을 추가하고, 현재 채움 범위와 후속 `pt_source` 연결 필요성을 API reference에 명시했다.
- `V2Source`가 현재 구현 가능한 `local`/`vworld`/`juso`/`cache`만 허용하며 Kakao/Naver/Google live adapter는 별도 task/ADR에서 확장한다는 문구를 보강했다.

**검증**:
- PR #69 commit 갱신 전 targeted/unit/OpenAPI/frontend type 검증을 다시 수행한다.

## 2026-05-28 20:43 (T-052 API v1/v2 분리와 AI-friendly 문서화)

**작업**: vworld 호환 v1 표면을 유지하면서 신규 v2 candidate schema와 API reference를 추가했다.

**반영**:
- 사용자 재확인에 따라 v2는 Kakao/Naver/Google/VWorld 직접 wrapper가 아니라 각 API 스타일의 장점을 참고한 `kor-travel-geo` 자체 API로 정리했다.
- `src/kortravelgeo/dto/v2.py`, `core/v2.py`, `api/routers/v2.py`를 추가하고 `/v2/geocode`, `/v2/reverse`, `/v2/search`를 연결했다.
- `AsyncAddressClient.geocode_v2()`, `reverse_v2()`, `search_v2()`를 추가했다.
- `docs/api-reference/`와 LLM 요약 문서를 추가했고, `openapi.json` 및 `kor-travel-geo-ui` 생성 타입을 갱신했다.
- v1 외부 fallback은 기존 ADR-019의 vworld/juso만 유지하고, Kakao/Naver/Google 호출과 새 API key는 추가하지 않았다.

**후속**:
- T-052 PR merge 후 T-053 코딩 전에 먼저 C1~C10 분석/판별/승인 UI 요구를 문서에 상세화한다.
- T-053 완료 뒤에는 사용자 최신 지시에 따라 T-061 Q3 fuzzy slim text-search를 먼저 진행한다.

## 2026-05-28 19:48 (T-052/T-053 선행 정리 — PR #67 리뷰 후속)

**작업**: PR #67 리뷰 후속과 사용자 확인사항을 T-052/T-053 본작업 전 선행 정리로 반영했다.

**반영**:
- 사용자 확인에 따라 T-056 RFC의 "조합/분리"는 주소 문자열 parse/compose가 아니라 코드 식별자의 조합·분해·정규화 의도였음을 문서화했다.
- 엄밀하지 않은 `clean-room` 표현을 "공개 주소 코드 규칙 기반 독립 구현, GPL 원본 코드 미복사"로 바로잡았다.
- Juso 검색 결과에 `admCd`/`rnMgtSn` 등 좌표 API 필수 코드가 없으면 coord API를 호출하지 않고 graceful `None`으로 끝나는 회귀 테스트를 추가했다.

**후속**:
- 이 선행 정리 PR을 머지한 뒤 T-052 v1/v2 API/provider 작업을 시작한다.

## 2026-05-28 19:20 (T-056 `python-legacy-address-base` Address 코드 helper 정리)

**작업**: `~/dev/python-legacy-address-base`의 실제 Address 표면을 확인하고, 본 저장소에서 필요한 주소 코드 helper를 clean-room으로 구현했다.

**확인**:
- `/home/digitie/dev/python-legacy-address-base`는 Git checkout이 아니었다. `.git`이 없어 `git rev-parse HEAD`는 실패했다.
- package license는 `GPL-3.0-or-later`였고, 본 저장소는 MIT이므로 원본 코드를 복사하지 않았다.
- 실제 Address 표면은 예상했던 `legacy.address_base.address.*` package가 아니라 `src/legacy/address-base/addresses.py` 단일 파일이었다.

**반영**:
- `src/kortravelgeo/core/address/codes.py`에 `SigunguCode`, `LegalDongCode`, `RoadNameCode`, `RoadNameAddressCode`, `AddressCodeSet`과 mapping/정규화 helper를 추가했다.
- Juso fallback 좌표 API 호출은 `AddressCodeSet`으로 `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`를 정규화한 뒤 요청한다.
- `docs/t056-legacy-address-base-address-merge.md`, ADR-035, 백엔드/아키텍처 문서, resume/tasks/CHANGELOG를 갱신했다.

**후속**:
- 사용자 최신 지시에 따라 T-056 이후에는 T-052/T-053 선행 정리 → T-052 → T-053 순서로 진행한다.

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

## 2026-05-28 18:26 (T-044 `maplibre-vworld-js` 0.1.0 문서-only 재확인)

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 0.1.0 기준으로 upstream code/API를 재확인하고, upstream 코드는 직접 수정하지 않은 채 이 저장소 문서에만 T-044 보완점을 반영했다.

**확인**:
- GitHub tag `v0.1.0`은 commit `8559bf4f8d5a32011a51669552bb7e1aedd42cfb`이고, commit message는 `chore: release v0.1.0`이다.
- GitHub release는 없었고, npm registry에서도 `maplibre-vworld@0.1.0`과 `maplibre-vworld-js@0.1.0`은 `E404`였다.
- package name/version은 `maplibre-vworld`/`0.1.0`이며, `dist/`, `exports`, `types`, `style.css`, `VWorldMap`, marker/layer primitive, VWorld helper가 포함되어 있었다.
- 현재 `kor-travel-geo-ui` dependency는 여전히 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`에 고정되어 있고, 이번 작업에서는 dependency를 갱신하지 않았다.

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
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
- 전체 pytest 결과는 216 passed, 6 skipped, 3 warnings다.

## 2026-05-28 17:42 (T-062 PR #53~#64 리뷰 audit/fixup)

**작업**: T-057 merge 직후 사용자 지시에 따라 PR #53부터 #64까지 아직 별도 audit하지 않은 PR 리뷰를 모두 재확인했다.

**확인**:
- 각 PR의 conversation comment, formal review, inline review thread, GraphQL `reviewThreads`를 확인했다.
- 모든 PR의 unresolved review thread는 0건이었다.

**직접 반영**:
- PR #53: search exact preflight의 Python/SQL 정규화 규칙을 문서화하고, shadow MV index 문서 오타를 수정했다. exact preflight가 없는 broad trigram fallback을 계속 측정하도록 `search_fuzzy` benchmark case와 REST 변환 case를 추가했다.
- PR #55: `pg_stat_statements` 조회/reset을 `x_extension` schema-qualified SQL로 고정했다.
- PR #59: reverse 좌표 bounds validation을 `PydanticCustomError("kor_travel_geo.coordinate_bounds", ...)` 기반 structured mapping으로 바꿔 문자열 전체 매칭 의존을 제거했다.
- PR #62: REST admission repeat 문서에 c64 tail 중심 비교 이유를 추가했다.
- PR #63: `tar.zst` SHA256 checksum 시간을 측정하고, backup envelope와 `tar.zst`의 의미를 단일 artifact 포장/checksum 단순화 중심으로 보강했다.

**후속**:
- 다음 작업은 사용자 추가 지시에 따라 T-044를 `maplibre-vworld-js` 0.1.0 기준으로 다시 확인하는 문서-only PR이다. upstream 코드는 직접 수정하지 않고 `kor-travel-geo` 문서에 보완점을 남긴다.

**검증**:
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `pytest -q`, `git diff --check`, `codegraph sync`를 통과했다.
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
- `KTG_API_MAX_CONCURRENCY`가 설정된 경우에만 주소 API 요청을 process-local semaphore로 제한한다. 기본값은 unset이라 기존 동작은 유지된다.
- `KTG_API_ADMISSION_TIMEOUT_MS`는 semaphore 대기 timeout이다. timeout 시 HTTP 429 + `E0200`을 반환한다.
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
- uvicorn 단일 process, `KTG_PG_POOL_SIZE=64`, `KTG_PG_MAX_OVERFLOW=0`.
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
- `KTG_PG_STATEMENT_TIMEOUT_MS=1800000`으로 재실행한 결과, `CONCURRENTLY` refresh는 133.28초, shadow `swap`은 352.85초였다.
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
- `kor-travel-geo-t027-db-1` 컨테이너를 `shared_preload_libraries=pg_stat_statements` 설정으로 재생성했다. bind mount `/home/digitie/kor-travel-geo-data/pgdata`는 유지했다.
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
- 당시 인프라 설정 파일, fresh schema SQL, Alembic `0011_t047_pg_stat_statements`에 `pg_stat_statements` preload/extension 경로를 추가했다.

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
- `src/kortravelgeo/infra/search_repo.py`: search repository가 공백 제거 query로 `rn_nrm`/`buld_nm_nrm` exact preflight를 먼저 실행하고, exact 결과가 있으면 그 결과 집합만 반환한다. exact 결과가 없을 때만 기존 broad trigram search로 fallback한다.
- `src/kortravelgeo/infra/sql.py`, `alembic/versions/0010_t047_search_exact_indexes.py`: `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`를 추가했다.
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

**작업**: 사용자 RFC(restore hot-swap, vworld/kakao/naver multi-provider + v1/v2 API + AI-friendly 문서, Web UI 통계/유지보수/관리/튜닝 + C1~C10 분석 UI/CSV, CLI 동시 실행 보호, 한국 IP만 허용, N150/Odroid 환경 검토, `python-legacy-address-base` Address 부분 병합 + 외부 라이브러리 삭제, 행정구역 hint 검색 가속)를 task 8건과 ADR 4건으로 문서화했다. 코드는 작성하지 않았다.

**반영 상세**:
- `docs/tasks.md`에 T-052~T-059 신규 항목 추가 + 우선순위 재정렬. 운영 안전성(T-056, T-058, T-059, T-054)을 먼저, 기능 보강(T-057, T-053, T-052) 다음, 운영 환경 비교(T-055)는 하드웨어 도착 후.
- `docs/decisions.md`에 ADR-035(`python-legacy-address-base` Address 흡수 + 외부 라이브러리 삭제), ADR-036(restore hot-swap `ALTER DATABASE RENAME` 기반), ADR-037(외부 IP 한국만 허용), ADR-038(API v1/v2 분리 + 외부 provider 흡수 + AI-friendly 문서)을 추가했다.
- 각 task별 design doc 8건 신규: `docs/t052-api-providers-v1-v2.md`, `docs/t053-admin-ui-ops-statistics.md`, `docs/t054-korea-only-geoip.md`, `docs/t055-deployment-n150-odroid.md`, `docs/t056-legacy-address-base-address-merge.md`, `docs/t057-region-hint-search.md`, `docs/t058-restore-hot-swap.md`, `docs/t059-concurrent-job-protection.md`.
- 각 design doc은 "상태/목적/현황/결정/구현 sketch/검증/남은 위험/관련 ADR-Task" 구조로 작성해 사람과 AI agent 모두가 cold start로 진입할 수 있게 했다.
- `CHANGELOG.md`/`docs/resume.md`에 같은 내용을 동기화했다.

**현황 확인 결과 (사용자가 "반영되어 있으면 스킵" 조건을 건 항목)**:
- restore hot-swap: 현 시점 `docs/t046-db-backup-restore.md`/ADR-030은 "기본 새 빈 DB + `replace_current` 위험 경로"만 명문화. hot-swap 절차 자체는 미반영 → **스킵하지 않고 T-058로 등록**.
- CLI 중복 실행 보호: in-process semaphore + `load_jobs` advisory lock + `TL_SPBD_BULD` staging lock + `ops.serving_releases` active partial unique는 이미 있음. cross-process 표준화는 일부만 적용 → **T-059로 인벤토리 + 표준화 등록**.

**다음 작업**: 우선순위에 따라 T-056부터 또는 T-027 베이스라인 활용 가능한 T-057/T-059부터 구현 PR을 만든다. 본 PR은 문서/계획만 포함하므로 코드/DDL은 후속 PR에서 처리한다.

**검증**:
- `git diff --check` 통과 예정(문서 전용).
- `pytest -q`, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`는 본 PR이 코드 변경이 없으므로 회귀 차원에서 baseline만 통과 확인.

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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=... /home/digitie/dev/kor-travel-geo/.venv/bin/python -m pytest tests/unit/test_query_performance_benchmark.py -q` 실행 결과 6건 통과.
- `ps` 확인 시 benchmark/pytest/ruff/gh/당시 인프라 명령 장기 실행 프로세스는 없었다.

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
- `git diff --check`, `.venv/bin/ruff check .`, `.venv/bin/mypy src/kortravelgeo`, `.venv/bin/lint-imports`, `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`를 실행했다. 결과는 `191 passed, 6 skipped`다.

**후속**:
- 이후 모든 새 작업은 해당 에이전트 고정 worktree에서 branch만 새로 따고, branch 전환 뒤 `codegraph sync`로 인덱스를 맞춘다.

## 2026-05-27 (PR #34~#47 리뷰 코멘트 audit/fixup)

**작업**: 사용자 지시에 따라 PR #34부터 #47까지 GitHub conversation comment, formal review body, inline review thread, GraphQL `reviewThreads`를 다시 확인했다. PR #34~#43에는 post-merge 리뷰 코멘트가 있었고, PR #44는 Windows Playwright 확인 메모, PR #45~#47은 확인 시점 기준 신규 코멘트가 없었다. unresolved current review thread는 0개였다.

**반영 상세**:
- `docs/postmerge-review-fixups-pr34-latest.md`를 추가해 PR별 코멘트, 이번 반영, 후속 이관 항목, 재사용할 GraphQL query template을 기록했다.
- PR #35 M3 반영: `LoadJobStatus.source_set`, `ConsistencyReport.source_set`, 내부 row protocol, `run_all_cases(source_set=...)` 타입을 `dict[str, Any]`로 넓혀 `SourceSetPlan`의 nested JSON을 보존한다. `openapi.json`, `kor-travel-geo-ui/types/api.gen.ts`, `kor-travel-geo-ui/lib/api.ts`도 함께 갱신했다.
- PR #43 M5 반영: `ops.audit_events.job_id` FK를 `ON DELETE SET NULL`에서 `ON DELETE NO ACTION`으로 변경했다. fresh DDL과 Alembic `0008_pr34_review_followups`를 추가해 감사 이벤트와 job 연결이 조용히 끊기지 않게 했다.
- PR #38/PR #42 후속 반영: `maplibre-vworld-js` upstream `main` 최신 SHA `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`를 확인해 `kor-travel-geo-ui` dependency/lockfile과 문서를 갱신하고, Windows `npm` 오사용을 막는 `scripts/frontend_check.sh`를 추가했다.

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
- `ktgctl load sppn-makarea`, API queue kind `sppn_makarea_load`, source set optional `sppn_makarea` child를 연결했다.
- `core.sppn`에 국가지점번호 parser와 EPSG:5179 좌표 formatter를 추가했다.
- geocode는 국가지점번호 문자열을 좌표로 변환한 뒤 `ST_Covers(tl_sppn_makarea.geom, point)`로 검증하고, `x_extension.national_point_number`와 `x_extension.sppn_makarea`를 반환한다.
- reverse geocode는 도로명/지번 후보가 없어도 polygon 포함 여부가 있으면 `status="OK"`와 `x_extension.sppn_makarea`를 반환한다.
- 실제 적재 중 `REPLACE(col, chr(0), '')`가 PostgreSQL에서 `null character not permitted`를 유발하는 문제를 발견해 `NULLIF(BTRIM(col::text), '')`로 수정했다.

**검증**:
- Targeted unit/contract pytest 48건을 통과했다.
- Docker PostGIS `kor_travel_geo_t042_sppn`에 세종 `구역의 도형/구역의도형_전체분_세종특별자치시.zip`을 실제 적재했다. 결과는 146행, 146 distinct key, source_yyyymm `202605`, 전체 valid MultiPolygon이었다.
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
- `KTG_BACKUP_ALLOWED_DIRS`, 임시 디렉터리, 병렬 jobs, 압축 level, TTL, callback allowlist, download token secret 설정을 추가했다.
- `infra.backup`에서 allowlist/symlink escape 검증, `pg_dump -Fd --jobs`, `.part` 기반 `tar.zst` archive, manifest/checksum, `pg_restore -Fd --jobs`, target DB empty/current DB guard, callback, HMAC download token을 구현했다.
- `pg_dump`/`pg_restore` password는 argv에 넣지 않고 `PGPASSWORD` 환경변수로 넘기도록 해 process argument와 log 노출을 줄였다.
- `ops.artifacts` helper를 확장해 `db_backup` artifact metadata를 저장하고, backup/restore 작업을 기존 영속 `load_jobs` 큐에 연결했다.
- `/v1/admin/backups`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events`, `ktgctl backup/restore`, `/admin/backups` UI를 추가했다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입/schema를 갱신했다.

**검증**:
- Backend targeted pytest 32건, `ruff`, `mypy`를 통과했다.
- Frontend `eslint`, `tsc --noEmit`, `vitest`, `next build`를 통과했다.
- Playwright 검증은 사용자 지시에 따라 Windows Node에서 수행했다. `/admin/backups` 화면에서 백업 시작, 복원 시작, 다운로드 링크 노출을 API mock으로 확인했고 screenshot은 `C:\Users\digit\AppData\Local\Temp\t046-admin-backups-windows.png`에 저장했다.
- Docker PostGIS에서 대구광역시 부분 원천을 실제 적재한 뒤 `/tmp/kortravel-t046/backups/t046_daegu_backup.tar.zst` 백업과 새 DB 복원을 수행했다. 원본/복원 row count는 `tl_juso_text=228,875`, `tl_juso_parcel_link=26,594`, `tl_locsum_entrc=228,610`, `tl_navi_buld_centroid=291,281`, `mv_geocode_target=228,875`로 일치했고, `대구광역시 중구 공평로 88` geocode/reverse smoke test가 모두 `OK`였다.

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
- `ktgctl load full-set`은 자동 발견 후 기준월이 섞이면 정확한 확인 문구 없이는 plan을 만들지 않는다.
- `/admin/load`는 다중 파일 선택과 DND, XHR upload progress, upload set cancel, source set review, 기준월 mismatch modal, 적재 진행률과 root job cancel을 제공한다.

**검증**:
- `tests/unit/test_source_set_plan.py`에서 source 탐지, optional 제외, 같은 기준월 plan, 혼합 기준월 확인, upload 저장/취소, 크기 제한 실패를 검증했다.
- `kor-travel-geo-ui/tests/unit/load-workflow.test.ts`에서 상태 전이, 확인 token 생성, 진행률 계산을 검증했다.
- 중간 검증으로 backend targeted pytest, backend ruff/mypy, frontend lint/type-check/load-workflow test를 통과했다. 최종 PR 검증에서는 전체 backend/frontend gate와 OpenAPI drift 검사를 다시 수행한다.

**후속**:
- C10 정합성 severity 조정은 `source_set.mixed_yyyymm_acknowledged`를 더 읽도록 별도 보강한다.
- `ops.dataset_snapshots`에 source set 확정 정보를 자동 연결하는 일은 T-027/T-047 full-load gate 보강 때 이어간다.
- 다음 작업은 T-046 백업/복원 구현이다.

## 2026-05-27 (T-049 — 운영 메타데이터·감사·릴리스 스키마 구현)

**작업**: ADR-033의 `ops` 운영 메타데이터 설계를 실제 DDL, Alembic migration, DTO/API/client, 관리 UI, 테스트로 구현했다.

**반영 상세**:
- `ops.audit_events`, `ops.dataset_snapshots`, `ops.serving_releases`, `ops.artifacts`, `ops.maintenance_windows`, `ops.table_stats_snapshots`를 `sql/ddl/001_schema.sql`과 `src/kortravelgeo/infra/sql.py`에 추가하고, 기존 DB upgrade용 Alembic `0006_t049_ops_metadata_schema.py`를 작성했다.
- `ops.audit_events`는 append-only trigger로 UPDATE/DELETE를 막고, `ops.serving_releases`는 `state='active'` partial unique index로 active release 한 건만 허용한다.
- `kortravelgeo.core.redaction`을 추가해 API key, DSN, password, token, callback secret, 주소 원문을 audit payload에 평문 저장하지 않도록 했다.
- `AdminRepository`, `AsyncAddressClient`, `/v1/admin/ops/*` API를 추가했다. audit event/snapshot/release/artifact/maintenance/table stats 조회, rollback plan, maintenance window 생성/종료, table stats snapshot capture를 제공한다.
- `kor-travel-geo-ui`에 `/admin/ops` 화면을 추가했다. release, snapshot, artifact, audit event, maintenance window, table stats snapshot을 조회하고 maintenance window 생성과 stats capture를 실행할 수 있다.
- OpenAPI와 frontend generated type/schema 목록을 갱신했다.

**검증**:
- `.venv/bin/python -m pytest -q` → 155 passed, 5 skipped.
- `.venv/bin/python -m ruff check .` 통과.
- `.venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` 통과.
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
- `kor-travel-geo-ui/lib/vworld.ts`의 `redactVWorldTileUrl` alias 수명 주석과 redaction test의 API key 누설 방지 assert를 추가했다.
- `kor-travel-geo-ui/README.md`에 WSL ext4에서는 Linux Node/npm을 사용하라는 검증 경고를 추가했다.
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
- `.venv/bin/python -m mypy src/kortravelgeo` 통과.
- `.venv/bin/lint-imports` 통과.
- 프론트엔드 로컬 검증은 Linux Node가 없고 Windows `npm`만 잡혀 UNC 경로 오류가 나므로 실행하지 않았다. GitHub Actions frontend job에서 확인한다.

## 2026-05-27 (문서 정합성 재검토와 task 순서 재정렬)

**작업**: 사용자 지시에 따라 `main` 최신 문서와 실제 CLI/최근 ADR 사이의 불일치를 전체적으로 재검토하고 문서에 반영했다. 코드는 작성하지 않았다.

**반영 상세**:
- README/SKILL의 현재 상태와 quick start를 갱신했다. `load all-sidos` 예시는 실제 CLI 옵션(`--juso`, `--jibun`, `--locsum`, `--navi`, `--shp-root`, `--yyyymm`) 기준으로 바꿨다.
- 현재형 문서의 브랜치 표현을 `master`에서 `main`으로 바로잡았다. 단, `master table` 같은 DB 도메인 용어와 과거 작업 일지의 역사적 표현은 유지했다.
- `SKILL.md`의 “백엔드만 다룬다” 설명을 같은 저장소 안의 별도 Node.js 패키지 `kor-travel-geo-ui`를 함께 관리한다는 설명으로 정리했다.
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

**작업**: 사용자 지시에 따라 `maplibre-vworld-js` 사용 시 항상 최신 버전을 확인하고, 이 라이브러리의 특화 기능은 upstream `vworld.js`가 아니라 `kor-travel-geo-ui` 쪽에서 구현한다는 원칙을 문서와 dependency에 반영했다.

**반영 상세**:
- `git ls-remote https://github.com/digitie/maplibre-vworld-js.git refs/heads/main`으로 upstream `main` 최신 commit `1a28b1099ab6c9c03e892e469974aee8c07deda1`을 확인했다.
- `kor-travel-geo-ui/package.json`과 `package-lock.json`의 `maplibre-vworld` dependency를 최신 확인 SHA로 갱신했다. CI에서 SSH key 없이 설치되도록 dependency와 lockfile `resolved`는 `git+https` 형식을 유지한다.
- ADR-032를 추가했다. VWorld layer/style, marker/popup/cluster primitive, tile error redaction, package export/type/CSS처럼 범용 기능은 `digitie/maplibre-vworld-js`에서 보강하고, geocode/reverse 입력 연결, API 응답 overlay, 정합성/성능/적재 상태 표시, 이 프로젝트 fallback UX는 `kor-travel-geo-ui` domain wrapper에서 구현한다.
- `README.md`, `docs/architecture.md`, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/tasks.md`, `docs/resume.md`, `docs/t036-maplibre-vworld-sync.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- `maplibre-vworld` dependency를 건드리는 PR은 최신 `main` 또는 stable release 확인 결과를 남긴다.
- upstream에 보낼 것은 범용 VWorld/MapLibre 기능이며, 주소 지오코딩 디버그/관리 UI에만 의미가 있는 기능은 이 저장소에서 구현한다.
- SHA 갱신 후에는 `kor-travel-geo-ui`에서 `npm ci`, lint, type-check, test, build를 재검증한다.

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
- 구현 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB `kor_travel_geo_t046_daegu` → `kor_travel_geo_t046_daegu_restore` backup/restore로 먼저 수행한다.

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
- ADR-028을 추가했다. 부족한 click callback, marker 제어, `flyToOptions`, tile error hook/redaction, key 미설정 fallback, SSR-safe 사용법, 타입/패키징 문제는 `kor-travel-geo`에서 우회하지 않고 `digitie/maplibre-vworld-js`를 직접 수정한다.
- `docs/frontend-package.md`, `docs/architecture.md`, `docs/t036-maplibre-vworld-sync.md`, `docs/resume.md`, `CHANGELOG.md`를 같은 방향으로 갱신했다.

**결정**:
- T-044는 두 저장소 작업으로 본다. 필요한 upstream 보강은 `maplibre-vworld-js` PR/commit으로 남기고, 그 검증된 SHA를 `kor-travel-geo-ui` dependency로 소비한다.
- 완료 조건에는 upstream test/build와 `kor-travel-geo-ui`의 `npm ci`, lint, type-check, test, build 검증을 포함한다.

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
- `src/kortravelgeo/loaders/shp/polygons_loader.py`에서 `TL_SPBD_BULD`만 `_ktg_stage_spbd_buld_polygon` staging table로 분기한다.
- staging 생성은 `accessMode="overwrite"`, `PG_USE_COPY=YES`, `SHAPE_ENCODING=CP949`, 기존 `plan.sql_statement` projection을 함께 사용한다.
- 운영 테이블 insert는 `SET LOCAL search_path = public, x_extension` 후 `INSERT ... SELECT`로 수행하고, `ST_Multi(geom)::geometry(MultiPolygon, 5179)`와 문자열 trim/NULL 정규화, 건물번호 integer cast를 명시했다.
- staging table은 시작 전과 종료 `finally`에서 모두 drop한다.
- `docs/t037-shp-geometry-tuning.md`를 추가하고 `docs/backend-package.md`, `docs/t034-shp-append-tuning.md`, `docs/t027-fullload-plan.md`, `docs/tasks.md`, `docs/resume.md`를 갱신했다.

**실제 파일 검증**:
- 세종 단일 `TL_SPBD_BULD`: 기존 append 38.36초 → projection staging 18.59초, 55,819행, source 추적 컬럼 전량 채움, staging table 없음.
- 경기도 raw staging은 원본 DBF 전체 속성을 복사해 22분 58.46초 동안 끝나지 않아 `pg_terminate_backend()`로 중단했다. 중단 지점은 GDAL feature 617,214 부근이었다.
- 경기도 projection staging: 1,649,975행, 40분 17.15초, source 추적 컬럼 전량 채움, staging table 없음.
- 세종 public CLI `ktgctl load shp ... --mode full --yyyymm 202604`: 9개 레이어 적재 성공, 1분 19.54초, `tl_spbd_buld_polygon=55,819`, `tl_sprd_intrvl=100,009`, `tl_sprd_rw=7,429`.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q` → 17 passed.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo/loaders/shp/polygons_loader.py` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없거나 반영이 끝나면 main에 merge하고 T-027 최종 실 데이터 클린 적재 검증으로 진행한다.

## 2026-05-26 (T-041 — 상세주소 동 도형/구역 추가 레이어 검토)

**작업**: PR #30 merge 이후 `codex/t041-extra-shape-layer-review` 브랜치에서 `건물군 내 상세주소 동 도형`과 `구역의 도형`을 실제 세종/경남 파일로 전자지도와 비교했다.

**반영 상세**:
- `src/kortravelgeo/loaders/shape_dbf.py`를 추가해 DBF/SHP layer summary와 key set overlap helper를 공용화했다.
- T-040 `building_shape_bundle.py`는 공용 helper를 사용하도록 정리했다.
- `src/kortravelgeo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`를 추가했다.
- ADR-026을 추가했다. 상세주소 동 도형과 구역 추가 레이어는 기본 `full_load_batch`/`mv_geocode_target`에 섞지 않고, 필요 시 별도 overlay/분석 테이블로 둔다.

**실제 파일 검증**:
- 세종 상세주소 동 polygon은 40,478행이고 전자지도 `TL_SPBD_BULD` 55,819행의 부분집합이었다. `BD_MGT_SN + EQB_MAN_SN` 교집합은 40,478, detail only 0, 전자지도 only 15,341이다.
- 경남 상세주소 동 polygon은 923,702행이고 전자지도 `TL_SPBD_BULD` 1,269,029행의 부분집합이었다. 교집합은 923,702, detail only 0, 전자지도 only 345,327이다.
- 세종 `구역의 도형` 중 `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`는 전자지도와 key 기준 완전 중복이었다. 경남도 같은 결과다.
- `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key 교집합이 0건이고, `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key였다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_building_shape_bundle.py tests/unit/test_extra_shape_layers.py tests/integration/test_real_extra_shape_sources.py -q` → 11 passed, 2 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_SLOW_REAL_DATA=1 .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q` → 1 passed in 16.74s.
- `scripts/compare_extra_shape_layers.py`로 세종 실제 파일 JSON 출력을 확인했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 148 passed, 5 skipped.
- `ruff check .`, `mypy src/kortravelgeo scripts/compare_extra_shape_layers.py scripts/compare_building_shape_bundle.py`, `lint-imports`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 약 20분 리뷰 대기한다. 리뷰가 없으면 main에 merge하고 T-037 geometry 포함 SHP 대형 레이어 적재 튜닝으로 진행한다.

## 2026-05-26 (T-040 — `도로명주소 건물 도형` bundle 비교)

**작업**: PR #29 merge 이후 `codex/t040-building-shape-bundle` 브랜치에서 `도로명주소 건물 도형` bundle과 기존 전자지도 건물/출입구 레이어의 natural key overlap을 실제 파일로 비교했다.

**반영 상세**:
- `src/kortravelgeo/loaders/building_shape_bundle.py`를 추가했다. ZIP 내부 `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC`와 전자지도 `TL_SPBD_BULD`, `TL_SPBD_ENTRC`의 DBF key set을 순수 Python으로 비교한다.
- `scripts/compare_building_shape_bundle.py`를 추가해 세종/경남 비교 결과를 JSON으로 재현할 수 있게 했다.
- ADR-025를 추가했다. `도로명주소 건물 도형`은 단순 중복이 아니지만 현행 `tl_spbd_buld_polygon`/serving MV에는 섞지 않고, 후속 loader가 필요하면 `tl_roadaddr_buld_polygon`, `tl_roadaddr_buld_entrc`, `tl_roadaddr_spot_cntc` 같은 별도 테이블로 둔다.
- 세종 실제 비교는 기본 integration test로 넣고, 경남 full key scan은 `KTG_SLOW_REAL_DATA=1` 선택 테스트로 분리했다.

**실제 파일 검증**:
- 세종 address polygon key: bundle 27,792 distinct, 전자지도 `TL_SPBD_BULD` 55,819 distinct, 교집합 15,339, bundle only 12,453, 전자지도 only 40,480.
- 경남 address polygon key: bundle 656,230 distinct, 전자지도 `TL_SPBD_BULD` 1,269,029 distinct, 교집합 345,290, bundle only 310,940, 전자지도 only 923,739.
- 세종 출입구 key: bundle 28,111, 전자지도 27,787, 교집합 27,766, bundle only 345, 전자지도 only 21.
- 경남 출입구 key: bundle 661,416, 전자지도 656,133, 교집합 656,114, bundle only 5,302, 전자지도 only 19.

**검증**:
- `python -m pytest tests/unit/test_building_shape_bundle.py tests/integration/test_real_extra_shape_sources.py -q` → 7 passed, 1 skipped.
- `KTG_SLOW_REAL_DATA=1 python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_building_shape_bundle_gyeongnam_key_overlap_slow -q` → 1 passed in 18.48s.
- `python -m pytest -q` → 144 passed, 4 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` → 통과.

## 2026-05-26 (T-039 — PR 전 검증 보강)

**작업**: T-039 PR 생성 전 전체 검증을 돌리며 문서/DDL/테스트 계약을 보강했다.

**반영 상세**:
- 기본 DDL 문자열(`sql/ddl/001_schema.sql`, `infra/sql.py`)에서 `tl_roadaddr_entrc.ent_man_no`를 Alembic 0005와 동일하게 nullable로 맞췄다. 반대로 기존 `tl_locsum_entrc.ent_man_no`는 `sig_cd + ent_man_no` PK이므로 `NOT NULL`을 유지한다.
- `tests/unit/test_consistency_sql.py`는 T-039의 `serving_entrc` CTE와 `source_kind` sample을 검증하도록 갱신했다.
- `docs/backend-package.md`, `docs/t039-roadaddr-entrance-loader.md`, `README.md`에 T-039 이전 MV가 있는 DB에서는 direct 출입구 적재 뒤 `ktgctl refresh mv --swap`을 권장한다고 명시했다.

**검증**:
- `python -m pytest -q` → 141 passed, 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check --output openapi.json`, `git diff --check` → 통과.
- Docker PostGIS `localhost:15432`의 새 `kor_travel_geo_t039` DB에서 `tests/integration/test_optional_real_postgres_load.py` → 1 passed in 2.86s.
- `kor-travel-geo-ui`에서 `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` → 통과.

## 2026-05-26 (T-039 — `도로명주소 출입구 정보` direct entrance loader)

**작업**: PR #28 merge 이후 `codex/t039-direct-entrance-loader` 브랜치에서 `RNENTDATA_2605_*.txt` direct entrance 원천을 적재하는 T-039를 구현했다.

**반영 상세**:
- `tl_roadaddr_entrc` 테이블과 Alembic `0005_t039_roadaddr_entrance_table`을 추가했다. 실제 파일에서 `ent_man_no`가 비는 행이 있어 PK는 `bd_mgt_sn` 단독으로 두고, `ent_man_no`는 nullable 원천 보존 필드로 둔다.
- `src/kortravelgeo/loaders/text/roadaddr_entrance_loader.py`를 추가했다. 디렉터리 입력 시 17개 ZIP 내부의 `RNENTDATA_*.txt` member를 직접 발견하고, 좌표 결측/`0/0` sentinel row는 skip한다.
- CLI `ktgctl load roadaddr-entrances`와 API job kind `roadaddr_entrance_load`를 추가했다.
- `mv_geocode_target` 대표 좌표 선택 순서를 `tl_roadaddr_entrc` → `tl_locsum_entrc` → `tl_navi_buld_centroid`로 바꿨다. 응답 호환성을 위해 direct entrance도 기존 `pt_source='entrance'`로 둔다.
- C3/C4/C6/C7/C8 정합성 SQL은 `tl_roadaddr_entrc`와 `tl_locsum_entrc`를 합친 대표 출입구 CTE를 사용하게 했고, C10 기준월 비교에 `tl_roadaddr_entrc`를 포함했다.

**실제 파일/DB 검증**:
- 전국 17개 ZIP을 직접 읽어 총 6,418,169행, 모든 행 19컬럼, `ent_source_cd='RM'`, `ent_detail_cd='01'`을 확인했다.
- 세종 ZIP은 원천 27,868행, distinct `bd_mgt_sn` 27,868, 빈 `ent_man_no` 9건, 유효 좌표 적재 대상 27,779행이었다.
- 경남 ZIP은 원천 657,845행, distinct `bd_mgt_sn` 657,845, 빈 `ent_man_no` 100건이었다.
- Docker PostGIS `localhost:15432`에 `kor_travel_geo_t039` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.74s`이며 세종 RNENTDATA 3행이 `tl_roadaddr_entrc`와 `load_manifest`에 반영됐고, MV의 `pt_5179`가 direct entrance 좌표를 사용함을 확인했다.
- 대상 테스트 `tests/unit/test_roadaddr_entrance_loader.py`, `tests/integration/test_real_roadaddr_entrance_files.py`, schema/batch/CLI 계약 테스트 → 29 passed.
- 대상 `ruff check`와 `mypy src/kortravelgeo` → 통과.

**다음 작업**: 전체 검증과 frontend/OpenAPI drift 확인 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-038 — `tl_juso_parcel_link` DDL/로더 구현)

**작업**: PR #27 merge 이후 `codex/t038-parcel-link-loader` 브랜치에서 ADR-022의 보조 지번 1:N 테이블을 실제 구현했다.

**반영 상세**:
- `tl_juso_parcel_link` 테이블, 인덱스 3종, Alembic `0004_t038_parcel_link_table`을 추가했다. `bd_mgt_sn`은 `tl_juso_text` FK + `ON DELETE CASCADE`, PK는 `(bd_mgt_sn, pnu)`다.
- `src/kortravelgeo/loaders/text/parcel_link_loader.py`를 추가했다. `jibun_rnaddrkor_*` full snapshot은 기본 `TRUNCATE` 후 UPSERT하고, daily `LNBR`은 `MVM_RES_CD` mapping에 따라 UPSERT/DELETE한다.
- CLI `ktgctl load parcel-links`, `ktgctl load daily-parcel-links`를 추가했다.
- API job kind `juso_parcel_link_load`, `juso_parcel_link_delta`를 추가했고, `full_load_batch` 기본 child 순서에 `juso_text_load` 직후 `juso_parcel_link_load`를 넣었다.
- `kor-travel-geo-ui` `/admin/load` 기본 payload에도 `juso_parcel_link_load`를 추가했다.
- `daily_juso_delta`는 MST 전용으로 유지하고, 같은 ZIP의 LNBR은 `juso_parcel_link_delta`로 별도 적용한다.

**실제 파일/DB 검증**:
- 실제 `jibun_rnaddrkor_seoul.txt`를 새 iterator로 파싱해 PNU `1111012000101500000`, `1114010300100680000`을 확인했다.
- 실제 `20260401_dailyjusukrdata.zip`의 LNBR 204행을 새 iterator로 파싱하고 첫 행 PNU `4148025326100310007`, `mvmn_de=20260402`, `MVM_RES_CD=31`을 확인했다.
- Docker PostGIS `localhost:15432`에 `kor_travel_geo_t038` DB를 만들고 선택형 실제 적재 테스트를 실행했다. 결과는 `1 passed in 2.81s`이며 snapshot 2행, daily LNBR 5행이 `tl_juso_parcel_link`와 `load_manifest`에 반영됐다.
- 전체 `pytest -q` → 133 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
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
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

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
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.

**다음 작업**: 전체 검증 후 PR을 열어 20분 리뷰 대기한다.

## 2026-05-26 (T-028 — 도로명주소 일변동 ZIP 로더)

**작업**: PR #24 merge 이후 `codex/t028-daily-delta-loader` 브랜치에서 `data/juso/daily/*.zip` 일변동 ZIP 로더를 구현했다.

**반영 상세**:
- `src/kortravelgeo/loaders/text/daily_juso_loader.py`를 추가했다. `AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT`를 읽어 `tl_juso_text`에 UPSERT/DELETE로 반영한다.
- `MVM_RES_CD`는 `Settings.mvm_res_code_actions`를 사용한다. 기본값은 `31/33=insert`, `34/35/36=update`, `63/64=delete`이며, 알 수 없는 코드는 `LoaderError`로 중단한다.
- 한 batch 안의 동일 `bd_mgt_sn`은 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 master에 반영한다.
- `TH_SGCO_RNADR_LNBR.TXT`는 현재 master table에 쓰지 않고 `unsupported_lnbr_rows`로 집계해 `load_manifest.source_set`에 남긴다. T-029에서 `jibun_rnaddrkor_*`와 함께 1:N 지번 관계 테이블 여부를 결정한다.
- member 내용이 `No Data`인 경우 컬럼 수 오류로 보지 않고 skip하며 `skipped_no_data_sources`에 기록한다.
- CLI `ktgctl load daily-juso`와 API job kind `daily_juso_delta`를 추가했고, `openapi.json` 및 `kor-travel-geo-ui/types/api.gen.ts`를 갱신했다.
- ADR-021과 `docs/t028-daily-juso-delta.md`를 추가해 MST/LNBR 분리, manifest watermark, 실제 파일 검증 수치를 문서화했다.

**실제 파일 확인**:
- `/mnt/f/dev/kor-travel-geo/data/juso/daily/20260401_dailyjusukrdata.zip`의 MST member는 422행이며 코드 분포는 `31=185`, `34=57`, `63=180`이었다.
- 같은 ZIP의 LNBR member는 204행이며 이번 구현에서는 manifest에 미지원 행 수로만 기록한다.
- `/mnt/f/dev/kor-travel-geo/data/juso/daily/20260404_dailyjusukrdata.zip`은 MST/LNBR 모두 `No Data`였다.

**검증 진행**:
- `pytest tests/unit/test_daily_juso_loader.py tests/integration/test_real_juso_text_loaders.py::test_actual_daily_juso_zip_loads_mst_rows_and_skips_no_data_members tests/unit/test_cli_contract.py -q` → 11 passed.
- `pytest tests/integration/test_real_juso_text_loaders.py -q` → 실제 NTFS `data/juso` fallback으로 5 passed.
- Docker PostGIS `localhost:15432`에 전용 DB `kor_travel_geo_t028`을 생성하고 `KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t028 pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 이 검증은 daily sample 3행 적용 뒤 `load_manifest.last_mvmn_de=20260402`, `row_count=3`, `unsupported_lnbr_rows=204`까지 확인한다.
- 대상 `ruff check`와 대상 `mypy` → 통과.
- `scripts/export_openapi.py`와 frontend `npm run gen:types` 실행.
- 전체 `pytest -q` → 122 passed / 3 skipped.
- `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `scripts/export_openapi.py --check`, `git diff --check` → 통과.
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
- `ruff check .`, `mypy src/kortravelgeo scripts/benchmark_mv_refresh.py`, `lint-imports`, `bash -n scripts/fullload_test.sh`, `git diff --check` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후, 코멘트가 있으면 반영하고 없으면 main에 merge한다.

## 2026-05-26 (T-036 — `maplibre-vworld-js` main 동기화)

**작업**: PR #22 merge 이후 `codex/t036-maplibre-vworld-sync` 브랜치에서 `kor-travel-geo-ui`의 `maplibre-vworld` dependency를 `digitie/maplibre-vworld-js` 최신 main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 갱신했다.

**반영 상세**:
- `kor-travel-geo-ui/package.json`과 lockfile의 `maplibre-vworld` GitHub SHA를 `11321fe8b8f4da849ee5c24ba18a27206a55e26e`에서 `c91c9f304669ce3f5fc4915f21186b23731d5816`로 올렸다. CI에서 SSH key 없이 설치되어야 하므로 dependency와 `resolved`는 모두 `git+https`를 유지한다.
- 최신 upstream은 `redactVWorldTileUrl()`가 아니라 `redactVWorldUrl()`를 export하고, redaction 표기는 `[redacted]` 대신 `***`를 사용한다.
- `kor-travel-geo-ui/lib/vworld.ts`는 `redactVWorldUrl as redactVWorldTileUrl` alias를 둬 기존 `CoordinateMap` import 계약을 유지한다.
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

**작업**: PR #21 merge 이후 `codex/t035-mv-refresh-benchmark` 브랜치에서 `mv_geocode_target` 갱신 전략을 실제 전국 DB `kor_travel_geo_t033`에서 비교했다. 재현 가능한 계측을 위해 `scripts/benchmark_mv_refresh.py`를 추가하고, `CONCURRENTLY`와 shadow swap의 phase별 시간, temp file/byte 증가, index 크기를 JSON으로 남겼다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`, DB `kor_travel_geo_t033`.
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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check scripts/benchmark_mv_refresh.py tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py src/kortravelgeo/loaders/postload.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy scripts/benchmark_mv_refresh.py src/kortravelgeo/loaders/postload.py` → 통과.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-036에서 `maplibre-vworld-js` upstream main과 UI dependency를 동기화한다.

## 2026-05-26 (T-034 — SHP append 병목 튜닝)

**작업**: PR #20 merge 이후 `codex/t034-shp-append-tuning` 브랜치에서 T-033의 최우선 병목이었던 `TL_SPRD_INTRVL` 적재 경로를 보강했다. geometry가 없는 DBF 속성 레이어는 GDAL `VectorTranslate` append를 우회해 직접 DBF scan + `psycopg COPY`로 적재하도록 분기했다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`.
- 데이터: ext4 mirror `/home/digitie/kor-travel-geo-data/juso/도로명주소 전자지도`.
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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py` → 통과.
- 실제 Docker DB `kor_travel_geo_t034_before`, `kor_travel_geo_t034_after`, `kor_travel_geo_t034_sejong`에서 기준선/개선 후/9개 레이어 전체 적재를 확인했다.

**다음 작업**: PR을 열어 20분 리뷰 대기 후 코멘트가 없거나 반영 완료되면 main에 merge한다. 이후 T-035에서 MV refresh/swap benchmark를 진행한다. `TL_SPBD_BULD` GDAL append 병목은 도형 포함 대형 레이어라 이번 PR에서는 유지하고, 별도 튜닝 후보로 남긴다.

## 2026-05-26 (T-033 — 전국 full-load 성능 재검증)

**작업**: PR #19 merge 이후 `codex/t033-full-load-revalidation` 브랜치에서 빈 Docker DB `kor_travel_geo_t033`를 만들고 실제 전국 `data/juso` full-load를 다시 실행했다. 사용자 지시에 따라 로그와 시스템 상태를 상세히 남기고, T-034/T-035 튜닝 전 기준선으로 문서화했다.

**실행 환경**:
- Docker PostGIS: `kor-travel-geo-t027-db-1`, `localhost:15432`, DB `kor_travel_geo_t033`.
- 데이터: ext4 mirror `/home/digitie/kor-travel-geo-data`, 원본 `/mnt/f/dev/kor-travel-geo/data/juso`.
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

**검증**: 리뷰 반영 뒤 대상 단위 테스트 41개 통과, 전체 `pytest -q` 104 passed / 7 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 세종·경남 축소 검증 1회)

**작업**: 사용자 지시에 따라 반복 횟수를 1회로 낮추고, 세종특별시·경상남도 축소 데이터만 실제 Docker DB(`kor_travel_geo_t032`)에 적재했다. 전국 full test와 반복 trial은 수행하지 않았다.

**결과**:
- `load all-sidos --no-refresh --allow-consistency-error`는 SHP 18개 layer 적재까지 완료했으나 `resolve_text_geometry_links()` 첫 UPDATE가 기본 5초 `statement_timeout`에 걸려 실패했다. 경과 2시간 1분 13초, 최대 RSS 163,672KB.
- 실패를 반영해 `resolve_text_geometry_links()`에 transaction-local 30분 timeout을 추가했다.
- 같은 DB에서 후처리만 재실행해 28.53초, 최대 RSS 77,156KB로 성공했다.
- C4/C6/C7 data-quality export는 11.25초, 최대 RSS 79,884KB로 CSV 6개를 생성했다.
- C4/C6/C7 정합성은 14.88초, 최대 RSS 80,204KB로 완료했다. `severity_max=ERROR`이며 C4 213건(`over_500m=2`), C6 77건, C7 851건이다.

**관찰**: 두 시도 축소 검증에서도 `TL_SPRD_INTRVL` 1,960,217행, `TL_SPBD_BULD` 1,324,177행 append가 전체 시간을 지배했다. GDAL `PG_USE_COPY=YES` 설정에도 `pg_stat_activity`에서는 일부 구간이 INSERT 형태로 관측되어, 후속 PR에서 GDAL COPY 강제 여부와 `TL_SPRD_INTRVL` 전용 loader를 다시 검토한다.

**검증**: 대상 단위 테스트 38개, 전체 `pytest -q` 101 passed / 7 skipped, `ruff check .`, `mypy src/kortravelgeo`, `lint-imports`, `git diff --check` 모두 통과했다.

## 2026-05-25 (T-032 — 성능 튜닝 범위 축소)

**작업**: PR #18 merge 이후 T-032를 시작했다. 사용자 지시에 따라 성능 튜닝 반복 기준은 기존 "10회 이상"에서 "세종특별시·경상남도 축소 데이터 1회 검증"으로 낮췄다. 전체 전국 full test와 반복 trial은 후속 안정화 단계로 미룬다.

**구현 방향**:
- C4 data-quality export는 nearest polygon 거리 계산을 `_ktg_dq_c4_distances` 임시 테이블로 한 번 만들고, sample CSV와 bucket CSV가 같은 결과를 재사용하도록 바꾼다.
- C6/C7 data-quality export는 polygon mismatch 결과를 case별 임시 violation 테이블로 한 번 만들고, sample CSV와 region summary CSV가 같은 결과를 재사용하도록 바꾼다.
- C4/C6/C7 정합성 SQL은 PostgreSQL planner가 고비용 CTE를 중복 평가하지 않도록 `MATERIALIZED` CTE를 명시한다.
- `load shp-all` 및 `load all-sidos --shp-root`는 여러 시도 SHP를 연속 적재할 때 각 시도마다 통계를 갱신하지 않고 마지막 시도 뒤 1회만 `ANALYZE`한다.

**검증 계획**: `kor_travel_geo_t032` Docker DB에서 세종특별자치시·경상남도 데이터 1회만 적재/검증한다. 현재 실행 중이며, 완료 결과와 경과 시간은 이 항목 또는 후속 항목에 이어 적는다.

## 2026-05-25 (PR #18 rebase — VWorld debug helper sync)

**작업**: 사용자 지시에 따라 T-032 성능 튜닝 전에 PR #18을 먼저 처리했다. PR #17이 main에 merge되어 `CHANGELOG.md`, `docs/journal.md`, `docs/resume.md`에서 충돌이 발생했으며, PR #17 데이터 품질 기록과 PR #18 VWorld sync 기록을 모두 보존하는 방식으로 rebase했다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과. high 기준 취약점 없음, moderate 7건은 기존 Next/PostCSS 및 Vitest/Vite 경로 잔여.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `git diff --check` → 통과.

**다음 작업**: PR #18을 푸시하고 PR 본문/코멘트를 갱신한다. PR #18 안정화 후 별도 T-032 성능 튜닝 PR을 시작한다.

## 2026-05-25 (PR #17/T-031 — 데이터 품질 export와 실제 DB 검증)

**작업**: PR #16 merge 확인 후 PR #17을 최신 `main` 위로 rebase했다. 충돌은 `docs/journal.md`, `docs/resume.md`에서만 발생했고, T-031 기록과 PR #15/VWorld 기록을 모두 보존하는 방식으로 해결했다.

**구현 상세**:
- `src/kortravelgeo/loaders/data_quality.py`를 추가했다. C2/C4/C6/C7 후속 분석용 CSV 8종(`c2_samples`, `c2_missing_key_summary`, `c4_distance_samples`, `c4_distance_buckets`, `c6/c7 samples`, `c6/c7 region_summary`)을 같은 SQL로 재현할 수 있다.
- `ktgctl validate data-quality-samples` CLI를 추가했다. `--cases C2,C4,C6,C7`, `--limit`, `--output-dir`로 산출 범위를 제어한다.
- SHP 보조 로더가 GDAL `SQLStatement` projection에 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`을 넣도록 보강했다. 기존 T-027 DB는 재적재 전이라 polygon `source_file`이 NULL이지만, 이후 재적재분부터 원천 파일 역추적이 가능하다.
- C4 sample CSV에는 출입구 좌표, 가장 가까운 polygon 대표점 좌표, `delta_lon`, `delta_lat`를 함께 넣어 500m+ 이상치의 좌표계/원천 오류 패턴을 빠르게 볼 수 있게 했다.

**실제 검증**:
- Docker DB: `kor-travel-geo-t027-db-1`, `localhost:15432`.
- `ktgctl validate data-quality-samples --cases C2,C4,C6,C7 --limit 5` → CSV 8개 생성, 2분 52.45초, 최대 RSS 79,956KB.
- `ktgctl validate data-quality-samples --cases C4 --limit 20` → C4 CSV 2개 생성, 2분 22.90초, 최대 RSS 80,008KB.
- `delta_lon`/`delta_lat` 컬럼 추가 후 `ktgctl validate data-quality-samples --cases C4 --limit 3` → 2분 18.48초, 최대 RSS 80,124KB. 상위 3건의 `delta_lon`은 각각 약 `1.9998~1.9999`도였다.
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

**작업**: `maplibre-vworld-js` PR #9를 먼저 열어 `VWorldMap`의 click/error/flyTo hook과 VWorld tile error/redaction helper를 추가했다. 이어 `kor-travel-geo-ui` 후속 브랜치에서 upstream commit `11321fe`로 dependency를 동기화하고, 디버그 UI의 tile error 분류와 URL redaction을 upstream helper로 교체했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#11321fe`로 갱신했다. lockfile의 `resolved`도 SSH가 아니라 HTTPS를 유지한다.
- `kor-travel-geo-ui/lib/vworld.ts`에서 `isVWorldTileError()`와 `redactVWorldTileUrl()`를 재수출한다.
- `components/vworld/CoordinateMap.tsx`는 로컬 `isTransientTileError()`/`redactVWorldTileUrl()` 중복 구현을 제거하고 upstream helper를 사용한다. key 미설정 fallback, overlay 임계치, marker 즉시 이동, SSR dynamic wrapper는 기존 UI 계약대로 유지한다.
- VWorld helper 단위 테스트에 tile error 분류와 key redaction 검증을 추가했다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 22 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리베이스 — maplibre-vworld package 소비)

**작업**: PR #14가 main에 merge된 뒤 `codex/maplibre-vworld-ui`를 최신 `main` 위로 rebase했다. 이후 upstream `digitie/maplibre-vworld-js` main commit `a5b3c65`를 확인하고, `kor-travel-geo-ui`가 VWorld helper/CSS를 실제 `maplibre-vworld` package에서 소비하도록 갱신했다.

**구현 상세**:
- `maplibre-vworld` dependency를 `git+https://github.com/digitie/maplibre-vworld-js.git#a5b3c65`로 고정했다. CI에서 SSH key 없이 설치되어야 하므로 package-lock의 `resolved`도 `git+https`로 유지했다.
- `kor-travel-geo-ui/lib/vworld.ts`는 로컬 구현을 제거하고 `getVWorldTileUrl()`, `getVWorldStyle()`, `getVWorldMaxZoom()`, `VWorldLayerType`를 upstream package에서 재수출한다.
- 전역 CSS는 `maplibre-vworld/style.css`를 import한다. 이 package export가 MapLibre GL 기본 CSS와 package CSS를 함께 제공한다.
- upstream style source id가 `vworld-${layerType}`이고 `Hybrid`는 `vworld-satellite`와 `vworld-Hybrid`를 함께 쓰므로, tile error source 판별을 `vworld` prefix 기준으로 바꿨다.
- Vitest/jsdom에서 upstream bundle이 `maplibre-gl` worker URL과 React `require()` 경로를 건드리는 문제를 테스트 setup shim으로 보정했다. 이 현상은 후속 `maplibre-vworld-js` 정합화 PR에서 upstream 테스트/번들 개선 후보로 추적한다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, README, changelog, `docs/resume.md`를 최신 package 소비 상태로 갱신했다.
- `VWorldMap` 컴포넌트 전체 대체는 이번 PR에 넣지 않고 후속 PR로 분리했다. 후속 PR은 click callback, marker 제어, tile error hook/redaction, key 미설정 fallback, SSR-safe wrapper를 `kor-travel-geo-ui`와 `maplibre-vworld-js` 사이에서 맞추는 작업이다.

**검증**:
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm ci --ignore-scripts` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run lint` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run type-check` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run test` → 7 files / 20 tests 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm run build` → 통과.
- `cd kor-travel-geo-ui && PATH=/tmp/node-v20.19.5-linux-x64/bin:$PATH npm audit --audit-level=high` → high 기준 통과. 잔여 advisory는 Next/PostCSS와 Vitest/Vite 경로의 moderate 7건이다.
- `git diff --check` → 통과.

## 2026-05-25 (PR #15 리뷰 보강 — VWorld MapLibre 안정화)

**작업**: PR #15 리뷰의 merge condition을 반영했다. 디버그 UI는 VWorld WMTS + MapLibre GL JS 방향을 유지하되, upstream package가 안정화되기 전까지 `maplibre-vworld` GitHub 의존성을 UI 패키지 graph에 올리지 않는 정책으로 정리했다.

**구현 상세**:
- `maplibre-vworld` 미사용 GitHub 의존성을 `kor-travel-geo-ui/package.json`과 lockfile에서 제거했다. upstream 보강은 별도 PR로 진행하고, 안정 태그 또는 SHA에서 install/build가 검증된 뒤 다시 도입한다.
- `components/vworld/LazyCoordinateMap.tsx`를 추가해 `CoordinateMap`을 `next/dynamic(..., { ssr: false })`로 지연 로딩한다. `/debug/geocode`, `/debug/reverse`는 이 wrapper만 import한다.
- `CoordinateMap.tsx`에서 VWorld tile fetch 오류를 transient로 분리했다. tile URL은 key가 드러나지 않도록 redaction한 뒤 경고 로그만 남기고, 누적 임계치 이상이거나 tile 외 오류일 때만 overlay를 표시한다.
- `lib/vworld.ts`에 레이어별 `maxZoom`을 추가했다. `Base`/`gray`/`midnight`는 z19, `Hybrid`/`Satellite`는 z18로 제한한다. attribution 표기도 `공간정보 오픈플랫폼 브이월드`로 보정했다.
- marker 위치 갱신 시 `flyTo({ animate: false, duration: 0 })`를 사용해 지도 클릭 후 불필요한 애니메이션 되튐을 줄였다.

**문서화**:
- ADR-020, `docs/frontend-package.md`, `docs/external-apis.md`, `docs/resume.md`, changelog에 dependency 미선언 정책, dynamic import, tile error 처리, zoom 한계, CSP/key 제한 주의사항을 명시했다.
- PR 리뷰를 놓치지 않도록 `docs/resume.md`의 알려진 함정에 conversation comment와 formal review를 모두 확인하는 루틴을 추가했다.

**검증**:
- `cd kor-travel-geo-ui && npm run lint` → 통과.
- `cd kor-travel-geo-ui && npm run type-check` → 통과.
- `cd kor-travel-geo-ui && npm run test` → 7 files / 18 tests 통과. `CoordinateMap` fallback과 dynamic loading skeleton 테스트를 포함한다.
- `cd kor-travel-geo-ui && npm ci --ignore-scripts` → 통과. `maplibre-vworld` GitHub dependency 없이 cold install을 확인했다.
- `cd kor-travel-geo-ui && npm run build` → 통과. `/debug/geocode`, `/debug/reverse`가 static route로 생성되고 지도 bundle은 dynamic import 경로로 분리된다.
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여다.
- `cd kor-travel-geo-ui && npm run dev -- --hostname 127.0.0.1 --port 3001` 후 `HEAD /debug/reverse` → 200 OK. 서버 렌더 단계에서는 skeleton이 표시되고 지도 bundle은 클라이언트 chunk로 분리됨을 HTML에서 확인했다.

## 2026-05-25 (디버그 UI 지도 VWorld/MapLibre 전환)

**작업**: 사용자 지시에 따라 `kor-travel-geo-ui`의 디버그 지도 방향을 Kakao Maps SDK에서 VWorld WMTS + MapLibre GL JS로 전환했다. 실제 VWorld API key는 저장소에 기록하지 않고, `.env.local`의 `NEXT_PUBLIC_VWORLD_API_KEY`로만 주입하는 정책을 유지했다.

**구현 상세**:
- `react-kakao-maps-sdk` 의존성을 제거하고, 직접 사용하는 `maplibre-gl`을 명시 의존성으로 추가했다.
- `components/kakao/CoordinateMap.tsx`를 `components/vworld/CoordinateMap.tsx`로 교체했다. 지도 click은 기존과 동일하게 `(lon, lat)` 순서로 callback을 호출하고, marker도 EPSG:4326 좌표를 그대로 사용한다.
- `lib/vworld.ts`에 VWorld WMTS tile URL과 MapLibre raster style helper를 추가했다. `Base`/`gray`/`midnight`/`Hybrid`는 `png`, `Satellite`는 `jpeg` 타일을 사용한다.
- `NEXT_PUBLIC_VWORLD_API_KEY`가 없거나 지도 로딩에 실패하면 기존처럼 같은 크기의 좌표 fallback preview를 보여 준다.

**문서화**:
- ADR-020을 추가했다. 디버그 UI 지도는 VWorld WMTS + MapLibre를 기준으로 하고, `digitie/maplibre-vworld-js`의 패키징·타입·Next.js 호환 문제가 나오면 해당 저장소도 적극 수정 대상에 포함한다고 명시했다.
- `docs/frontend-package.md`, `docs/external-apis.md`, `docs/architecture.md`, `README.md`, `docs/resume.md` 등에 VWorld 지도 환경변수와 upstream 보강 원칙을 반영했다.

**검증**:
- `cd kor-travel-geo-ui && npm run lint` → 통과.
- `cd kor-travel-geo-ui && npm run type-check` → 통과.
- `cd kor-travel-geo-ui && npm run test` → 6 files / 15 tests 통과. VWorld WMTS helper 단위 테스트를 포함한다.
- `cd kor-travel-geo-ui && npm ci --ignore-scripts && npm run build` → 통과. HTTPS Git dependency lockfile 재현성을 확인했다.
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과. Next.js/Vitest 경로의 moderate advisory는 잔여.
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
- `mypy src/kortravelgeo` → 통과.
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
- Optional: Docker 포트 환경변수를 저장소 prefix 규칙에 맞춰 `KTG_DB_PORT`에서 `KTG_DB_PORT`로 변경했다.
- 반복 방지: `docs/agent-guide.md`에 PR 리뷰 확인 프로토콜을 추가했다. 앞으로 PR 리뷰 반영 시 conversation comments뿐 아니라 `reviews[].body`와 `review_threads[]`를 반드시 확인한다.

**검증**:
- `pytest tests/unit/test_alembic_migrations.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_shp_loader_gdal.py tests/unit/test_postload_mv.py tests/unit/test_navi_loader.py tests/unit/test_consistency_sql.py -q` → 17 passed.
- `ruff check .` → 통과.
- `mypy src/kortravelgeo` → 통과.
- `lint-imports` → Layered architecture kept.
- `bash -n scripts/fullload_test.sh` → 통과.
- `PATH="$PWD/.venv/bin:$PATH" DATA_DIR=/home/digitie/kor-travel-geo-data KTG_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` → 통과. 출력 DSN은 `localhost:15432`.
- `pytest -q` → 80 passed, 7 skipped.
- 임시 DB `kor_travel_geo_pr14_review`에서 `alembic upgrade head` → 0001, 0002 적용 성공. `LI_CD=''` 샘플 insert 시 generated `bjd_cd=1111010100`, `rncode_full=111103100012` 확인.
- 실제 T-027 DB 영향 조회: `empty_li=0`, `empty_rn=0`, `empty_rds_sig=0`, `bjd_8=0`, `bjd_10=10,687,732`.

## 2026-05-25 (PR #14/T-027 — 실제 전국 SHP 재적재와 정합성 재검증)

**작업**: `data/juso/도로명주소 전자지도` 실제 전국 SHP 17개 시도 × 9개 레이어를 새 natural-key 스키마로 Docker PostGIS에 재적재하고, C1~C10 정합성 검증을 실제 DB에서 재실행했다.

**실행 로그**:
- 상세 로그: `artifacts/fullload/20260524_173115/execution-log.md` (git ignore 산출물)
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Python 3.12.3, GDAL 3.8.4
- DB: `kor-travel-geo-t027-db-1`, `localhost:15432`, `kor_travel_geo`
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
- `ruff check src/kortravelgeo/loaders/consistency.py tests/unit/test_consistency_sql.py` 통과.
- `pytest tests/unit/test_consistency_sql.py -q`는 pytest capture 임시파일 `FileNotFoundError`로 테스트 실행 전 실패.
- `pytest -s tests/unit/test_consistency_sql.py -q` → 2 passed.
- SHP 9개 테이블 `ANALYZE` → 4.14초, 성공.
- `ruff check src/kortravelgeo/infra/geocode_repo.py src/kortravelgeo/infra/zip_repo.py src/kortravelgeo/infra/pobox_repo.py tests/unit/test_infra_repo_sql.py` 통과.
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
- `scripts/fullload_test.sh`는 기본 `KTG_PG_STATEMENT_TIMEOUT_MS`를 30분으로 높인다. 대량 링크 해소와 shadow MV 빌드가 운영 기본값 5초에 막히지 않도록 하기 위함이다.
- 실제 MV 빌드 후 `pt_source='centroid'`가 0건인 것을 확인했다. 원인은 내비게이션용DB의 `bd_mgt_sn`이 25자리이고 정본 `tl_juso_text.bd_mgt_sn`은 26자리라 직접 조인이 불가능한 점이었다. 또한 내비 `bjd_cd`는 리 코드가 `00`인 경우가 많아 10자리 법정동 완전 일치도 부적합했다. MV fallback을 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 대표 centroid 조인으로 변경했다.
- 두 번째 MV swap에서 `idx_mv_next_geocode_target_next_pk`가 이미 존재한다는 충돌을 확인했다. 첫 swap 때 shadow MV 인덱스명이 운영 MV에 그대로 남았기 때문이다. swap 전후에 `idx_mv_next_*` 이름을 운영명 `idx_mv_*`로 정규화하도록 보강했다. 이어 실제 재시도에서 old MV의 운영명 인덱스가 아직 있는 상태로 next 인덱스를 rename하려 하면 next 인덱스가 drop되는 것을 확인해, old MV를 먼저 drop한 뒤 next 인덱스를 rename하도록 순서를 조정했다.
- 실제 C1~C10 정합성 검증에서 C1/C2가 전량 불일치했다. `TL_SPBD_BULD.BD_MGT_SN`도 25자리이고 정본은 26자리라 건물 polygon도 직접 `bd_mgt_sn` 조인이 불가능했다. `tl_spbd_buld_polygon`에 `RDS_SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `SIG_CD`, `EMD_CD`, `LI_CD`를 함께 적재하고 C1/C2/C4/C5를 natural key 기준으로 바꿨다. C8은 `TL_SPRD_RW`에 `rds_man_no`가 없어 전량 WARN이 나므로, `TL_SPRD_MANAGE` LineString geometry를 적재해 도로 인접성 검증에 사용하도록 바꿨다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py -q` → 6 passed.
- `.venv/bin/python -m ruff check src/kortravelgeo/loaders/shp/polygons_loader.py src/kortravelgeo/cli/main.py tests/unit/test_shp_loader_gdal.py tests/unit/test_cli_contract.py` → 통과.
- 실패로 오염된 SHP 보조 테이블 9개만 drop 후 `KTG_PG_DSN=...15432 .venv/bin/ktgctl init-db` 재실행. MV 생성은 timeout 경고가 났지만 SHP 테이블 스키마는 `MULTIPOLYGON 5179`로 복구됨을 확인했다.
- `세종특별자치시` 실제 SHP 9개 레이어 적재 성공: 59.09초, 최대 RSS 약 128MiB, `tl_spbd_buld_polygon` 55,819행, `tl_sprd_intrvl` 100,009행 등 9개 테이블 row count 확인.
- 전국 SHP 153개 레이어 적재 성공: 3시간 1분 34초, 최대 RSS 약 181MiB. 정확한 row count는 `tl_spbd_buld_polygon` 10,687,732행, `tl_sprd_intrvl` 16,993,167행, `tl_sprd_rw` 1,482,679행 등으로 확인했다.

**다음 작업**: 변경분을 PR #14에 푸시하고, 같은 Docker DB에서 전국 `shp-all --mode full`을 재실행한다. 이후 pobox/bulk optional 단계, 링크 해소, MV swap, C1~C10 정합성, smoke test를 순서대로 계속 진행한다.

## 2026-05-24 (PR #14/T-027 — 실제 데이터로드 실행 중 포트 충돌 방지)

**작업**: PR #13이 main에 머지된 뒤 `codex/t027-fullload-execution` 브랜치에서 실제 데이터로드를 시작했다. WSL ext4 클론(`~/dev/kor-travel-geo`)에서 Python/GDAL 환경을 만들고, `F:\dev\kor-travel-geo\data` 원본을 `~/kor-travel-geo-data` 작업 사본으로 복사했다.

**실행 로그**:
- 상세 실행 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 기록한다.
- 환경: WSL2 Ubuntu 24.04, AMD Ryzen 7 7840HS 16 vCPU, 메모리 29GiB, Docker 29.5.2, Docker Compose v5.1.4, Python 3.12.3, GDAL 3.8.4.
- `--copy-data` 시작 `2026-05-24T17:31:15+09:00`, 종료 `2026-05-24T18:35:47+09:00`, 경과 약 1시간 4분 32초.
- 복사 결과: `~/kor-travel-geo-data/juso` 약 25GB, 파일 683개. `epost`는 현재 원본 파일이 없어 빈 디렉터리다.

**발견한 문제**:
- 로컬 5432 포트가 기존 `airflow-postgres-1` 컨테이너에서 이미 사용 중이었다.
- T-027 기본 compose/스크립트가 `localhost:5432`를 그대로 사용하면 기존 DB에 DDL/적재를 실행할 위험이 있다.

**보강 상세**:
- 당시 인프라 설정 파일의 외부 포트를 `${KTG_DB_PORT:-5432}:5432`로 파라미터화했다.
- `scripts/fullload_test.sh`는 `KTG_PG_DSN`이 없을 때 `KTG_DB_PORT`를 반영한 DSN을 만든다.
- `docs/t027-fullload-plan.md`, `docs/dev-environment-recovery.md`, `CLAUDE.md`에 `KTG_DB_PORT=15432` 사용 예와 포트 충돌 주의사항을 추가했다.

**검증**:
- `bash -n scripts/fullload_test.sh` 통과.
- `DATA_DIR=/home/digitie/kor-travel-geo-data KTG_DB_PORT=15432 PLAN_ONLY=1 bash scripts/fullload_test.sh` 통과. 출력 DSN이 `localhost:15432`로 바뀌는 것을 확인했다.
- `git diff --check` 통과.

**다음 작업**: PR 생성 후 `KTG_DB_PORT=15432`로 Docker PostGIS를 기동하고 실제 적재를 계속 진행한다. 이후 발견되는 문제는 같은 PR에 누적한다.

## 2026-05-24 (PR #13/T-027 — Windows 재설치·Codex 세션 복구 문서화)

**작업**: Windows 재설치 후 `git pull`로 PR #13 작업을 문제없이 이어갈 수 있도록 복구 절차를 문서화했다. 실제 Docker 전체 적재와 `PLAN_ONLY=1` 실행은 하지 않았다.

**보강 상세**:
- `docs/windows-reinstall-recovery.md`를 추가했다. Git branch/PR을 영속 상태의 기준으로 두고, `data/`·`.env`·API 키·WSL distro·Docker volume의 백업 여부를 구분했다.
- 재설치 후 WSL/GDAL/Python 환경 복구, PR #13 브랜치 checkout, `docs/t027-fullload-plan.md` 확인, `PLAN_ONLY=1 bash scripts/fullload_test.sh` preflight 순서를 명시했다.
- Codex 레벨 복구는 repo에 넣을 내용과 로컬 세션 편의 기능을 분리했다. 문서에는 일반적인 `codex resume`, `codex fork`, `codex doctor`, `codex cloud` 확인 명령과 `CODEX_HOME`/`.codex` 백업 주의사항만 남겼다.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/dev-environment.md`, `docs/dev-environment-recovery.md`, `docs/resume.md`에서 새 복구 문서를 참조하도록 연결하고, 실제 적재는 사용자 명시 전 실행하지 않는 금지선을 맞췄다.

**다음 작업**: PR #13 리뷰 후에도 실제 전체 적재는 바로 실행하지 않는다. 먼저 문서와 스크립트 syntax 확인을 거친 뒤, 사용자가 허용하면 `PLAN_ONLY=1` preflight 결과를 PR에 공유한다.

## 2026-05-24 (PR #13/T-027 — Docker full-load 계획 보강)

**작업**: 사용자 지시에 따라 실제 Docker 전체 적재 실행은 중단하고, `F:\dev\kor-travel-geo\data\juso` 전체를 대상으로 한 계획/문서/스크립트 preflight 보강만 진행했다. 로컬 파일 시스템은 목록과 용량만 확인했고 DB 적재·Docker 실행은 하지 않았다.

**확인한 데이터 인벤토리**:
- `data/juso` 전체는 약 28GB다.
- 현재 full-load에 바로 쓸 수 있는 자료는 `202603_도로명주소 한글_전체분`, `202604_위치정보요약DB_전체분.zip`, `202604_내비게이션용DB_전체분`, `도로명주소 전자지도`다.
- `daily/*.zip`, `jibun_rnaddrkor_*`, `건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`, `도로명주소 출입구 정보`는 현재 로더의 직접 적재 대상이 아니므로 후속 태스크로 분리했다.

**보강 상세**:
- `docs/t027-fullload-plan.md`를 실행 전 리뷰 가능한 계획서로 재작성했다. 실행 금지선, Docker project/volume 안전장치, 기준월 분리, phase별 중단·재개, 산출물 경로, 미지원 자료 후속 태스크를 명시했다.
- `scripts/fullload_test.sh`는 실행 산출물로 남기되 `PLAN_ONLY=1` preflight를 추가했다. 단일 `YYYYMM` 대신 `JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM`을 분리하고, CLI 호출은 `kor-travel-geo` console script로 맞췄다.
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
- M4: Prometheus gauge 이름을 `kor_travel_geo_cache_hits_total`에서 `kor_travel_geo_cache_hits`로 변경했다.
- M5: `ExplainDebugger`가 `explainFormSchema`를 사용해 SELECT/WITH와 세미콜론 금지를 클라이언트에서도 검증한다.
- CI: `scripts/__init__.py`를 추가하고 pytest `pythonpath`에 repository root를 명시해 GitHub Actions의 pytest 수집 환경에서도 `scripts.export_openapi` import가 안정적으로 동작하게 했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 70 passed, 1 skipped
- 임시 DB `kor_travel_geo_codex_pr12_review`에서 `KTG_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed
- `cd kor-travel-geo-ui && npm run lint && npm run type-check && npm run test && npm run build` → 통과, Vitest 12 passed
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high && npm audit --audit-level=high` → high 기준 통과, moderate advisory만 잔여

**다음 작업**: PR #12 CI 재확인과 리뷰어 코멘트 답변.

## 2026-05-23 (PR #12 — T-021~T-026 프론트엔드·관측·CI 구현)

**작업**: PR #11을 main에 머지한 뒤, PR #11 후속 의견을 PR #12로 이관했다. PR #12 범위는 T-018~T-020이 main에 이미 포함된 상태에서 T-021~T-026을 실제 코드와 테스트로 마무리하는 것이다.

**구현 상세**:
- T-021: `kor-travel-geo-ui` 패키지를 추가했다. Next.js 16(App Router), React 18, Tailwind, TanStack Query, `react-kakao-maps-sdk`, OpenAPI 타입 생성 스크립트(`npm run gen:types`)를 포함한다.
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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q`
- `KTG_TEST_PG_DSN=... .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` — 실제 `data/juso` 샘플 COPY와 MV 생성 검증
- `cd kor-travel-geo-ui && npm ci && npm run gen:types && npm run lint && npm run type-check && npm run test && npm run build`
- `cd kor-travel-geo-ui && npm audit --omit=dev --audit-level=high`

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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- 임시 DB `kor_travel_geo_codex_pr11_followup`에서 `KTG_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q` 실행 → 실제 `data/juso` 샘플 COPY + MV 생성 1 passed.

**다음 작업**: PR #11에 후속 의견과 검증 결과를 남긴 뒤, 리뷰어가 원하면 payload schema를 OpenAPI DTO 수준에서 더 좁히는 작업을 별도 PR로 분리한다.

## 2026-05-23 (PR #11 리뷰 fixup — 라이브러리 batch DAG 비대칭 해소)

**작업**: PR #11 리뷰에서 발견된 라이브러리/REST 비대칭 이슈를 해결했다. `AsyncAddressClient.submit_load("full_load_batch", ...)`가 `AdminRepository.insert_load_job`을 직접 호출하던 경로를 `insert_load_batch`로 라우팅하여, 라이브러리 사용자도 REST `/v1/admin/loads`와 동일하게 root + 5종 child + DAG가 즉시 적재되도록 한다.

**구현 상세**:
- `src/kortravelgeo/infra/batch.py` 신규 모듈에 `BATCH_SOURCE_KINDS`와 `batch_children()`을 이동했다. `api/_jobs.py`의 동명 private 헬퍼는 제거하고 새 모듈을 import한다.
- `AsyncAddressClient.submit_load`는 `kind == "full_load_batch"`일 때 `batch_children(payload)`로 child 구성을 결정해 `AdminRepository.insert_load_batch`를 호출한다. 비-batch kind는 종전대로 `insert_load_job`을 사용한다.
- `infra/batch.py`는 `core/dto` 의존 없는 순수 모듈이라 client / api / loaders 어느 레이어에서도 import 가능. import-linter "Layered architecture" 컨트랙트 유지.

**검증**:
- `tests/unit/test_infra_batch.py` 신규 — default kind 순서, `payloads` 매핑 키, 명시 `children` 우선, 잘못된 entry drop을 검증.
- `tests/unit/test_client_submit_load_batch.py` 신규 — `AsyncMock`으로 `insert_load_batch` / `insert_load_job` 호출 분기를 검증.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest tests/unit/ -q` → 51 passed.
- `python -m ruff check`, `mypy --strict src/kortravelgeo/api/_jobs.py src/kortravelgeo/infra/batch.py src/kortravelgeo/client.py`, `lint-imports` 모두 통과.
- `python scripts/export_openapi.py --check` → drift 없음 (DTO 변경 없음).

**다음 작업**: T-021 프론트엔드 패키지 `kor-travel-geo-ui` 부트스트랩.

## 2026-05-23 (codex, T-018~T-020 구현 + 신규 PR 준비)

**작업**: PR #10 리뷰 fixup 위에서 T-018~T-020을 추가 구현하고, 사용자 요청대로 P1/P2 리뷰 반영 사항과 T-005~T-020 완료 범위를 하나의 신규 PR로 등록할 준비를 진행했다.

**구현 상세**:
- T-018: CLI 운영 명령을 확장했다. `ktgctl load all-sidos`는 juso/locsum/navi 필수 경로와 선택 SHP/epost 보조 경로를 받아 직접 적재 → 링크 해소 → C1~C10 정합성 검증 → optional MV refresh까지 묶는다. `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`도 추가했다.
- T-019: `infra/external_api.py`를 추가했다. `AsyncAddressClient.geocode(..., fallback="api")`는 로컬 DB 결과가 `NOT_FOUND`일 때만 외부 폴백을 호출한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 API + 좌표 API다. 외부 응답은 기존 `GeocodeResponse`로 변환하며 공급자 출처는 `x_extension.source`에만 둔다.
- T-020: `scripts/export_openapi.py`를 추가해 `create_app().openapi()`를 `openapi.json`으로 내보낸다. `--check` 모드는 committed schema와 생성 결과가 다르면 실패한다. `.github/workflows/openapi.yml`은 PR마다 `.[api]` extra 설치 후 drift 검사를 실행한다.

**문서**:
- `docs/tasks.md`에서 T-018~T-020을 완료로 이동했다.
- `docs/resume.md`의 다음 작업을 T-021 프론트엔드 부트스트랩으로 갱신했다.
- `docs/backend-package.md`에 외부 API fallback 흐름과 OpenAPI export/CI drift 절차를 명시했다.
- `docs/external-apis.md`에 구현 위치, 호출 순서, 응답 매핑 정책을 보강했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 51 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN` 미설정 시 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_t020_verify' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kor_travel_geo_codex_t020_verify` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/export_openapi.py` → 통과
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
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 47 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_pr10_fix' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed. 검증 후 `kor_travel_geo_codex_pr10_fix` DB는 삭제했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo` → 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept

**다음**: PR #10에 반영 요약과 검증 결과를 코멘트로 남긴다.

## 2026-05-23 (codex, T-005~T-017 일괄 구현 + 실제 파일/DB 검증)

**작업**: PR #7이 닫힌 뒤 최신 `origin/main`(`fa276dd`)에서 새 브랜치 `codex/t017-text-primary-load`를 만들고, ADR-012/ADR-016 기준으로 T-005부터 T-017까지 백엔드 1차 구현을 진행했다. 사용자의 추가 지시대로 `data/juso` 실제 파일을 반드시 열어 검증했고, 로컬 PostGIS에 별도 테스트 DB를 만들어 실제 샘플 COPY 적재와 MV 생성까지 확인했다.

**변경 파일(주요)**:
- 신규: `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_text_primary_postgis_schema.py`
- 신규: `src/kortravelgeo/infra/engine.py`, `infra/sql.py`, `infra/pnu.py`, `infra/geocode_repo.py`, `infra/reverse_repo.py`, `infra/search_repo.py`, `infra/zip_repo.py`, `infra/pobox_repo.py`, `infra/admin_repo.py`
- 신규: `src/kortravelgeo/core/protocols.py`, `core/normalize.py`, `core/geocoder.py`, `core/reverse_geocoder.py`, `core/searcher.py`, `core/zipcoder.py`, `core/poboxer.py`, `core/responses.py`
- 갱신: `src/kortravelgeo/client.py`, `src/kortravelgeo/__init__.py`, `src/kortravelgeo/dto/admin.py`, `src/kortravelgeo/cli/main.py`
- 신규: `src/kortravelgeo/api/app.py`, `api/_jobs.py`, `api/deps.py`, `api/responses.py`, `api/routers/*`
- 신규: `src/kortravelgeo/loaders/text/juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`, `loaders/shp/polygons_loader.py`, `shp/delta_loader.py`, `loaders/postload.py`, `loaders/consistency.py`, `loaders/pobox_loader.py`, `loaders/bulk_loader.py`, `loaders/manifest.py`
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
- 로컬 PostgreSQL(PostGIS)에서 `kor_travel_geo_codex_t017` 테스트 DB를 생성해 DDL 적용 → 실제 파일 샘플 COPY 적재 → `resolve_text_geometry_links()` → `mv_geocode_target` 생성까지 통과 확인 후 DB를 삭제했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 43 passed, 1 skipped. skipped 1건은 `KTG_TEST_PG_DSN`이 없을 때만 건너뛰는 선택형 실제 PostgreSQL COPY 테스트다.
- `KTG_TEST_PG_DSN='postgresql+psycopg://postgres:postgres@localhost:5432/kor_travel_geo_codex_t017' .venv/bin/python -m pytest tests/integration/test_optional_real_postgres_load.py -q` → 1 passed.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
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
- `docs/backend-package.md` §10 CLI — `ktgctl load juso/locsum/navi/shp`, `ktgctl validate consistency`, `ktgctl jobs list/status/cancel` 추가.
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
- 신규: `src/kortravelgeo/dto/geocode.py`, `src/kortravelgeo/dto/reverse.py`, `src/kortravelgeo/dto/search.py`, `src/kortravelgeo/dto/zipcode.py`, `src/kortravelgeo/dto/pobox.py`, `src/kortravelgeo/dto/admin.py`
- 신규: `src/kortravelgeo/loaders/juso_map.py`
- 신규: `tests/unit/test_dto_geocode.py`, `tests/unit/test_dto_reverse.py`, `tests/unit/test_dto_search_zipcode_pobox_admin.py`
- 신규: `tests/integration/test_juso_map_files.py`
- 갱신: `src/kortravelgeo/dto/__init__.py`, `pyproject.toml`, `docs/tasks.md`, `docs/resume.md`, `CHANGELOG.md`

**결정**:
- DTO는 `docs/backend-package.md` §4의 wire contract를 우선해 pydantic v2 frozen model로 작성했다.
- `type` 필드는 vworld/API wire field이므로 DTO 파일별로 `A003` ruff ignore를 한정 적용했다.
- pydantic runtime이 nested DTO 타입을 해석해야 하므로 `GeocodeResponse`, `ReverseResultItem`, `SearchResultItem`의 address DTO imports는 runtime import로 유지하고 해당 파일에만 `TC001` ignore를 한정 적용했다.
- GDAL 적재 구현은 T-013 범위로 남긴다. 다만 이번 작업에서 순수 Python으로 SHP/DBF 헤더를 직접 열어 `강원특별자치도/51000`의 11개 마스터 레이어와 `TL_SPBD_BULD` 필드(`BD_MGT_SN`, `BULD_MNNM`, `MVM_RES_CD`, `RN_CD`, `SIG_CD` 등)를 검증했다.

**검증**:
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 28 passed. 실제 파일 경로 `data/juso/도로명주소 전자지도/강원특별자치도/51000/*.shp|*.dbf|*.shx`를 열어 검사함.
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
- `.venv/bin/lint-imports` → Layered architecture kept

**다음**: T-005 — `infra/engine.py` async engine factory + 통합 테스트 준비.

---

## 2026-05-23 (claude, epost 데이터셋 정책)

**작업**: 우편번호 외부 API 활용 정책을 ADR-009로 확정하고 관련 문서 보강.

**변경 파일**:
- `docs/decisions.md` — ADR-009 추가 (epost 15000302, `downloadKnd=1` 분기 1회 전체 적재. 실시간 lookup 15056971 미도입).
- `docs/external-apis.md` — epost 절 보강: 데이터셋 ID 15000302, `downloadKnd` 4종 표, 분기 1회 전체 적재 흐름, 미도입 API(15056971) 명시. 한눈에 표에도 데이터셋 ID + ADR 인용.
- `docs/data-model.md` — `postal_pobox`/`postal_bulk_delivery` 위에 epost 15000302 ZIP 적재 출처와 ADR-009 인용.
- `.env.example` — `KTG_EPOST_API_KEY` 위 주석에 데이터셋 ID + ADR-009 표기.
- `CHANGELOG.md` — `### Added`에 ADR-009 요약.

**결정**:
- ADR-009: 우편번호 매칭은 epost 데이터셋 15000302의 전체 ZIP(`downloadKnd=1`)을 **분기 1회** 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE → INSERT. 변경분 누적 미운영. 실시간 lookup API(데이터셋 15056971) 미도입.

**검증**:
- 본 실행 환경(원격 컨테이너)은 `openapi.epost.go.kr` 외부망이 차단되어 직접 호출은 못 했다. 데이터셋 ID와 `downloadKnd` 4종 정의는 공공데이터포털 검색 결과로 확정. 사용자 WSL 환경에서 키 재발급 후 `curl ... -G --data-urlencode "downloadKnd=1"`로 응답을 마지막 점검 권장.
- 사용자가 채팅에 노출한 서비스 키는 즉시 재발급(또는 활용중지) 권장. 본 PR/문서/`.env.example`에 평문 커밋 없음.

**다음**: T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 시 본 ADR을 reference로 적용. CLI에 `ktgctl load epost --kind=full` 같은 entry를 두고 운영은 systemd timer로 분기 트리거.

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
- 갱신: `src/kortravelgeo/settings.py`, `tests/unit/test_settings.py`, `docs/backend-package.md`

**결정**:
- `reset_settings()`는 인자 없이 싱글톤을 비우는 역할만 맡는다.
- 테스트나 명시 주입이 필요할 때는 `set_settings(settings)`를 사용한다.

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex, 리뷰 2차 반영)

**작업**: PR 리뷰 항목 5~10 반영 — DTO 필수성, validator 범위, CLI exit, ruff ignore, 예외명, namespace package 정리

**변경 파일**:
- 갱신: `src/kortravelgeo/dto/address.py`, `src/kortravelgeo/cli/main.py`, `src/kortravelgeo/exceptions.py`, `pyproject.toml`
- 갱신: `tests/unit/test_dto_address.py`, `tests/unit/test_exceptions.py`
- 갱신: `docs/backend-package.md`, `docs/decisions.md`
- 삭제: `src/kortravel/__init__.py`

**결정**:
- `RefinedAddress.structure`는 사양대로 필수 `AddressStructure`로 둔다.
- 빈 문자열 → `None` 변환 validator는 optional address fields에만 적용하고, `level0`은 빈 문자열을 명시적으로 거부한다.
- `typer.Exit`는 인스턴스(`raise typer.Exit()`)로 raise한다.
- `N815` ruff ignore는 vworld 호환 필드가 있는 `dto/address.py`에만 한정한다.
- base 예외명은 `KorTravelGeoError`로 확정한다(ADR-014).
- `kortravel` parent는 PEP 420 implicit namespace package로 둔다(ADR-015).

**다음**: 기존 다음 작업 유지 — T-004 나머지 DTO 작성.

---

## 2026-05-23 (codex)

**작업**: PR 리뷰 반영 — 설정 기본값을 사양과 맞추고 README에 법적·데이터 사용 한계 추가

**변경 파일**:
- 갱신: `src/kortravelgeo/settings.py`, `.env.example`, `tests/unit/test_settings.py`, `README.md`

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
- 신규: `src/kortravel/__init__.py`, `src/kortravelgeo/__init__.py`, `src/kortravelgeo/version.py`, `src/kortravelgeo/py.typed`
- 신규: `src/kortravelgeo/settings.py`, `src/kortravelgeo/exceptions.py`, `src/kortravelgeo/client.py`, `src/kortravelgeo/cli/main.py`
- 신규: `src/kortravelgeo/dto/common.py`, `src/kortravelgeo/dto/address.py`
- 신규: `tests/unit/test_settings.py`, `tests/unit/test_dto_common.py`, `tests/unit/test_dto_address.py`
- 갱신: `CHANGELOG.md`, `docs/tasks.md`, `docs/resume.md`

**결정**:
- import-linter는 도구 제약상 `root_package = "kortravel"`와 `containers = ["kortravelgeo"]` 조합으로 설정한다. 이는 문서의 `kortravelgeo` 계층 계약과 같은 의미이며 실제 도구 실행이 통과하는 형태다.
- `AsyncAddressClient`와 CLI는 이번 범위에서 import/install 검증을 위한 자리표시자로만 둔다. 실제 지오코딩 기능은 T-010/T-011에서 구현한다.
- 사용자가 지정한 SHP 기준 경로 `data/juso/도로명주소 전자지도`를 확인했다. 강원도 샘플의 11개 DBF 필드는 문서의 마스터 레이어(`TL_SPBD_BULD`, `TL_SPBD_ENTRC`, `TL_SPRD_MANAGE` 등)와 맞는다.

**검증**:
- `pip install -e ".[dev]"` 통과
- `pip install -e ".[api,dev]"` 통과
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 10 passed
- `.venv/bin/python -m ruff check .` → 통과
- `.venv/bin/python -m mypy src/kortravelgeo` → 통과
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
- 식별자 통일: GitHub 저장소 = `kor-travel-geo`, Python import = `kortravelgeo`, CLI = `kor-travel-geo`, env prefix = `KTG_`, PostgreSQL DB = `kor_travel_geo`, 프론트엔드 패키지 = `kor-travel-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "kor-travel-geo"`, scripts `kor-travel-geo = "kortravelgeo.cli.main:app"`, importlinter `root_package = "kortravelgeo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kortravelgeo` 패키지의 PostgreSQL+PostGIS 재구현 + `kor-travel-geo-ui` 프론트엔드)을 master 문서에 반영

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

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kor-travel-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kortravelgeo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
