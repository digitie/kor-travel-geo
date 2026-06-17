# ADR-016: 적재 진행 상태와 정합성 리포트는 라이브러리·API로 일급 노출한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
ADR-006(in-process 큐)과 ADR-011(`load_jobs` 영속화)이 작업 상태를 DB에 적었지만, 외부 라이브러리 사용자(`AsyncAddressClient`)는 작업 큐 표면에 접근할 일이 직접 없다. 또한 ADR-012의 텍스트↔SHP 정합성 검증 결과를 디버그 UI(`kor-travel-geo-ui /admin/load`)와 라이브러리 사용자가 모두 봐야 한다.

## 결정
다음을 사양에 일급 추가한다.

1. **`AsyncAddressClient.load_status(job_id)` / `load_jobs(limit, kind)`** — 적재 작업 상태/진행률/`current_stage`/`log_tail` 조회. 라이브러리 사용자가 자체 앱에서 직접 폴링 가능.
2. **`POST /v1/admin/loads`** + **`GET /v1/admin/loads/{job_id}`** + **`GET /v1/admin/loads?kind=...&state=...`** — REST 표면. WebSocket `/v1/admin/loads/{job_id}/stream`은 선택(structlog 라인 push).
3. **`AsyncAddressClient.consistency_report(report_id?)` / `run_consistency_check(scope)`** — 텍스트↔SHP 정합성 리포트 생성/조회. ADR-012의 검증 케이스(아래)별 결과를 구조화된 JSON으로 반환.
4. **`POST /v1/admin/consistency/run`** + **`GET /v1/admin/consistency/{report_id}`** + **`GET /v1/admin/consistency`** — REST.

## 근거
- 적재가 분기 풀로드로 30~60분 걸리므로 진행 상태가 외부에 노출되어야 운영 자동화가 가능.
- 정합성 리포트는 한 번 생성하고 보관(`load_consistency_reports` 테이블)해 시계열로 회귀 추적.
- 디버그 UI가 같은 라이브러리·REST 함수를 호출하므로 별도 어댑터 없이 일관.

## 결과(긍정)
- 외부 앱이 적재 cron을 자체 관찰 가능.
- 정합성 회귀(예: 텍스트와 SHP 좌표 95th percentile 오차가 갑자기 증가)가 자동 감지 가능.

## 결과(부정)
- 라이브러리 API 표면이 늘어 mypy/import-linter 부담 약간 증가.
- WebSocket 스트리밍은 T-015 작업 큐와 분리해서 추가하는 게 안전(별도 후속).

## 후속
- (open) `consistency_report`의 임계값과 알람 정책은 운영 단계에서 캘리브레이션.
- (open) WebSocket `/v1/admin/loads/{job_id}/stream`은 T-015 본체 구현 후 별도 PR.
