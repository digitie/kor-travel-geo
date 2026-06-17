# ADR-038: API 표면을 v1(vworld 호환)과 v2(자체 통합 candidate)로 분리하고 AI-friendly 문서를 둔다

- 상태: accepted
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude, codex 보정

## 컨텍스트

본 라이브러리는 vworld OpenAPI 응답 형식 호환을 핵심 정체성으로 둔다(ADR-007/-012). 그러나 신규 API는 vworld key 명명에 갇히지 않고 Kakao Local, Naver Geocoding/Reverse, Google Geocoding/Places, VWorld의 좋은 API 스타일(후보 목록, 주소 구성요소, category/keyword, bbox/viewport, 좌표/주소 reverse 표현)을 참고할 필요가 있다. 사용자 재확인에 따라 v2는 외부 API를 직접 호출하는 wrapper가 아니라 `kor-travel-geo` 자체 데이터와 자체 schema를 노출하는 API다.

## 결정

API 표면을 **v1**(기존 호환)과 **v2**(신규)로 분리한다.

1. **v1**: `/v1/*` 경로 + 현재 DTO 그대로 동결. vworld 호환 key 명명(`addresses[]`, `result.point`, `x_extension.*`) 유지.
2. **v2**: `/v2/geocode`, `/v2/reverse`, `/v2/search`, 후속 `/v2/region/lookup`, `/v2/zipcode/{zip_no}`, (선택) `/v2/transform`. 자체 candidate-list schema, `confidence`/`match_kind`/`source`/`distance_m`/`point_precision`/`bbox` 명시.
3. 라이브러리: 초기 T-052에서는 `AsyncAddressClient`에 `geocode_v2`, `reverse_v2`, `search_v2`를 추가했다. 2026-05-29 ADR-039에서 Python 공개 API는 v2 계약만 남기고 `geocode`, `reverse`, `search`로 승격한다.
4. 외부 API 직접 호출:
   - T-052에서는 새 외부 provider adapter를 추가하지 않는다.
   - 기존 ADR-019의 vworld/juso geocode fallback은 v1 호환 경로로 유지한다.
   - v2 `fallback="api"`는 기존 v1 fallback 결과를 candidate schema로 투영하는 호환 옵션이며, Kakao/Naver/Google 호출을 뜻하지 않는다.
5. v2 입력은 region hint(T-057 `sig_cd`/`bjd_cd`/`bbox`)를 1차 시민으로 받는다.
6. 문서화:
   - `docs/api-reference/` 디렉터리에 v1/v2/library/operators 분류로 markdown.
   - 각 endpoint별 "요약/사용 시나리오/입력 schema/출력 schema/예시(curl + Python + JSON)/에러/관련 ADR" 표준 구조.
   - `docs/api-reference/llm-summary.md`: AI agent용 전체 표면 압축 요약.
   - OpenAPI는 v1/v2 paths 모두 포함, frontend `types/api.gen.ts` 자동 갱신.
7. 새 외부 provider live 비교가 필요해지면 별도 task/ADR에서 API key, quota, 약관, cache TTL, source 표기 정책을 먼저 결정한다.
8. `confidence`는 endpoint-local 점수로 정의한다. geocode는 주소 매칭 신뢰도, reverse는 반경 대비 거리 기반 점수, search는 검색 score다. 좌표 자체의 정밀도는 `point_precision`으로 별도 표현한다.

## 근거

- vworld 호환은 기존 SDK 사용자(`kor-travel-geo-ui` 포함 외부 클라이언트)에게 중요한 contract. 깨지면 안 된다.
- 외부 API들의 좋은 응답 패턴을 v1에 강제 흡수하면 vworld key 명명이 흐려진다.
- 본 라이브러리의 기본 응답은 local PostGIS다. 외부 provider wrapper를 늘리면 약관·캐시·쿼터·출처 표기 부담이 커지므로 T-052 범위에서 제외한다.
- AI agent와 사람이 동시에 읽을 수 있는 문서가 있어야 운영/디버깅이 효율적.

## 결과

- T-052에서 v2 DTO/router/client/문서 PR을 작성한다.
- `docs/api-reference/` skeleton + `llm-summary.md` 생성.
- v1 동결: 회귀 0 검증. `openapi.json`의 `/v1/*` paths schema diff 없음.
- v2 router/client 변환과 OpenAPI/frontend type drift를 검증한다.
- 6~12개월 후 v1 deprecation 일정은 별도 ADR.

## 남은 위험

- v1 + v2 동시 유지 비용. maintenance burden 증가.
- 외부 API 스타일을 참고한 필드가 실제 로컬 데이터로 얼마나 채워지는지 endpoint별 문서와 UI에서 명확히 표시해야 한다.
- v2 응답이 vworld key 명명과 분리되어, 일부 SDK 사용자가 두 schema 모두 다뤄야 한다. `docs/api-reference/v2/migration-from-v1.md` 작성으로 완화.
- 향후 외부 provider live adapter를 추가하면 약관·쿼터·캐시·출처 표기 정책을 새 ADR로 먼저 정해야 한다.
