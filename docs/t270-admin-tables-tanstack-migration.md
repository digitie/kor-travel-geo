# T-270~ Admin UI 테이블 TanStack Table+Virtual 전환 (계획·범위·테스트)

상태: 진행 중 (Agent B/Claude) · 2026-06-17 · 사용자 지시: admin UI의 **모든 테이블**을
TanStack React Table + TanStack React Virtual 기반 공유 컴포넌트로 교체.

전제(디스커버리 결과, 8개 read-only 서브에이전트 분석):
- TanStack Table 8 / Virtual 3은 이미 설치됨. 공유 컴포넌트 `components/ui/VirtualTable.tsx`(T-254)가
  존재하나 **div CSS-grid(비-semantic)** 이고 grid 모드만 있다. 현재 소비자는 `backup-artifacts` 1개.
- admin 테이블 총 **27개**. 대부분 tiny(서버 cap ≤10~20행)라 가상화 이득이 없고, div-grid로 일괄 전환 시
  ① `<table>` a11y(role/scope) 퇴행, ② 테스트 2건 깨짐(`restore-reconcile.test.tsx` getByRole('table'),
  `source-files-matchset-compare.spec.ts` locator('tr')), ③ tiny 테이블에 불필요한 가상화·검색 toolbar.

## 결정된 아키텍처 (사용자 선택: semantic+grid 2모드)

`VirtualTable`을 **TanStack Table 기반 단일 공유 컴포넌트, 2개 렌더 모드**로 업그레이드한다.

- `as="table"`(semantic): 실제 `<table>/<thead>/<th scope="col">/<tbody>/<tr>/<td>`. 비가상화(전체 행 렌더).
  tiny·a11y 민감·`tr`/`role=table` 단언 테이블용. 기본값(소규모).
- `as="grid"`(virtualized): 현행 div CSS-grid + TanStack Virtual windowing. **ARIA roles 추가**
  (role=table/row/columnheader/cell, aria-sort). 대용량 리스트용(artifacts/groups 등).
- 두 모드 모두 **TanStack Table**(`useReactTable`)이 column def/정렬/global-filter를 구동 → "모든 테이블이
  TanStack Table 기반" 충족. 가상화는 grid 모드에서만(대용량). `virtualize?: boolean | 'auto'`.

확장 props(소비자별 필요, 디스커버리 gaps 기반):
- 선택: `selectable`, `selectedKeys`/`onSelectedKeysChange`, 헤더 select-all (reconcile-items, consistency).
- 행 상호작용: `getRowClassName(row)`(active/changed 강조), `onRowClick`.
- 셀: `VirtualColumn.align?`, `cellClassName?`, 테이블 `wrapCells?`(nowrap/ellipsis 해제 — pgStats query,
  table-description, path-cell).
- toolbar: `toolbarExtras?` 슬롯, 검색 없을 때 toolbar 생략(static).
- sticky 헤더(`<table>`/grid 모두), 선택적 `minWidth`+가로 스크롤, `footer`(추후 필요 시).
- 하위호환: 기존 `VirtualColumn`/props 유지 → `backup-artifacts`(grid)는 무변경 동작.

**예외(별도 처리)**: `resumable-upload-sessions`는 행마다 SSE 구독(ResumableSessionRow) → 비가상화
`as="table"`로만 전환(windowed 마운트 회피). 매우 대용량이 아니므로 안전.

## 변경 범위 (27개 테이블 verdict)

| 그룹 | 테이블 | 모드 | 비고 |
|------|--------|------|------|
| backups | backup-artifacts | grid(현행) | 이미 마이그레이션. ARIA roles만 보강. |
| backups | backup-jobs | table | 빈 상태 emptyHint, 취소 버튼 title='취소' 보존. JobProgress 카드 유지. |
| backups | pg-table-stats(TableStatsPanel) | table | sort/search 추가(원시 숫자 sortValue). |
| backups | restore-reconcile-rowcounts | table | 카드당 1개. getByRole('table') 테스트 통과 유지. caption/th scope. |
| ops | 7개(releases/snapshots/windows/table-stats/pg-stat/artifacts/audit) | table | tiny. pg-stat query·windows reason는 wrapCells. StatusBadge 셀 유지. |
| consistency | consistency-samples | table | 선택(checkbox)+단일선택(링크)+active-row. **서버 Pager 유지**(클라 검색/정렬 OFF). |
| consistency | perf-benchmark-summary | table | tiny. .perf-delta 셀 클래스 보존. |
| source-files | groups(ListTab) | table | 행 액션(재검증)·StatusBadge·groupId 툴팁 보존. |
| source-files | MatchSetCategorySummary + 3×SourceMatchSetItem | table | tiny. 공유 표현 컴포넌트로 통합 가능. |
| source-files | reconcile-runs/issue-items/capacity(ReconcileTab) | table | 선택/select-all/active-row. colspan 빈 행→emptyHint. |
| source-files | matchset-compare setmeta/items(MatchSetComparePanel) | table | items: `tr` 단언 통과 유지(semantic). setmeta: 행-헤더 key/value. |
| source-files | resumable-upload-sessions(UploadTab) | table(비가상) | 행별 SSE. |

비-테이블(제외): cache 메트릭 카드, logs `<pre>`, load 스텁, 각종 `<dl>`/카드 리스트.

## 코드·동작 영향
- 공유 컴포넌트 1개 업그레이드(하위호환) + 위 컴포넌트들의 `<table>` JSX를 `VirtualTable` 호출로 치환.
- wire/백엔드 영향 없음(순수 프론트). 데이터 fetch·라우팅 불변.
- a11y: table 모드는 semantic + `<th scope>`/caption로 **개선**. grid 모드는 ARIA roles 추가로 개선.
- 시각: tiny 테이블은 toolbar/검색/고정높이 없는 static 렌더(현행과 동일 룩 유지). nowrap 셀은 필요한 곳만 wrap.

## 세부 task
- **T-270** 공유 컴포넌트 업그레이드(2모드·ARIA·선택·active-row·align/wrap·toolbarExtras·sticky)+단위테스트. (foundation, 본 PR)
- **T-271** OpsPanel 7테이블 → table 모드 + 행/셀 e2e 신규(현재 0).
- **T-272** backups: backup-jobs·TableStatsPanel·restore-reconcile → table 모드.
- **T-273** source-files ListTab(groups+MatchSetCategorySummary)+3×SourceMatchSetItem → table(공유 item 컴포넌트).
- **T-274** source-files ReconcileTab(3)+MatchSetComparePanel(2)+UploadTab sessions → table 모드(+선택/active-row, tr 단언 유지).
- **T-275** ConsistencyPanel samples(+선택·Pager 유지)+PerfValidationSummary benchmark → table 모드.
- **T-276** (테스트 플랜 재점검 후) e2e 신규 커버리지 + 회귀 업데이트, Playwright 실행.

각 마이그레이션 task는 독립 컴포넌트라 서브에이전트로 병렬 가능(공유 컴포넌트는 T-270에서 고정 후).

## 테스트 플랜 (개요 — e2e 전 재점검·task화 예정 = T-276)
- 단위: `tests/unit/virtual-table.test.tsx` 확장 — table/grid 모드, 정렬(asc▲→desc▼→none), global-filter+count,
  선택(toggle/select-all), active-row className, emptyHint(API-empty vs 검색-no-match), wrapCells, ARIA roles,
  semantic table(`getByRole('table')`/`columnheader`/`row`). jsdom offsetHeight stub 패턴 재사용.
- 회귀(반드시 보존): backups artifact 검색(getByLabel '목록 검색'), 취소 getByTitle('취소'), consistency '#N' 버튼+Pager,
  matchset-compare `tr` 단언(semantic 모드라 통과), span.status/.perf-delta 셀 클래스, 각 빈 상태 문구(emptyHint로 이전).
- e2e 신규(작은 부분까지): 마이그레이션된 각 surface별 — 정렬 토글, 패널-scoped 검색+count, 빈 상태, (대용량 fixture로)
  grid windowing(DOM 행 수 << total), 셀 내 액션 a11y(접근명 보존), 다중 테이블 페이지의 '목록 검색' strict-mode 중복 방지(패널 scope).
- 게이트: 매 task마다 type-check/lint/(vitest)test/build + 본 surface e2e(Windows Playwright). 백엔드 openapi --check 무영향.

## 위험·완화
- e2e 깨짐: `tr`/`role=table`는 semantic 모드로 통과 유지. 빈 상태 문구는 emptyHint로 정확히 이전. 다중 검색 input
  strict-mode → 패널 scope 규약. 셀 액션 selector(title/label/role)는 셀 렌더에서 접근명 보존.
- SSE 행: 비가상 table 모드로 회피.
- consistency 서버 페이징: VirtualTable 클라 검색/정렬 OFF + 외부 Pager 유지(가상화로 대체하지 않음).
