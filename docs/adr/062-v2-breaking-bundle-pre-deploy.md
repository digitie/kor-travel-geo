# ADR-062: v2 breaking 묶음(enum 정직화·envelope/error 통일·좌표 lon/lat)을 배포 전 일괄 적용한다

- 상태: accepted
- 날짜: 2026-06-17
- 결정자: 사용자(지시) + claude
- 관련: T-268, T-105(#308), ADR-060(§1/§2/§4/§6/§9), ADR-061, ADR-039, ADR-038, T-169, T-173

## 컨텍스트

ADR-060은 v2 breaking 묶음 ②enum 정직화·③envelope/error 통일·④좌표 lon/lat를 "v2 배포 직전" 적용으로
계획했다. v2는 여전히 미배포 candidate(ADR-039)이고 소비자는 내부 UI/SDK뿐이라 wire 회귀 위험이 없다.
사용자가 배포 전 정리를 지시해 묶음을 지금 적용한다.

## 결정

1. **일괄 적용(T-268).** 미배포 중 한 번에 적용해 typegen/UI 분기 비용을 최소화한다(ADR-060 §9 원칙).
2. **②enum 정직화**: published 후보 enum은 emit되는 값만 담는다. `match_kind="detail"`,
   `point_precision` `exact`/`interpolated`/`approximate`를 schema에서 제거하고 `conventions.md` §2
   예약 목록으로 옮긴다(producer가 생기면 enum+typegen 추가). `source` vworld/juso는 description에
   "fallback 전용" 주석.
3. **③envelope/error**: `RegionsWithinRadiusResponse`에 공통 header `{status, query_id, input}`를 추가한다.
   v2 전용 error envelope `{status:"ERROR", query_id, error:{code, message, hint?, field?}}`(`V2ErrorEnvelope`)를
   도입하고 OpenAPI에 v2 4xx를 명세한다. 범위는 **v2 API의 검증/도메인 에러**(`responses.py` 핸들러 +
   admission)이며, 교차-cutting 인프라 게이트(GeoIP 403)는 모든 표면에서 공유 legacy `{response:{errorCode}}`
   형태를 유지한다(인프라 응답 일관성). v1 vworld(ADR-038)는 무변경. T-173 input-safety(구조화 4xx)는
   유지하고 shape만 바꾼다. 레거시 `StructuredErrorEnvelope`(ADR-061)는 폐기·대체한다.
4. **④좌표 lon/lat**: `CandidateV2.point`를 `Point{x, y}`에서 `PointV2{lon, lat}`로 바꾼다. v1 vworld의
   `Point{x, y}`(ADR-038)는 별도 유지하고, 내부 v1→v2 변환에서 `_to_point_v2`로 매핑한다.
5. **error_payload 중앙화**: path 기준으로 vworld/v2/legacy envelope를 분기하는 단일 `error_payload(exc, *, path, field?)`로
   모아 모든 에러 발생 지점(예외 핸들러·admission)이 일관 동작하게 한다.

## 근거

- v2 미배포 + typegen 동반이라 지금 적용이 배포 직전 적용과 위험이 동일하고, 잔여 breaking 부채를 없앤다.
- GeoIP/admission 같은 인프라 게이트를 v2 envelope로 강제하면 보안 응답 필드(`message_en`/`client_country`)와
  충돌하고 표면 간 비일관을 만든다 → 공유 legacy 유지가 더 일관적.

## 결과

- backend DTO(`dto/v2.py` `PointV2`/`V2ErrorEnvelope`/enum, `RegionsWithinRadiusResponse`), `responses.py`
  (path-aware), `client.py`, `core/v2.py`(`_to_point_v2`) + openapi/typegen + 프론트(`GeocodeDebugger` point)
  + 테스트. `dto/common.py`의 `StructuredErrorEnvelope`/`StructuredErrorBody` 제거.
- v1 vworld 호환은 영향 없음. 검증 게이트(ruff/mypy/lint-imports/openapi --check/unit 1014/프론트) 통과.
