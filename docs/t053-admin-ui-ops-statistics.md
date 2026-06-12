# T-053: Admin Web UI 운영/유지보수/관리/튜닝 표면 보강 + C1~C10 상세 분석 UI

## 상태

- 상태: 구현 완료(1차)
- 대상 브랜치: `codex/t053-admin-consistency-ui`
- 사용자 RFC: 2026-05-27 — "web UI는 유지보수 목적으로도 쓰임. 관련해서 기능 보완(통계/유지보수/관리/튜닝). TanStack Query, Zustand 활용. C1~C10 데이터를 별도의 테이블에 적재하고 UI를 통해 직접 눈으로 보거나 상세 분석을 할 수 있게 상세 분석 UI 및 CSV 형태로 빼서 볼 수 있도록 UI에 반영."
- 사용자 재확인: 2026-05-28 — T053은 최대한 다각도로 데이터를 볼 수 있도록 하고, C1~C10 비정상 케이스가 왜 발생했는지 사용자가 직접 데이터를 비교해 판별하며, 하나 또는 여러 sample을 수동 승인/거절/보류/메모/재검증할 수 있어야 한다. maplibre-vworld-js 기반 지도 오버레이와 테이블 뷰를 적극 활용하고, C1~C10 기준은 웹페이지 자체에서 사용자가 판별할 수 있을 만큼 명확히 설명한다. 필요한 경우 v1/v2 API 확장에도 반영한다.

## 목적

`kor-travel-geo-ui`는 현재 디버그(`/debug/*`)와 기본 관리(`/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`, `/admin/backups`, `/admin/ops`)로 구성된다. 본 task는 운영자가 "실제 운영 콘솔"로 쓸 수 있도록 다음 4개 표면을 보강한다.

1. **통계**(`/admin/stats`): row count 추이, 적재/응답 metrics, geo_cache hit ratio, 외부 provider 호출 분포.
2. **유지보수**(`/admin/maintenance`): vacuum/analyze 트리거, index health, table bloat, dead tuple 추이.
3. **관리**(`/admin/ops` 보강): T-049 ops 메타데이터(`snapshots`, `releases`, `artifacts`, `audit-events`, `maintenance-windows`)를 단순 list가 아니라 cross-reference + 액션 가능한 콘솔로.
4. **튜닝**(`/admin/performance` 보강): T-047 benchmark 결과를 시계열로 보고, 보조 view/MV 도입 효과를 GUI에서 직접 비교.

추가로 **C1~C10 정합성 분석 UI**를 별도 표면으로 정리한다. 현재 `load_consistency_reports.cases` JSONB에 sample/metric이 묶여 있어 SQL 없이는 case별 deep dive가 어렵다. 본 task에서는 case sample을 별도 테이블에 분리 적재하고, UI에서 sort/filter/map/CSV export/수동 판정까지 직접 수행할 수 있게 한다.

## 1차 구현 범위와 우선순위

T053 1차 PR의 중심은 **C1~C10 정합성 상세 분석/수동 판별 콘솔**이다. 통계(`/admin/stats`), 유지보수(`/admin/maintenance`), 운영(`/admin/ops`), 튜닝(`/admin/performance`)은 본 문서에 전체 방향을 유지하되, 같은 PR에서 위험 없이 연결 가능한 최소 진입점만 구현하고 나머지는 T050 또는 별도 task로 분리한다. 이유는 C1~C10 sample 저장, 판정 상태, 지도 overlay, CSV export, 다중 선택 관리가 백엔드 schema와 UI를 동시에 건드리는 충분히 큰 작업이기 때문이다.

1차 PR에서 반드시 구현할 것:

- C1~C10 기준 설명을 UI 자체에 포함한다. 사용자는 문서를 열지 않고도 각 케이스가 무엇을 비교하고 어떤 상황이 비정상인지 알 수 있어야 한다.
- sample을 row 단위로 조회하고, table/map/detail panel에서 서로 다른 원천 데이터를 나란히 비교한다.
- sample 단건 및 다중 선택에 대해 `approve`, `reject`, `defer` 판정을 저장하고, reason code와 메모를 남긴다.
- 현재 filter를 CSV/JSON으로 export한다.
- 지도 overlay는 `maplibre-vworld-js` public API를 소비하는 domain wrapper에서 구현한다. upstream 코드는 직접 수정하지 않는다.

후속으로 넘길 수 있는 것:

- 전역 통계/유지보수/튜닝 대시보드의 full surface.
- `point_precision`처럼 v2 public schema와 직접 연결되는 추가 표현이 필요할 때의 v2 확장.
- 대용량 viewport 기반 infinite loading과 server-side vector tile화.

## C1~C10 기준 설명 모델

UI에는 각 케이스별로 "무엇을 비교하는가", "정상 기준", "비정상 해석", "사용자가 볼 증거", "추천 판정"을 카드 또는 collapsible panel로 제공한다. 이 설명은 API 응답에도 `case_definition` 형태로 내려 사용자와 AI agent가 같은 기준을 읽을 수 있게 한다.

| 코드 | 비교 대상 | 비정상 기준 | 사용자가 볼 증거 | 주된 원인 후보 | 기본 판정 가이드 |
|------|-----------|-------------|------------------|----------------|------------------|
| C1 | `tl_juso_text` 텍스트 정본 vs `tl_spbd_buld_polygon` 건물 polygon natural key | 텍스트에는 있으나 SHP polygon에 대응 행이 없음 | `bd_mgt_sn`, `rncode_full`, 건물번호, `bjd_cd`, 텍스트 주소, 주변 polygon 후보 | SHP 누락, 기준월 차이, 자연키 해소 실패, 건물 삭제/신규 반영 시차 | 원천 기준월 차이면 `defer`, 반복 원천 누락이면 `approve`, loader key 오류면 `reject` |
| C2 | SHP 건물 polygon vs 텍스트 정본 natural key | polygon에는 있으나 텍스트 정본에 대응 행이 없음 | polygon 속성, `missing_resolve_key`/`missing_text`, 주변 텍스트 후보 | SHP 속성 결측, 정본 누락, 기준월 차이, natural key 조합 오류 | `missing_resolve_key`는 loader 보강 후보로 우선 `reject`, 명백한 원천 시차는 `defer` |
| C3 | 텍스트 정본 건물 vs 대표 출입구(`locsum`, same-month direct entrance) | 대표 출입구가 해소되지 않음 | 텍스트 주소, 출입구 후보 여부, source kind, 기준월 | 위치정보요약DB 누락, direct 출입구 기준월 불일치, 키 해소 실패 | source set 혼합이면 `defer`, 키 해소 규칙 문제면 `reject` |
| C4 | 대표 출입구 좌표 vs 건물 polygon | 50m 초과 WARN, 500m 초과 ERROR | 출입구 점, 건물 polygon, 거리 line, `source_kind`, nearest polygon | 좌표 원천 이상치, 잘못된 polygon 매칭, 기준월 차이, 경도/위도 또는 좌표계 오류 | 500m 초과는 원칙 `reject`, 실제 원천 좌표 이상이면 `approve`+근거 메모 |
| C5 | 내비 centroid vs 건물 polygon centroid | 10m 초과 WARN | 내비 centroid, polygon centroid, 거리 line, 건물 속성 | 내비 원천 centroid 편차, polygon 후보 다대다, 기준월 차이 | 도형이 복잡한 대형 건물은 `approve`, key mismatch는 `reject` |
| C6 | 텍스트 우편번호 vs 기초구역 polygon | zip polygon 누락 WARN, 좌표 외부 ERROR | 출입구 점, BAS polygon, 텍스트 `zip_no`, polygon `bas_id` | 우편번호 원천 시차, BAS polygon 누락, 좌표 오차 | polygon 누락은 `defer`, 좌표 외부는 지도 확인 후 `approve` 또는 `reject` |
| C7 | 행정구역 polygon vs 출입구 좌표 | 행정 polygon 누락 WARN, 좌표 외부 ERROR | 출입구 점, 법정동/행정동 polygon, `bjd_cd`, `adm_cd` | 행정경계 변경 시차, 좌표 오차, 코드 매핑 오류 | 경계 인접 소수는 `approve`, 코드/좌표 체계 오류는 `reject` |
| C8 | 도로명 polyline vs 출입구 좌표 | 같은 도로명 100m 밖 WARN | 출입구 점, 도로 polyline, 거리 line, `rncode_full` | 도로 중심선 누락, 도로명 코드 매핑 오류, 대규모 단지 진입로 | 실제 진입로가 멀면 `approve`, 코드 mismatch면 `reject` |
| C9 | PNU 형식 | PNU 형식 위반 1건 이상 ERROR | PNU 원문, 자리수, `bjd_cd`, 산 여부, 본번/부번 | 파싱/적재 오류, 원천 값 결측 또는 형식 변경 | 대부분 loader/parser 결함 후보로 `reject` |
| C10 | 원천별 `source_yyyymm` | 기준월 2종 이상 WARN | table별 기준월, source set 확인 여부, row-level evidence | 의도한 혼합 적재, 일부 원천 최신화, 실수로 다른 월 파일 섞임 | 확인된 혼합은 `approve`, 확인 없는 혼합은 `reject` 또는 `defer` |

판정 상태의 의미:

- `unreviewed`: 아직 사람이 보지 않은 sample.
- `approved`: 비정상이지만 원천 특성 또는 운영자가 허용한 예외로 받아들인다. 데이터는 수정하지 않는다.
- `rejected`: loader, 정규화, source set, 좌표계, 원천 선택 문제로 보며 후속 수정이 필요하다.
- `deferred`: 판정 근거가 부족해 원천 파일, 외부 기준, 추가 재검증이 필요하다.

판정은 원천 데이터를 바꾸는 작업이 아니라 **운영 판단 기록**이다. 같은 sample에 대한 판정 변경은 마지막 상태를 current로 쓰되, `ops.audit_events`에 변경 이력을 남긴다.

## C1~C10 분석 화면 요구사항

### 정보 구조

`/admin/consistency`는 리포트 목록과 최신 리포트 요약을 유지하고, `/admin/consistency/{report_id}`에서 상세 분석을 제공한다.

상세 화면은 다음 영역을 갖는다.

1. **Case rail**: C1~C10 목록, severity, count, `unreviewed/approved/rejected/deferred` 수, threshold 요약.
2. **Criteria panel**: 선택 case의 기준 설명, 정상/비정상 예시, 판단 체크리스트.
3. **Filter toolbar**: severity, decision, `sig_cd`, `bjd_cd`, `bd_mgt_sn`, reason, source kind, distance range, source month, has point, bbox.
4. **Comparison table**: sample row를 원천별 column group으로 보여 준다. 도로명 정본, SHP polygon, locsum/direct entrance, navi, BAS/admin/road layer, source month evidence를 case별로 표시한다.
5. **Map overlay**: 선택 sample 또는 현재 filter result의 지도 비교. polygon/point/line overlay와 legend를 제공한다.
6. **Detail drawer**: 선택 sample의 raw evidence JSON, 후보 주소/좌표, 판정 이력, 메모, 재검증 버튼.
7. **Bulk action bar**: 선택한 여러 sample에 대해 `approve/reject/defer`, reason, note를 일괄 적용한다.
8. **Export panel**: 현재 filter를 CSV/JSON으로 내보내고, 사람이 읽는 Markdown 요약을 생성한다.

### 지도 overlay 규칙

- C1/C2: 텍스트 또는 polygon만 있는 경우, 존재하는 geometry와 nearest 후보를 다른 색으로 표시한다. 후보가 없으면 시군구 centroid 또는 source row만 표시한다.
- C3: 텍스트 주소와 해소된 출입구 후보가 없음을 보여 주고, 같은 natural key 주변 후보를 점으로 표시한다.
- C4: 출입구 점, 건물 polygon, nearest 연결선을 표시한다. 50m/500m threshold를 line 색상과 legend로 구분한다.
- C5: 내비 centroid와 polygon centroid를 점으로 표시하고 연결선을 표시한다.
- C6: 출입구 점과 기초구역 polygon을 함께 표시한다. 텍스트 `zip_no`와 polygon `bas_id`가 다르면 label로 표시한다.
- C7: 출입구 점과 법정동/행정동 polygon을 표시한다. 경계 밖이면 nearest boundary distance를 보조 metric으로 보여 준다.
- C8: 출입구 점과 도로 polyline을 표시하고 100m threshold line을 표시한다.
- C9: 좌표가 없을 수 있으므로 table/detail 중심으로 보여 주고, `bjd_cd`가 있으면 법정동 영역 overlay를 보조로 표시한다.
- C10: 지도보다 source month matrix가 중요하다. 지도 탭에서는 sample point가 있는 row만 표시하고, 기본은 table/matrix view다.

MapLibre 구현은 `kor-travel-geo-ui` domain wrapper에 둔다. `maplibre-vworld-js`의 `VWorldMap`, marker/layer primitive, tile error helper를 소비하되, T053에서 upstream 코드는 직접 수정하지 않는다. 필요한 범용 기능이 부족하면 별도 upstream task로 기록한다.

### 테이블 비교 규칙

테이블은 card grid가 아니라 조밀한 운영 table을 기본으로 한다. column group은 case별로 다르지만 다음 공통 필드는 고정한다.

- identity: `sample_id`, `case_code`, `report_id`, `bd_mgt_sn`, `rncode_full`, `bjd_cd`, `sig_cd`
- severity/decision: `severity`, `decision_state`, `reason_code`, `reviewed_by`, `reviewed_at`
- metric: `distance_m`, `ratio`, `threshold_exceeded`, `source_kind`, `source_yyyymm`
- geometry summary: `lon`, `lat`, `has_polygon`, `has_line`, `bbox`
- evidence: case별 `case_metric` JSONB와 source row snippets

사용자는 row 하나를 클릭해 detail drawer에서 raw evidence를 볼 수 있고, checkbox로 여러 row를 선택해 bulk action을 수행한다. bulk action은 현재 filter 전체가 아니라 **선택된 sample id 목록**에만 적용한다. "현재 filter 전체에 적용"은 위험하므로 별도 typed confirmation이 있는 후속 기능으로 둔다.

### 수동 판정과 관리

판정 액션:

- `approve`: 원천 특성으로 인정. 필수 reason: `source_gap`, `known_boundary_issue`, `mixed_yyyymm_acknowledged`, `legacy_source`, `manual_verified`.
- `reject`: 수정 필요. 필수 reason: `loader_key_error`, `coordinate_error`, `source_set_error`, `parser_error`, `upstream_data_error`, `needs_code_fix`.
- `defer`: 추가 확인 필요. 필수 reason: `needs_source_file_check`, `needs_map_check`, `needs_reload`, `needs_policy_decision`.

UI 제약:

- note는 선택이지만 `reject`와 `defer`에서는 10자 이상 권장 경고를 보여 준다.
- 판정 변경 시 이전 상태와 새 상태를 확인 modal에 표시한다.
- bulk action은 선택 count, case distribution, severity distribution을 modal에 보여 준다.
- 이미 `approved/rejected/deferred`인 sample을 다시 변경할 수 있지만, audit event가 남아야 한다.

재검증:

- 단건 재검증은 해당 sample의 source key로 현재 DB에서 evidence를 다시 조회하는 lightweight endpoint를 둔다.
- 전체 case 재검증은 기존 `POST /v1/admin/consistency/run`을 사용한다.
- 재검증 결과가 기존 sample과 달라지면 detail drawer에 "stale sample" warning을 표시한다.

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

### 신규 테이블과 판정 컬럼

```sql
-- ops.consistency_case_samples
-- C1~C10 case sample을 row-per-record로 분리 적재하고 최신 수동 판정 상태를 함께 둔다.
CREATE TABLE IF NOT EXISTS ops.consistency_case_samples (
  sample_id            UUID PRIMARY KEY,
  report_id            TEXT NOT NULL REFERENCES load_consistency_reports(report_id) ON DELETE CASCADE,
  case_code            TEXT NOT NULL CHECK (case_code ~ '^C(10|[1-9])$'),
  severity             TEXT NOT NULL CHECK (severity IN ('OK','INFO','WARN','ERROR')),
  sample_rank          INTEGER NOT NULL DEFAULT 0,
  bd_mgt_sn            TEXT,
  rncode_full          TEXT,
  sig_cd               TEXT,
  bjd_cd               TEXT,
  distance_m           DOUBLE PRECISION,
  source_yyyymm        TEXT,
  source_kind          TEXT,
  -- case별로 의미가 다른 metric/evidence는 JSONB로 보존한다.
  case_metric          JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- 좌표는 별도 컬럼으로 둔다. 4326은 API/UI 직렬화용, 5179는 공간 query용이다.
  point_4326           geometry(Point, 4326),
  point_5179           geometry(Point, 5179),
  bbox_4326            JSONB NOT NULL DEFAULT '{}'::jsonb,
  has_polygon          BOOLEAN NOT NULL DEFAULT false,
  has_line             BOOLEAN NOT NULL DEFAULT false,
  decision_state       TEXT NOT NULL DEFAULT 'unreviewed'
                       CHECK (decision_state IN ('unreviewed','approved','rejected','deferred')),
  reason_code          TEXT,
  note                 TEXT,
  reviewed_by          TEXT,
  reviewed_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_consistency_case_samples_report
  ON ops.consistency_case_samples (report_id, case_code, severity, decision_state);
CREATE INDEX idx_consistency_case_samples_case_severity
  ON ops.consistency_case_samples (case_code, severity, distance_m DESC);
CREATE INDEX idx_consistency_case_samples_sig
  ON ops.consistency_case_samples (sig_cd, case_code);
CREATE INDEX idx_consistency_case_samples_review
  ON ops.consistency_case_samples (report_id, case_code, decision_state, reviewed_at DESC);
CREATE INDEX idx_consistency_case_samples_4326
  ON ops.consistency_case_samples USING GIST (point_4326);
```

판정 변경 이력은 `ops.audit_events`에 `resource_type='consistency_sample'`, `resource_id=<sample_id>`, `action='consistency.sample.decision'` 형태로 append-only 기록한다. 최신 상태는 sample row의 `decision_state`/`reason_code`/`note`/`reviewed_*` 컬럼을 읽는다. 별도 history table은 같은 정보를 두 번 저장하므로 1차 구현에서는 만들지 않는다.

`source_snapshot`에는 원천 주소 전문을 저장하지 않는다. 대신 비교에 필요한 식별자, 원천 row 일부 필드, metric, geometry summary, nearest candidate 요약처럼 운영자가 판정하는 데 필요한 최소 evidence만 넣는다. 사람이 볼 주소 문자열이 꼭 필요하면 API가 현재 DB에서 재구성해 일회성 응답으로 내려 주고, sample table에는 저장하지 않는다.

### 적재 정책

- `run_all_cases()` 실행 시 기존 `load_consistency_reports.cases` JSONB는 그대로 채우고(요약), 동시에 `ops.consistency_case_samples`에도 row 단위 insert한다.
- sample 수는 케이스별 cap이 있다. 1차 구현은 현재 `ConsistencyCase.sample` cap을 그대로 row로 펼치고, cap 정책이 부족해지면 시군구별 stratified sampling을 후속으로 보강한다. 즉 `ops.consistency_case_samples`는 **report에 캡처된 대표 표본 검토 테이블**이지 전체 위반 모집단 테이블이 아니다. C2 34,699건처럼 전수 위반을 사람이 모두 CSV로 내려받아 분석해야 하면 case별 full-violation export job을 별도 후속으로 만든다.
- `sample_id`는 `report_id + case_code + sample_rank + source key`를 기반으로 재현 가능한 UUIDv5로 만든다. 같은 report 재조회에서 UI selection과 review mutation이 흔들리지 않아야 한다.
- `ops` schema 정책상 secret/주소 원문 평문 저장 금지(ADR-033). `bd_mgt_sn`, `rncode_full`, `bjd_cd`, `sig_cd`, 거리 metric, source month는 OK이고 원문 주소는 저장하지 않는다.
- T-056 `core.address` helper를 사용해 `sig_cd`, `bjd_cd`, `rncode_full`, 도로명주소관리번호 필터 입력을 API와 UI 양쪽에서 같은 규칙으로 정규화한다.
- 이미 생성된 오래된 report는 `cases` JSONB를 펼쳐 sample table에 lazy backfill할 수 있어야 한다. `GET /samples`가 table row를 찾지 못하면 해당 report의 JSONB sample을 한 번 펼쳐 저장한 뒤 조회한다.
- `reason_code`는 UI에서 권장 어휘를 dropdown으로 제공하지만, 서버는 1차 구현에서 80자 이하 자유 문자열을 허용한다. API 직접 호출자는 UI 권장값을 우선 사용해야 reason별 집계가 깨끗하게 유지된다. 서버 enum 승격은 운영 집계 요구가 커지는 시점의 후속이다.

### REST 표면

```text
GET  /v1/admin/consistency/case-definitions
       — C1~C10 설명, threshold, 기본 판정 가이드

GET  /v1/admin/consistency/{report_id}/cases/{case_code}/samples
       ?severity=ERROR&decision=unreviewed&sig_cd=11&order_by=distance_m&desc=true&page=1&page_size=100
       Accept: application/json | text/csv

GET  /v1/admin/consistency/{report_id}/cases/{case_code}/summary
       — 시군구별 count, severity 분포, distance 통계

PATCH /v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/decision
       { decision_state, reason_code, note, reviewer }

POST /v1/admin/consistency/{report_id}/cases/{case_code}/samples/bulk-decision
       { sample_ids, decision_state, reason_code, note, reviewer }

POST /v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/recheck
       — 현재 DB 기준 lightweight evidence 재조회. 1차 구현은 stale 여부/현재 source key 존재 여부 중심.
```

CSV export는 `Accept: text/csv` 또는 `?format=csv`. 1차 구현은 페이지/필터 결과를 안정적으로 내보내고, 100만 행 streaming은 cursor-based query로 후속 확장한다. response schema 변경은 모두 admin v1에 둔다.

### v1/v2 API 확장 판단

- **v1 admin API**: C1~C10 case definition, sample list, manual decision, bulk decision, export, recheck를 담당한다. 운영자 UI가 쓰는 mutable API이므로 `/v1/admin/*`가 맞다.
- **v1 public API**: 기존 vworld 호환 `/v1/address/*` 응답 구조는 건드리지 않는다. 자체 필드는 계속 `x_extension` 안에만 둔다.
- **v2 public API**: T052의 candidate schema는 사용자/AI가 주소 후보를 비교하는 read-only API다. T053 수동 판정 상태, review note, admin audit를 v2 후보 응답에 섞지 않는다. 다만 향후 "정합성 sample을 v2 geocode/reverse 후보와 직접 비교"하는 기능을 만들면 별도 `admin` 전용 compare endpoint로 둔다.

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

`/admin/consistency/{report_id}` 페이지를 확장한다. 좌측 case rail과 우측 분석 영역을 같은 화면에 두고, 사용자가 case 선택 → 기준 확인 → table/map 비교 → 단건 또는 bulk 판정 → export까지 끊기지 않게 진행할 수 있어야 한다.

### 우측 분석 영역

1. **Overview**: report 메타, severity 분포, case별 판정 진행률, C4/C5 거리 histogram, C10 source month matrix.
2. **Criteria**: 선택 case의 비교 대상, 비정상 기준, 권장 판정, 체크리스트. UI 내부 copy는 이 문서의 C1~C10 표와 API `case_definitions`를 source of truth로 쓴다.
3. **Compare Table**: TanStack Table — sample row의 식별자/metric/geometry/decision/evidence를 정렬·필터·페이지. row 클릭 시 detail drawer와 지도 selection이 동시에 바뀐다.
4. **Map Overlay**: 현재 filter page 또는 선택 row를 MapLibre + `maplibre-vworld-js` wrapper로 표시한다. C4/C5/C8은 연결선과 거리 label, C6/C7은 polygon/point 관계, C10은 point가 있는 sample만 표시한다.
5. **Decision Drawer**: raw evidence JSON, source snapshot, 기존 판정 이력 요약, 단건 `approve/reject/defer`, reason, note, recheck.
6. **Export**: 현재 filter CSV/JSON 다운로드와 Markdown 요약 생성. CSV는 backend export를 기본으로 쓰고, UI column visibility는 query param으로 전달한다.

4탭 형태로 화면을 쪼개는 것은 1차 구현 목표가 아니다. 사용자가 데이터를 비교하다가 기준 설명/지도/판정 버튼을 계속 오가야 하므로, 화면은 rail + table + map/detail split layout을 우선한다.

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
// kor-travel-geo-ui/lib/stores/consistency-analysis-store.ts
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

1. 본 문서 보강 — 사용자 RFC를 C1~C10 기준, 화면 정보 구조, 판정 상태, API 경계로 구체화한다.
2. `ops.consistency_case_samples` DDL + Alembic migration + 기존 report JSONB lazy backfill.
3. `run_all_cases()` 변경 — 새 report 생성 시 sample row 별도 적재.
4. admin DTO/client/repository/API — case definitions, samples, summary, single/bulk decision, CSV/JSON export.
5. `kor-travel-geo-ui` 타입 갱신 — OpenAPI export → `npm run gen:types`.
6. `kor-travel-geo-ui/app/admin/consistency` 보강 — report list에서 detail page로 진입하고, detail page에 criteria/table/map/detail/decision/export를 구현한다.
7. `lib/stores/consistency-analysis-store.ts` — selected sample, visible columns, drawer, map view, selection set만 zustand에 둔다.
8. `/admin/stats`, `/admin/maintenance`, `/admin/ops`, `/admin/performance`의 full surface는 T050/T061 이후 별도 task로 분리한다.

## 검증 기준

- backend: `pytest`에서 `ops.consistency_case_samples` DDL, report sample 저장, lazy backfill, sample list/summary, single/bulk decision, CSV 응답 회귀.
- frontend: vitest로 zustand store reducer, TanStack Query key 생성, decision payload, CSV column 선택 테스트.
- e2e/브라우저: `/admin/consistency/{report_id}`에서 case 선택, sample row 클릭, 지도 표시, 단건/다중 판정 modal, CSV 다운로드 버튼 동작.
- 운영: 실제 T-027 final clean load 결과 report에서 C4 ERROR 16건, C7 ERROR 6,817건이 sample 테이블에 row-per-record로 적재되는지 확인.

## 남은 위험

- `ops.consistency_case_samples`가 case당 1,000건 cap이라도 전체 10 case × 다중 report로 누적되면 수십만 row가 된다. retention 정책은 `load_consistency_reports` 삭제 cascade와 별도 TTL task로 보강한다.
- CSV streaming은 대용량에서 cursor-based query로 바꿔야 메모리 안전하다. 1차 구현이 페이지 단위 export라면 문서와 UI에 한계를 명확히 표시한다.
- MapLibre + 다수 sample marker(>10,000)는 cluster + viewport-based loading 필수다. 1차 구현은 선택 sample과 현재 page 중심으로 제한한다.
- 판정 상태는 운영 기록이므로 감사 추적이 중요하다. audit insert가 실패하면 decision update도 실패해야 한다.
- `source_snapshot`에 주소 원문이나 외부 API key가 들어가지 않도록 redaction helper와 테스트가 필요하다.
- Zustand store가 너무 많아지면 cross-store dependency가 생긴다. T053은 `useConsistencyAnalysisStore` 하나만 둔다.

## 관련 ADR/Task

- ADR-016: `load_consistency_reports` 도입. 본 task는 후속 확장.
- ADR-033: `ops` schema. `consistency_case_samples`는 `ops` schema 안에 둔다.
- T-047: 성능 튜닝 결과를 `/admin/performance`에서 활용.
- T-052: v2 API의 region hint를 sample filter에서도 동일하게 사용.
- T-054: 외부 IP에서 admin 화면 접근 차단.
