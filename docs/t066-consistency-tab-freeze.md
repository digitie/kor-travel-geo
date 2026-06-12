# T-066 Consistency 탭 진입 프리즈 완화

- 상태: 완료
- 날짜: 2026-05-30
- 관련 UI: `kor-travel-geo-ui` `/admin/consistency`

## 배경

사용자가 `/admin/consistency` 진입 시 브라우저 탭이 멈추는 현상을 보고했다. 백엔드 `GET /v1/admin/consistency`, report detail, case sample, case summary API는 Docker DB 기준 모두 수십 ms 안에 응답했으므로, 1차 원인은 서버 쿼리 정지가 아니라 프론트엔드 초기 렌더 비용으로 판단했다.

## 원인

기존 `ConsistencyPanel`은 샘플을 사용자가 선택하지 않아도 다음 동작을 수행했다.

1. `selectedSampleId`가 없으면 현재 page의 첫 `point` 샘플을 자동 선택처럼 사용했다.
2. 그 결과 `/admin/consistency` 진입 직후 `LazyCoordinateMap`이 import되고 MapLibre/VWorld 지도가 초기화됐다.
3. VWorld 타일 요청, WebGL 초기화, 지도 resize observer가 테이블/리포트 hydrate와 같은 순간에 겹쳐 탭 진입 체감이 무거워졌다. 특히 인증키/타일 오류가 있으면 console warning과 overlay 갱신이 함께 발생해 프리즈처럼 보일 수 있다.

## 변경

- 샘플을 명시적으로 선택하기 전에는 `selectedSample`을 `null`로 유지한다.
- `MapPreview`는 샘플 미선택 상태에서 `LazyCoordinateMap`을 렌더하지 않고 가벼운 placeholder만 보여 준다.
- 사용자가 테이블의 sample 버튼을 누르면 그때 지도 컴포넌트를 동적으로 로드한다.
- 이 동작을 `tests/unit/consistency-panel.test.tsx`로 고정했다. 테스트는 샘플 목록이 로드되어도 지도 컴포넌트가 호출되지 않고, sample 선택 후에만 호출되는지 확인한다.

## 검증

- `GET /v1/admin/consistency` 직접 호출: `224 bytes`, 약 `5.6ms`
- `GET /v1/admin/consistency/{report_id}` 직접 호출: `21,572 bytes`, 약 `12.4ms`
- C1~C10 sample/summary API 직접 호출: 모두 약 `10~50ms`
- `PATH=/home/digitie/.cache/parking-radar-node-v22.15.0/bin:$PATH npm run test -- consistency-panel consistency` → `2 passed`, `4 tests`

WSL Playwright headless Chromium은 `libasound.so.2` 누락으로 실행하지 못했다. 사용자가 지정한 최종 브라우저 검증 기준은 Windows Playwright이므로, Docker UI 재기동 후 Windows 환경에서 `/admin/consistency` 진입 회귀를 확인한다.

## 후속

- T-067에서 geocode v2 응답은 기존 대표점(point)을 유지하고, 옵션으로 영역/라인 도형을 함께 반환한다.
- 디버그 UI 지도 overlay도 point와 geometry를 함께 표시한다. 성복동은 행정구역 polygon, 성복1로는 도로 line, 성복1로 35는 건물 polygon을 표시하되, point를 제거하지 않는다.
