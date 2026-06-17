# ADR-003: 응답 구조는 vworld와 호환되도록 유지한다

- 상태: accepted
- 날짜: 2026-05-22
- 결정자: human

## 컨텍스트
`kor-travel-geo`이 vworld의 드롭인 대체로 쓰일 수 있어야 한다는 요구가 있다. 동시에 자체 부가 정보(`bd_mgt_sn`, `zip_source`, 신뢰도 등)도 노출해야 한다.

## 결정
응답 최상위 키(`service`, `status`, `input`, `refined`, `result`)는 vworld 그대로 따른다. 자체 확장은 `x_extension` 키 하나에 모은다.

## 근거
- 기존 vworld 소비자 코드 수정 없이 도입 가능
- 확장 필드는 명확히 분리되어 호환성을 깨지 않음

## 결과(긍정)
- 폴백(`fallback="api"`) 시 vworld 원응답과 자연스럽게 섞임
- OpenAPI 스키마가 단정적

## 결과(부정)
- `x_extension` 외 필드 추가는 즉시 거절해야 한다 — 리뷰어 규율 필요
