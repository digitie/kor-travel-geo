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

- **진행 중 작업 없음.** (T-177A~T-177H와 T-183 live UI full-load e2e 완료 —
  `tasks-done.md` 참조.)

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

### 선행 리뷰 후속

- **진행 중 작업 없음.** (T-178a~T-178f Claude Code 리뷰 후속 완료 — `tasks-done.md` 참조.)

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
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
