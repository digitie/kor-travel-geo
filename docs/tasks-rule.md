# tasks-rule.md — task 문서 작성·유지 규칙

`docs/tasks.md` / `docs/tasks-done.md` 의 작성 규약 정본. task 문서를 **어떻게 쓰고
유지하는가**만 둔다. PR/리뷰 루프·두 에이전트 병행 운영 같은 **작업 진행(process)
규칙은 여기 두지 않는다** — `docs/runbooks/agent-workflow.md`(단계별 런북)와
`docs/agent-guide.md`를 본다.

## 1. 세 문서의 역할

| 문서 | 역할 |
|------|------|
| [`docs/tasks.md`](tasks.md) | 열린 `[ ]`(진행 중/대기/보류) 백로그 + 상단 포인터 |
| [`docs/tasks-done.md`](tasks-done.md) | 완료 `[x]`·종료(no-go/no-action)·아카이브 history (newest-first) |
| [`docs/resume.md`](resume.md) | 현재 진척 + "다음 한 작업" (진척 **정본**) |

- 현재 상태·세션 연속성의 최상위 정본은 [`CLAUDE.md`](../CLAUDE.md)이며, 진척 서술은
  `resume.md`가 정본이다. `tasks.md`에 상태 스냅샷을 길게 중복하지 않는다.

## 2. tasks.md ↔ tasks-done.md 분리 규칙

- 블록(섹션/Phase) 단위로 라우팅: 열린 `[ ]`가 하나라도 있으면 `tasks.md`,
  전부 닫혔으면(`[x]`/종료) `tasks-done.md`.
- 완료 task를 `tasks.md`에 길게 남기지 않는다 — 완료 확인 후 `tasks-done.md`로
  옮긴다(이동 시 남은 열린 항목 count를 보존한다).
- 진척 서술은 `resume.md`가 정본 — `tasks.md`에 상태 스냅샷을 중복하지 않는다.

## 3. task ID 스킴

- 기본: `T-NNN` 연번 (예: `T-153`, `T-276`).
- 하위 작업: `T-NNN<letter>` (예: `T-213a`~`h`, `T-218a`~`f`).
- 잔여/파생/한정자: `T-NNN <식별구>` (예: `T-219 M4`, `T-219 잔여 L`, `T-105 audit`).
- 종료 표기: `T-NNN 종료(no-go)` / `T-NNN 종료(no-action)`.

### 번호 배정 순서 (ADR-050)

새 작업 ID는 다음 우선순위·번호대 규칙으로 배정한다.

① 데이터 원천 보강·검증(**T-110~**) → ② 데이터 적재/백업 기능 구현·검증(**T-200~**) →
(최하위 우선순위) v2 재audit(**T-105**) · v1 vworld 100% 호환(**T-106**).

- 원천 보강은 T-110부터 1씩, 적재/백업은 T-200부터 1씩 올리고, 중간에 추가되는
  작업은 각각 T-1xx / T-2xx 번호로 채운다.
- 번호 규칙: **T-1xx = 성능/기능/geocoder/안정성**, **T-2xx = Admin UI + 데이터
  적재/백업/복원**.
- T-105/T-106은 ID는 낮지만 우선순위는 **최하위**다.
- 이미 `journal.md`/`tasks-done.md`에서 참조 중인 ID는 재번호하지 않는다.
- 단위별 상세 scope·의존성·근거는 ADR-050과
  `docs/t109-backup-source-upload-management.md`의 구현 순서 절에 있다.

## 4. status 마커

- `[ ]` 미완료 · `[x]` 완료 · `[~]` 부분완료(하위 일부 완료).
- 완료/종료 항목 내 해소·철회 표기: `✅`(해소) · `~~취소선~~`(철회).
- 외부 조건으로 진행 불가한 항목은 "보류 (외부 조건)" 블록에 둔다.

## 5. 표준 entry 형식

```markdown
- [ ] **T-NNN[<letter>|<식별구>]** — <짧은 제목> (<범위/담당 표시, 선택>)

  <1~3문장: 무엇을·완료 조건·정본 리포트 링크.>
```

- 모든 backlog 항목은 `[ ]` 체크박스를 단다(상단 포인터 포함).
- 완료/종료 항목은 `tasks-done.md`에서 `- [x] **T-NNN** — … (YYYY-MM-DD)` 형식으로,
  완료/종료 일자를 끝에 붙여 newest-first로 누적한다.
- task당 상세 위치는 하나 — 인덱스/포인터는 참조만 하고 본문을 중복하지 않는다.

## 6. 인덱스/상세 정합

- `tasks.md` 상단 포인터의 열린 `[ ]`와 하위 상세 섹션은 일치해야 한다.
- 외부 저장소 작업은 본 저장소에서 직접 실행하지 않는 한 "외부 추적"으로만 둔다.
- 보류 항목은 도입 조건(외부 하드웨어 등)이 충족되기 전까지 잔여로 계산하지 않는다.

## 7. 완료 처리 워크플로

완료/종료 → `tasks-done.md` 상단에 요약 아카이브(완료/종료 일자 표기) + `journal.md`
엔트리 + `resume.md` 갱신. 정본 리포트가 있으면 `docs/` 또는 `docs/reports/...`로 링크한다.
