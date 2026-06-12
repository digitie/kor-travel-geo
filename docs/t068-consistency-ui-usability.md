# T-068 Consistency UI 프리즈 재발 수정과 가독성 개선

- 상태: 완료
- 관련 UI: `kor-travel-geo-ui` `/admin/consistency`, `/admin/tables`, `/admin/backups`

## 배경

T-066에서 "샘플 선택 전에는 지도를 마운트하지 않도록" 보강했지만, 사용자가 `/admin/consistency`에서 프리즈가 재현된다고 보고했다. T-066은 지도 마운트 시점만 미뤘을 뿐, 마운트 이후의 두 가지 정지 요인은 남아 있었다.

## 프리즈 근본 원인과 수정

1. **ResizeObserver 동기 resize 루프** (`CoordinateMap.tsx`).
   - 기존 `new ResizeObserver(() => map.resize())`는 콜백 안에서 동기적으로 `map.resize()`를 호출했다. `resize()`가 레이아웃을 다시 계산하면서 같은 프레임에 ResizeObserver를 재발화시키면 "ResizeObserver loop"가 발생해 메인 스레드가 점유되고 탭이 멈춘다. 특히 지도가 화면 하단의 큰 영역으로 들어가면서 레이아웃 변동이 커져 재현 확률이 높아졌다.
   - 수정: resize를 `requestAnimationFrame` 한 프레임으로 합쳐 한 번만 호출하고, 언마운트 시 대기 중인 프레임을 취소한다.

2. **좌표 없는 표본에서도 WebGL 지도를 마운트** (`ConsistencyPanel.tsx`).
   - point가 없는 표본을 선택해도 `LazyCoordinateMap`이 마운트되어 WebGL/타일 초기화가 일어나고, 표시할 좌표가 없어 "지도 로딩 중" 오버레이가 계속 남아 프리즈처럼 보였다.
   - 수정: `MapPreview`는 `sample.point`가 있을 때만 지도를 마운트하고, 좌표가 없으면 가벼운 안내 박스를 보여 준다.

## 레이아웃 변경

- 지도를 좌/우 2열 비교 그리드에서 빼내, 분석 영역 가장 아래의 전용 `map-section`으로 옮겼다.
- 지도 높이를 `60vh`(최소 440px)로 키워 도형/주변 맥락을 더 넓게 본다.

## 가독성(용어) 개선

- Consistency 표 헤더/필터를 한글화: `표본`, `심각도`, `판정`, `건물관리번호`, `시군구코드`, `거리`, `원천`, `사유`, `정렬: …`, `내림차순` 등.
- 지도 범례를 `분류/거리/건물 도형/도로선` 의미 중심 문구로 변경.
- Tables 탭에 각 테이블의 의미를 설명하는 `설명` 칼럼을 추가했다 (`lib/table-descriptions.ts`).
- Backups 탭의 `destination_dir`를 "백업본 저장 폴더"로 라벨링하고, 기타 폼 라벨(profile/jobs/compression/callback/target_database 등)에 한글 설명을 병기했다.

## 폴더 dropdown

- `GET /v1/admin/backups/allowed-dirs`를 추가해 서버 설정 `backup_allowed_dirs` allowlist를 반환한다.
- Backups 탭의 "백업본 저장 폴더"는 allowlist가 있으면 dropdown으로 기존 폴더를 선택하게 하고, 없으면 직접 입력 폴백을 유지한다.
- 임의 디스크 경로를 탐색하는 엔드포인트는 두지 않는다(허용 디렉터리만 노출).

## e2e 회귀 스펙

`tests/e2e/consistency.spec.ts`를 추가했다. consistency API를 `page.route`로 목킹해 DB 없이 UI 단독으로 실행하며 두 가지를 검증한다.

1. `/admin/consistency` 진입 시 멈추지 않고(핵심 UI가 렌더되면 메인 스레드가 살아 있는 것), 표본 선택 전에는 지도 대신 "표본 선택 대기" 안내만 보인다.
2. 표본(`#1`)을 선택하면 안내가 사라지고 지도 범례(`분류 C4`, `건물 도형 있음`)가 나타난다.

이 환경에서는 네트워크 정책으로 Playwright Chromium 바이너리를 내려받지 못해(`browserType.launch: Executable doesn't exist`) 실제 브라우저 실행은 하지 못했다. 대신 `npx playwright test --list`로 스펙 수집을 확인하고, `next start`로 띄운 UI에서 `/admin/consistency`가 HTTP 200으로 서버 렌더되는 것을 확인했다. 실제 브라우저 실행은 Chromium을 받을 수 있는 환경(사용자 Windows Playwright 등)에서 수행한다.

## 검증

- 프론트: `npm run lint`, `npm run type-check`, `npm run test`(34 passed), `npm run build` 통과.
- 백엔드: `ruff check .`, `mypy`(변경 파일), `pytest tests/unit/test_api_app_contract.py tests/unit/test_v2_api.py`(12 passed), OpenAPI drift 체크(`export_openapi.py --check`) 통과.
- `npm run gen:types`로 `types/api.gen.ts`/`schemas.gen.ts`를 재생성했다.
- 참고: `tests/unit/test_metrics.py::test_metrics_render_includes_external_api_and_admin_gauges`는 이 변경과 무관하게 현재 실행 환경에서 `render_prometheus()`가 빈 본문을 반환해 실패한다(메트릭 코드 미변경).
- 브라우저 회귀(Windows Playwright)는 사용자 환경에서 수행한다.
