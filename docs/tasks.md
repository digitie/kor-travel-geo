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

근거와 증거는 `docs/journal.md` 2026-09-28 항목. 우선순위 순.

- [ ] **T-314** — 백업 커버리지 복구 + 이관본 검증. 09-19 이후 geo 백업 0건(T-307 launch
  회귀). 공용 instance 이관본(09-24/25 무기록 data-only 이관)과 옛 PGDATA/09-19 아카이브의
  테이블별 row count 대조 → 검증된 새 백업 1건 확보 → 그 뒤에만 09-19 아카이브와 옛 PGDATA
  (`/home/digitie/kor-travel-geo-data/pgdata-final-20260529`, 32.8GB) 정리. `scheduled_backup`
  재개 여부 결정(Dagster schedule STOPPED, API run-due 경로는 launch 복구로 다시 동작).
- [ ] **T-309** — DB 오류 분류 정정. `QueryCanceled`(57014)가 `OperationalError` 하위라
  statement timeout이 "check KTG_PG_DSN" 503으로 보인다(`api/responses.py:186-188`) — timeout을
  별도 코드/문구로, connect-time permission denied도 구분. UI(`GeocodeDebugger.tsx`,
  `lib/api.ts getErrorMessage`)가 v2 envelope를 파싱해 한국어로 표시. serving MV가 비어 있으면
  `/v1/readyz`·관리 홈이 degraded를 보이게.
- [ ] **T-310** — `/metrics`와 Cache 패널의 `geo_cache` 전수 scan 제거(15초 scrape마다 공용
  instance 논리 읽기의 대부분) — `reltuples`/TTL 캐시로. `pg_stat_statements` capture를
  `userid = current_user`로 한정하고 주기 완화. 09-28 확인 시 API 기동(09-25) 이후
  `ktg_api_db_errors_total{route="/metrics"}`가 `OperationalError` 234건 — scrape 실패 원인도 같이 본다.
- [ ] **T-317** — 지번 geocode 누락 2건(T-308 검증 중 발견, 이관 전부터 있던 코드 동작 — MV 데이터는
  정상). (1) `core/normalize.py` `parse_address`가 "N가" 법정동(`태평로1가`, `종로1가`)을 도로
  `태평로`+번호 1로 읽어 `서울특별시 중구 태평로1가 31`(MV에 행 있음)이 `jibun_address`로도
  NOT_FOUND. (2) v2 `query` 자유 입력은 `client.py`에서 항상 `type="road"`라 지번 문자열
  (`성남시 분당구 삼평동 681`)이 약 3초 뒤 NOT_FOUND — 같은 값을 `jibun_address`로 주면 OK.
  `parse_address(...).is_road`가 False면 parcel 조회를 시도하게.
- [ ] **T-311** — road fallback(`infra/geometry_repo.py` `_ROAD_GEOMETRY_SQL`) 비용 개선:
  인덱스 쓸 수 있는 정규화 도로명 조건(trigram) 또는 완전 도로명주소면 생략. MV가 채워져도
  supplemental/NOT_FOUND 경로가 매 요청 ~5초를 더한다.
- [ ] **T-312** — 공용 instance에서 불가능한 DB 수명주기 기능 차단: hot-swap plan/execute/rollback
  (`postgres` DB CONNECT 필요), restore-drill·scratch full-load·replace_current restore
  (`CREATE DATABASE` 필요)를 capability flag로 막고 UI에서 숨긴다. app role로 복원 가능한 백업
  형식(`--no-owner/--no-privileges`, extension TOC 필터).
- [ ] **T-313** — 코드 기본 DSN(`Settings.pg_dsn`, `alembic.ini`)이 은퇴한 `12500`을 가리킨다 —
  공용 instance 기준으로 정리(테스트 기대값 포함).
- [ ] **T-315** — geo-api/geo-ui를 `/opt` docker-manager 트리에서 재배포(현재 홈 트리 소유, 그
  compose는 은퇴한 `kor-travel-geo-postgres`를 `depends_on`). manager 담당과 조율.
- [ ] **T-316** — SQLAlchemy 2.1 업그레이드 검토(#551에서 `<2.1` 고정 — 2.1.1이 mypy 추론을
  깨고 하위 호환 변경 포함).

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
