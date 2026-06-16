# API Reference

이 디렉터리는 사람이 읽는 설명과 AI agent가 빠르게 표면을 파악하는 요약을 함께 둔다. 기계가 직접 읽을 정식 스키마는 저장소 루트의 `openapi.json`이며, 백엔드 변경 뒤에는 `scripts/export_openapi.py`와 `kor-travel-geo-ui`의 `npm run gen:types`를 함께 실행한다.

## 표면 구분

| 구분 | 경로 | 목적 | 호환성 |
|------|------|------|--------|
| v1 | `/v1/address/*`, `/v1/admin/*` | vworld 호환 응답, 기존 UI/SDK/운영 스크립트 | 최상위 응답 구조 유지, 자체 필드는 `x_extension`만 사용 |
| v2 | `/v2/*` | 외부 API 스타일의 장점을 참고한 자체 후보 목록 | 자체 schema, candidate 중심 |
| library | `AsyncAddressClient` | Python async API | 주소 조회는 후보 목록 응답만 공개, REST v1 호환 응답은 HTTP 표면으로 분리 |

## 현재 구현 범위

- v1 지오코딩 fallback은 기존처럼 `vworld`, `juso` 순서로만 시도한다. 키가 없는 provider는 건너뛴다.
- v2는 `POST /v2/geocode`, `POST /v2/reverse`, `POST /v2/search`, `POST /v2/regions/within-radius`를 제공한다.
- v2 응답의 `source`는 `local`, `vworld`, `juso` 중 하나다. v1 내부 캐시 결과는 v2에서 별도 provider source로 노출하지 않고 `local`로 접는다.
- v2는 Kakao/Naver/Google/VWorld API를 직접 wrapping하지 않는다. 각 API의 후보 목록, 주소 구성요소, bbox/viewport, 장소 검색 스타일을 참고한 자체 schema다.
- `CandidateV2.distance_m`은 정식 거리 필드이고, `confidence`는 endpoint-local 점수다. reverse는 `1 - distance_m / radius_m`, search는 검색 score, geocode는 주소 매칭 신뢰도를 뜻한다.

## 문서 지도

- [LLM 요약](llm-summary.md)
- [v1 geocode](v1/geocode.md)
- [v1 reverse](v1/reverse.md)
- [v1 search](v1/search.md)
- [v2 컨벤션 (재audit)](v2/conventions.md)
- [v2 geocode](v2/geocode.md)
- [v2 reverse](v2/reverse.md)
- [v2 search](v2/search.md)
- [v2 regions within radius](v2/regions-within-radius.md)
- [AsyncAddressClient](library/async-address-client.md)
- [오류 코드](library/error-codes.md)
- [API 키](operators/api-keys.md)
