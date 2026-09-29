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

## 현재 세션 상태 (2026-09-01)

- ✅ **T-304** — Prometheus 계측 경계와 Geocoder Admin UI 브랜딩을 보강했다. n150 API/UI
  Docker 재배포, 실제 Prometheus target/query 확인, 인증 포함 Chromium live E2E(31/31)를
  완료했으며 PR #544 merge를 진행한다.
- ✅ **T-297** — 디스크 위험 사후 조치를 완료 처리했다. 남은 재발 방지 검토는 낮은 우선순위
  후속으로 보존한다.
- ✅ **T-299** — blue 색상톤을 유지한 상태에서 색각 구분성·상태 의미 전달을 검토하고, 상태 dot과
  텍스트를 공통 배지에 반영했다. 운영 Chromium live 검증까지 완료했다(31/31 통과).
- ✅ **T-300** — 공통 포커스 링의 비텍스트 대비·키보드 이동·메뉴/테이블 포커스를 보완하고,
  정합성 판정 모달의 닫힘 후 트리거 복귀까지 반영했다. 운영 Chromium live 검증까지 완료했다(31/31 통과).
- ✅ **T-303** — 최신 `kor-travel-map` 기준 메인 콘텐츠·공용 컴포넌트·메뉴·반응형 표면을
  전체 동기화했다. 기존 blue 색상톤을 유지하고 운영 UI 검증과 인증 포함 live E2E(31/31)를 완료했다.

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

### T-308 공용 instance 이전 후속 (2026-09-28 사고 조사에서 나온 것)

근거와 증거는 `docs/journal.md` 2026-09-28·2026-09-29 항목. T-309~T-318은 2026-09-29에 완료
(`tasks-done.md`). 아래는 그 리뷰에서 나온 후속이다. 우선순위 순.


- [ ] **T-323** — T-319 리뷰 잔여 minor: sppn 전체 재적재가 TRUNCATE 뒤 실패하면 manifest row는
  지워졌지만 active serving release fallback이 이전 기준월을 돌려준다(빈/부분 테이블인데 이전 월).
  fallback을 "테이블에 행이 있고 manifest가 없을 때"로 좁히거나(`EXISTS … LIMIT 1`), 실패한 재적재를
  release에 기록하지 않게. 영향은 sppn 재적재 실패 뒤 다음 refresh/백업의 `sppn_makarea` 기준월 1건.
- [ ] **T-322** — Dagster instance storage 드라이버를 `postgresql+psycopg2://`로 명시(manager 담당과 조율).
  **검증 완료**(2026-09-29, 상세·실측 표·소스 근거는
  [`t322-dagster-storage-driver.md`](t322-dagster-storage-driver.md)): dagster_postgres는 pin 범위
  (0.25~0.29.24) 전체에서 URL을 `psycopg2.connect`/libpq에 넘기는 런타임 경로가 없고(event watcher는
  SQLAlchemy polling), `postgresql+psycopg2://`는 SQLAlchemy 2.0·2.1 모두 end-to-end 통과. psycopg 3은
  NOTIFY bind·webserver `with conn:`(연결을 닫는다)·`.pgcode`로 **미지원** — 2.1로 가는 길은 드라이버 명시뿐.
  `postgres_db:` 형식은 기본 scheme이 `postgresql`이라 단독으로는 해법이 아니다. 남은 운영 절차:
  1. (manager) n150 `.env`의 `KOR_TRAVEL_GEO_DAGSTER_PG_URL` scheme만 `postgresql://` →
     `postgresql+psycopg2://`(user/password/host/port/db 동일). manager `.env.example` 153·465행·문서 예시도.
     현재 이미지(SQLAlchemy 2.0.54)에서는 같은 드라이버라 동작 변화 0, DB migration·재build 불필요.
  2. 적용 전 Dagster에 STARTED/STARTING run이 0건인지 확인(run은 code-server 안의 자식 프로세스라 재생성 시 끊긴다).
  3. 세 서비스만 재생성: `kor-travel-geo-dagster-code-server`, `kor-travel-geo-dagster`,
     `kor-travel-geo-dagster-daemon`(env는 재생성 때만 반영).
  4. 검증: 세 컨테이너 healthy, 컨테이너 안 `KTG_DAGSTER_PG_URL` scheme이 `postgresql+psycopg2`, webserver
     GraphQL `runsOrError`가 200(healthcheck의 `repositoriesOrError`만으로는 부족 — DB가 깨져도 200이다),
     `dagster-daemon liveness-check`, 다음 `scheduled_backup` run-due tick run이 SUCCESS.
  5. 롤백: 값을 `postgresql://`로 되돌리고 같은 세 서비스 재생성.
  6. (그 뒤, 선택) `sqlalchemy<2.1` pin 해제는 별도 PR로만 — 조건: 1~4 완료, code location import 시
     storage URL 드라이버가 psycopg2가 아니면 즉시 실패하는 guard(2.1 + bare URL은 healthcheck를 통과한 채
     run만 못 돈다), CI `dagster` job의 2.0 assert를 2.1로 바꿔 통과. 그전까지 pin 유지.

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
