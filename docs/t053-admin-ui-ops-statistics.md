# T-053: Admin Web UI 운영/유지보수/관리/튜닝 표면 보강 + C1~C10 상세 분석 UI

## 상태

- 상태: 설계 (구현 전)
- 대상 브랜치: `agent/<agent>-t053-*`
- 사용자 RFC: 2026-05-27 — "web UI는 유지보수 목적으로도 쓰임. 관련해서 기능 보완(통계/유지보수/관리/튜닝). TanStack Query, Zustand 활용. C1~C10 데이터를 별도의 테이블에 적재하고 UI를 통해 직접 눈으로 보거나 상세 분석을 할 수 있게 상세 분석 UI 및 CSV 형태로 빼서 볼 수 있도록 UI에 반영."

## 목적

`kraddr-geo-ui`는 현재 디버그(`/debug/*`)와 기본 관리(`/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`, `/admin/backups`, `/admin/ops`)로 구성된다. 본 task는 운영자가 "실제 운영 콘솔"로 쓸 수 있도록 다음 4개 표면을 보강한다.

1. **통계**(`/admin/stats`): row count 추이, 적재/응답 metrics, geo_cache hit ratio, 외부 provider 호출 분포.
2. **유지보수**(`/admin/maintenance`): vacuum/analyze 트리거, index health, table bloat, dead tuple 추이.
3. **관리**(`/admin/ops` 보강): T-049 ops 메타데이터(`snapshots`, `releases`, `artifacts`, `audit-events`, `maintenance-windows`)를 단순 list가 아니라 cross-reference + 액션 가능한 콘솔로.
4. **튜닝**(`/admin/performance` 보강): T-047 benchmark 결과를 시계열로 보고, 보조 view/MV 도입 효과를 GUI에서 직접 비교.

추가로 **C1~C10 정합성 분석 UI**를 별도 표면으로 정리한다. 현재 `load_consistency_reports.cases` JSONB에 sample/metric이 묶여 있어 SQL 없이는 case별 deep dive가 어렵다. 본 task에서는 case sample을 별도 테이블에 분리 적재하고, UI에서 sort/filter/map/CSV export까지 직접 수행할 수 있게 한다.

## 기술 stack 결정

- **TanStack Query v5**: server state(REST API 응답, polling, refetch, mutation). 이미 부트스트랩되어 있다(T-021).
- **Zustand**: client-only state(현재 보고 있는 case id, filter, CSV column 선택, modal open/close 등 ephemeral UI state). React Context 대신 zustand로 통일.
- **TanStack Table v8**: 큰 dataset(특히 C1~C10 sample 수만~수십만 행) sort/filter/pagination/virtualization.
- **MapLibre GL + maplibre-vworld**: 정합성 sample을 지도 위에 표시(T-044 domain wrapper 활용).
- **PapaParse**: 클라이언트 CSV export(브라우저 메모리 한계 내). 대용량은 backend `?format=csv` 응답 사용.

state separation 원칙:

```
server state (REST 응답, 캐시 가능)        → TanStack Query
URL state (현재 case, page, filter param) → URL search params + Next.js router
ephemeral UI state (modal, selection, etc) → Zustand
form state (controlled input)              → React local state + Zod validation
```

## C1~C10 정합성 결과 별도 테이블

### 현재 한계

PR #43에서 만든 `load_consistency_reports(report_id, scope, severity_max, source_set, cases JSONB, ...)`는 한 row가 한 리포트 전체를 담는다. `cases` JSONB 안에 case별 `{count, severity, sample[]}`이 있어 다음 작업이 어렵다.

- "전국 리포트에서 C4 sample만 distance 큰 순으로 정렬" — JSONB array unnest + sort 비용 큼.
- "최근 30일 C7 ERROR row 추세" — JSONB 안 sample row를 시계열로 집계 불가.
- "C2 sample에서 시군구별 분포" — JSONB 내부 group by 어려움.

### 신규 테이블

```sql
-- ops.consistency_case_samples
-- C1~C10 case sample을 row-per-record로 분리 적재
CREATE TABLE IF NOT EXISTS ops.consistency_case_samples (
  sample_id            UUID PRIMARY KEY,
  report_id            TEXT NOT NULL REFERENCES load_consistency_reports(report_id) ON DELETE CASCADE,
  case_code            TEXT NOT NULL CHECK (case_code ~ '^C(10|[1-9])$'),
  severity             TEXT NOT NULL CHECK (severity IN ('OK','INFO','WARN','ERROR')),
  bd_mgt_sn            TEXT,
  sig_cd               TEXT,
  bjd_cd               TEXT,
  distance_m           DOUBLE PRECISION,
  source_yyyymm        TEXT,
  -- case별로 의미가 다른 metric은 JSONB로 보존
  case_metric          JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- 좌표는 별도 컬럼 (지도 표시/공간 query용)
  point_4326           geometry(Point, 4326),
  point_5179           geometry(Point, 5179),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_consistency_case_samples_report
  ON ops.consistency_case_samples (report_id, case_code, severity);
CREATE INDEX idx_consistency_case_samples_case_severity
  ON ops.consistency_case_samples (case_code, severity, distance_m DESC);
CREATE INDEX idx_consistency_case_samples_sig
  ON ops.consistency_case_samples (sig_cd, case_code);
CREATE INDEX idx_consistency_case_samples_4326
  ON ops.consistency_case_samples USING GIST (point_4326);
```

### 적재 정책

- `run_all_cases()` 실행 시 기존 `load_consistency_reports.cases` JSONB는 그대로 채우고(요약), 동시에 `ops.consistency_case_samples`에도 row 단위 insert한다.
- sample 수는 케이스별 cap이 있다(예: case당 1,000건). cap을 넘으면 stratified sampling (시군구별 비율 유지).
- `ops` schema 정책상 secret/주소 원문 평문 저장 금지(ADR-033). `bd_mgt_sn`은 자체 식별자이므로 OK, 주소 텍스트는 저장하지 않는다.

### REST 표면

```text
GET  /v1/admin/consistency/{report_id}/cases/{case_code}/samples
       ?severity=ERROR&sig_cd=11&order_by=distance_m&desc=true&page=1&page_size=100
       Accept: application/json | text/csv

GET  /v1/admin/consistency/{report_id}/cases/{case_code}/summary
       — 시군구별 count, severity 분포, distance 통계
```

CSV export는 `Accept: text/csv` 또는 `?format=csv`. 100만 행도 streaming response로 안전.

## /admin 화면 4종 보강

### `/admin/stats` 통계

- row count 추이: `tl_juso_text`, `tl_locsum_entrc`, `tl_roadaddr_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc`, `tl_spbd_buld_polygon`, `mv_geocode_target`. T-049 `ops.table_stats_snapshots` 시계열 그래프.
- 적재 metrics: 최근 batch 처리 시간, child 별 phase 시간(T-033 phase timer 활용).
- geo_cache: hit/miss/expired ratio, top-N hit keys.
- 외부 provider: `geo_cache.source` 기준 vworld/kakao/naver 호출 비율.

기술: TanStack Query polling(30s) + Chart.js(또는 Recharts) 시계열.

### `/admin/maintenance` 유지보수

- index health: `pg_stat_user_indexes` 기반 idx_scan/idx_tup_read, bloat 추정.
- dead tuples: `pg_stat_user_tables.n_dead_tup`.
- 마지막 `VACUUM`/`ANALYZE` 시각.
- 액션 버튼:
  - `VACUUM (VERBOSE, ANALYZE) <table>` 트리거 → `load_jobs(kind="maintenance_vacuum")`.
  - `REINDEX INDEX CONCURRENTLY <index>` 트리거.
- 위험 액션은 `ops.maintenance_windows` active window 필요.

### `/admin/ops` 보강

T-049의 raw list를 그대로 두고, 다음 cross-reference view를 추가:

- snapshot → 연결된 release/artifact/consistency report/performance report를 한 화면에서 navigate.
- artifact → 다운로드/만료/체크섬 검증/연결 job 표시.
- audit event → action × outcome × actor × resource로 facet filter.
- maintenance window → 현재 active window가 차단 중인 작업 종류 표시.

### `/admin/performance` 튜닝

T-047 결과 연계:

- benchmark run 목록 + 시계열(p95/p99).
- 같은 query군의 baseline vs trial 비교.
- slow query sample 클릭 → 저장된 `EXPLAIN` plan JSON viewer.
- 후속 보조 view/MV 도입 전후 비교(refresh/swap 시간, 디스크, p95/p99).

## C1~C10 분석 UI

`/admin/consistency/{report_id}` 페이지를 확장한다. 좌측 case 목록, 우측 분석 영역.

### 우측 영역 탭

1. **Summary 탭**: case별 count, severity 분포, 시군구별 분포, distance histogram(C4/C5).
2. **Sample 탭**: TanStack Table — sample row의 `bd_mgt_sn`/`sig_cd`/`distance_m`/`source_yyyymm`/`severity` 정렬·필터·페이지. 행 클릭 시 우측 panel에 좌표 지도(MapLibre + maplibre-vworld) + 원본 row metadata.
3. **Map 탭**: 현재 filter된 sample을 한 화면에 지도로. cluster(MapLibre cluster source). zoom 14 이상에서 individual marker.
4. **Export 탭**:
   - "현재 filter CSV 다운로드" 버튼 → `Accept: text/csv` 호출, backend streaming.
   - "현재 filter JSON 다운로드" 버튼.
   - "현재 filter Markdown report" — case sample을 보고서 형태로.

### URL state vs Zustand 분리

- URL search params (`?case=C4&severity=ERROR&sig_cd=11&order=distance_desc`): bookmark 가능한 view.
- Zustand store (`useConsistencyAnalysisStore`): 지도 zoom/center, 선택된 sample id, side panel open, column visibility.

URL state는 SSR-safe하므로 Next.js Route Handler/Server Component에서도 hydrate 가능.

## TanStack Query 활용

- `useQuery(['consistency-report', report_id])` — report 메타.
- `useQuery(['consistency-samples', report_id, case_code, filter])` — paginated sample list. `keepPreviousData: true`로 pagination smooth.
- `useMutation(['run-consistency'])` — `POST /v1/admin/consistency/run`.
- `useInfiniteQuery` — map 탭의 viewport-based loading.

cache key는 `(report_id, case_code, filter_hash)`로 고정. filter는 URL params에서 직접 도출.

## Zustand 활용

```ts
// kraddr-geo-ui/lib/stores/consistency-analysis-store.ts
interface ConsistencyAnalysisState {
  selectedSampleId: string | null;
  mapZoom: number;
  mapCenter: [number, number];
  sidePanelOpen: boolean;
  visibleColumns: Set<string>;
  setSelected: (id: string | null) => void;
  setMapView: (zoom: number, center: [number, number]) => void;
  togglePanel: () => void;
  toggleColumn: (key: string) => void;
}

export const useConsistencyAnalysisStore = create<ConsistencyAnalysisState>()((set) => ({
  selectedSampleId: null,
  mapZoom: 7,
  mapCenter: [127.5, 36.5],
  sidePanelOpen: false,
  visibleColumns: new Set(["bd_mgt_sn","sig_cd","distance_m","severity"]),
  // ...
}));
```

같은 패턴으로:

- `useStatsViewStore` — 통계 화면 ephemeral state.
- `useMaintenanceConfirmStore` — 유지보수 액션 confirm modal.
- `usePerformanceCompareStore` — baseline vs trial selection.

## CSV export 정책

- 클라이언트 측 export: 100,000 row 이하 → 브라우저 메모리 OK, PapaParse 사용.
- 서버 측 export: 100,000 row 초과 → `Accept: text/csv` streaming response.
- column 선택: Zustand의 `visibleColumns` 그대로 CSV header에 반영.
- 한글 파일명: `Content-Disposition: attachment; filename*=UTF-8''C4_ERROR_20260527.csv`.
- BOM 추가(Excel 호환): `﻿`로 시작.

## 구현 순서

1. `ops.consistency_case_samples` DDL + Alembic migration.
2. `run_all_cases()` 변경 — sample row 별도 적재.
3. `/v1/admin/consistency/.../samples` REST endpoint + CSV streaming.
4. `kraddr-geo-ui/app/admin/consistency/[report_id]/page.tsx` 보강 — 4탭 구조.
5. `lib/stores/consistency-analysis-store.ts` + 다른 zustand store 추가.
6. `/admin/stats`, `/admin/maintenance` 신규 page.
7. `/admin/ops` cross-reference view 보강.
8. `/admin/performance` T-047 benchmark 연계.

## 검증 기준

- backend: `pytest`에서 `ops.consistency_case_samples` insert/select/CSV 응답 회귀.
- frontend: vitest로 zustand store reducer, TanStack Query key 생성, CSV column 선택 테스트.
- e2e (Windows Playwright): `/admin/consistency` 4탭 navigation, sample row 클릭 시 지도 표시, CSV 다운로드 button 동작.
- 운영: 실제 T-027 final clean load 결과 report에서 C4 ERROR 16건, C7 ERROR 6,817건이 sample 테이블에 row-per-record로 적재되는지 확인.

## 남은 위험

- `ops.consistency_case_samples`가 case당 1,000건 cap이라도 전체 10 case × 다중 report로 누적되면 수십만 row. retention 정책 (예: 90일 ttl 또는 `report_id` deletion cascade) 필요.
- CSV streaming은 backend에서 cursor-based query로 구현해야 메모리 안전. `cursor` + `psycopg.connection.execute(... server_side=True)` 사용.
- MapLibre + 다수 sample marker(>10,000)는 cluster + viewport-based loading 필수.
- Zustand store가 너무 많아지면 cross-store dependency가 생긴다. 한 화면 = 한 store 원칙 권장.

## 관련 ADR/Task

- ADR-016: `load_consistency_reports` 도입. 본 task는 후속 확장.
- ADR-033: `ops` schema. `consistency_case_samples`는 `ops` schema 안에 둔다.
- T-047: 성능 튜닝 결과를 `/admin/performance`에서 활용.
- T-052: v2 API의 region hint를 sample filter에서도 동일하게 사용.
- T-054: 외부 IP에서 admin 화면 접근 차단.
