# CHANGELOG

## [Unreleased]

### Added
- T-021~T-023/T-026: Next.js 기반 디버그·관리 UI 초안 추가.
- T-020 연계: `openapi.json` 기반 타입 생성 스크립트 추가.
- MapLibre GL JS + VWorld WMTS 기반 좌표 지도 컴포넌트와 key 미설정 fallback 프리뷰 추가.
- VWorld 지도 컴포넌트 dynamic import wrapper와 skeleton 테스트 추가.
- `digitie/maplibre-vworld-js` 연동 원칙 문서화: 패키징·타입·Next.js 호환 문제가 나오면 UI workaround만 두지 않고 upstream도 적극 수정한다.
- `/api/proxy/[...path]` Route Handler로 raw ZIP 업로드와 JSON API 호출을 같은 경로에서 프록시.
- Vitest 단위 테스트: 시도 추론, load workflow reducer, consistency severity, schema name generation, API path helper.

### Changed
- `maplibre-vworld`를 upstream main commit `c91c9f304669ce3f5fc4915f21186b23731d5816`로 동기화한다. 최신 upstream redaction helper는 `redactVWorldUrl()`이며, UI 내부에서는 기존 import 계약을 유지하기 위해 `redactVWorldTileUrl` alias로 재수출한다.
- `maplibre-vworld`를 `git+https://github.com/digitie/maplibre-vworld-js.git#a5b3c65`로 고정하고, VWorld WMTS helper와 CSS를 upstream package에서 소비한다.
- `maplibre-vworld`를 upstream PR #9 commit `11321fe`로 동기화하고, VWorld tile error 분류와 URL redaction을 upstream helper로 공유한다.
- upstream zod v4 peer dependency에 맞춰 `zod ^4.4.3`을 직접 의존성으로 둔다.
- VWorld tile transient error는 즉시 fatal overlay로 고정하지 않고 redacted warning과 누적 임계치로 처리한다.
- VWorld `Hybrid`/`Satellite`는 z18, `Base`/`gray`/`midnight`는 z19 maxZoom을 적용한다.
