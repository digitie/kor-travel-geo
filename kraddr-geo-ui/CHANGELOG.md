# CHANGELOG

## [Unreleased]

### Added
- T-021~T-023/T-026: Next.js 기반 디버그·관리 UI 초안 추가.
- T-020 연계: `openapi.json` 기반 타입 생성 스크립트 추가.
- MapLibre GL JS + VWorld WMTS 기반 좌표 지도 컴포넌트와 key 미설정 fallback 프리뷰 추가.
- `digitie/maplibre-vworld-js` 연동 원칙 문서화: 패키징·타입·Next.js 호환 문제가 나오면 UI workaround만 두지 않고 upstream도 적극 수정한다.
- `/api/proxy/[...path]` Route Handler로 raw ZIP 업로드와 JSON API 호출을 같은 경로에서 프록시.
- Vitest 단위 테스트: 시도 추론, load workflow reducer, consistency severity, schema name generation, API path helper.
