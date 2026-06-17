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

T-177 파일 기반 full-load e2e 재검증에 들어가기 전, 2026-06-16 이후 PR에서 발견한
Claude Code 리뷰 후속을 먼저 닫는다. T-110~T-176(데이터 원천 보강·성능·정확도)과
T-200~T-276(데이터 적재/백업/복원 + Admin UI)은 모두 완료됐고, T-153 최종 안정화
acceptance도 닫혔다(`tasks-done.md`). 남은 항목은 아래 리뷰 후속, 선택적 후속, 외부 조건
보류다.

### 선행 리뷰 후속

- [ ] **T-178c** — 번호형 가지도로 파싱 회귀 방지(#336).

  PR #277 Claude Code 코멘트 후속. `테헤란로1길 10`, `올림픽로35길` 같은 번호형 가지도로가
  도로명/건물번호로 잘못 분리되지 않도록 정규화/파싱 테스트와 최소 보정을 추가한다.

- [ ] **T-178d** — `DBAPIError` handler 오류 분류 보정(#336).

  PR #266 Claude Code 코멘트 후속. transient 연결/운영 DB 장애와 `ProgrammingError`·
  `IntegrityError` 같은 버그성 오류가 같은 503 재시도 가능 오류처럼 보이지 않도록 API
  error handler 분류와 테스트를 보강한다.

- [ ] **T-178e** — `ops.pg_stat_statements_snapshots` retention/prune 정책(#336).

  PR #253 Claude Code 코멘트 후속. 저사양 운영에서 pg_stat snapshot이 무한 증가하지 않도록
  retention 설정, pruning 실행 지점, 단위/통합 테스트를 추가한다.

- [ ] **T-178f** — RustFS HEAD 오류/size 판정 정직화(#336).

  PR #290 Claude Code 코멘트 후속. RustFS HEAD 오류를 모두 missing으로 뭉개지 않고,
  `content-length` 부재를 size `0`으로 처리하지 않도록 `head_object`와 restore-source
  reconcile 경로를 보강한다.

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
