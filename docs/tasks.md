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

## 진행 중

- **진행 중 작업 없음.** (T-270~T-276 Admin UI 테이블 TanStack 전환 완료 — `tasks-done.md`
  참조. T-276 e2e는 PR #327에서 머지.)

## 대기

> 번호 배정 순서·ID 스킴(ADR-050)은 [`docs/tasks-rule.md`](tasks-rule.md) §3을,
> 두 에이전트 병행 권장 순서·병행 운영 원칙(PR/리뷰 루프)은
> [`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다.

T-178a~T-178f Claude Code 리뷰 후속은 모두 닫혔다. 이제 T-177 파일 기반 full-load e2e
재검증을 진행한다. T-177은 T-073 shell script에 맞추지 않고, opt-in pytest 통합/e2e가 실제
파일을 읽어 scratch PostgreSQL DB를 구축하는 방향으로 진행한다. 상세 계획과 Task 분해는
[`docs/t177-file-driven-full-load-e2e-plan.md`](t177-file-driven-full-load-e2e-plan.md)가 정본이다.

### 선행 리뷰 후속

- **진행 중 작업 없음.** (T-178a~T-178f Claude Code 리뷰 후속 완료 — `tasks-done.md` 참조.)

### T-177 파일 기반 full-load e2e

- [ ] **T-177B** — opt-in e2e 하니스와 destructive preflight.

  `KTG_TEST_FULL_LOAD_E2E`, `KTG_TEST_PG_DSN`, typed confirmation, DB 이름 allowlist,
  data-root discovery artifact를 갖춘 공통 pytest fixture를 만든다. DB 구동/정지는 하지 않고,
  scratch DB에만 schema/index 적용 smoke를 수행한다.

- [ ] **T-177C** — 텍스트 정본과 daily delta DB 구축 e2e.

  실제 도로명주소 한글, 지번 연결, daily MST/LNBR, 위치정보요약DB, 내비게이션용DB 파일을
  loader API로 읽어 DB에 적재한다. Row count, `load_manifest`, 기준월, 링크 해소 전후 수치를
  artifact로 고정한다.

- [ ] **T-177D** — 전자지도 SHP/PostGIS geometry e2e.

  실제 도로명주소 전자지도 selected 시도 SHP 9개 레이어를 읽어 PostGIS 테이블에 적재한다.
  GDAL 부재 시 skip하고, SRID, geometry validity, source file/source yyyymm, 주요 row count를
  검증한다.

- [ ] **T-177E** — 선택 보강 원천 e2e.

  도로명주소 출입구 정보와 `TL_SPPN_MAKAREA`를 실제 파일에서 읽어 선택 보강 테이블에
  적재한다. Same-month gate, SPPN geocode/reverse smoke, 기준월 혼합 warning 표면을 검증한다.

- [ ] **T-177F** — post-load serving, smoke, consistency e2e.

  T-177C~E 적재 DB를 바탕으로 text-geometry link, serving MV, geocode/reverse/search/zipcode
  smoke, C1~C10 consistency subset report를 검증하고 실패 sample artifact를 남긴다.

- [ ] **T-177G** — 전국 long-run full-load e2e.

  별도 `KTG_TEST_FULL_LOAD_E2E_LONGRUN=1` opt-in으로 전국 실제 원천 전체를 읽어 DB를 구축한다.
  Phase별 wall time, row count, DB size, source month summary, 실패 재개 지점을 artifact로 남긴다.

- [ ] **T-177H** — T-047 benchmark와 최종 acceptance report.

  전국 long-run DB를 기준으로 SQL/REST benchmark hook, p95/p99, error count, slow plan,
  `pg_stat_statements` snapshot을 수집하고 최종 acceptance 문서를 갱신한다.

### 선택 후속 (낮은 우선순위)

- [ ] **T-219 잔여 L** — v1 VWorld 호환 minor 후속(선택). M1~M5는 모두 완료
  (M5+M1=#306, M2/M3=#314, M4=#305/ADR-061; `tasks-done.md`). 남은 minor L만 선택
  후속으로 둔다:
  - (1) Starlette 404/405가 v1에서 unwrapped로 누출.
  - (2) 좌표 bounds 텍스트 영어 하드코딩(validation 메시지는 한글)·동일 `INVALID_RANGE`
    코드 불일치.
  - (3) v1 docs/ADR-053에 `service.version`·에러 `response.service`/`response.status`
    명시.
  - (4) 비-address 경로(admin/zipcode/pobox/`regions/within-radius`) OpenAPI
    `422`→`400` 명세 정합(ADR-061 §5, pre-existing drift).

  v1 vworld 호환(ADR-038) 변경 금지.

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL benchmark, REST benchmark, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
