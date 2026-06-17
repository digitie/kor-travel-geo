# ADR-060: v2 API 컨벤션을 차원별로 명문화하고 변경은 additive 우선·breaking 묶음 분리로 적용한다

- 상태: accepted (audit 결론; 구현은 후속 task로 분리)
- 날짜: 2026-06-16
- 결정자: claude
- 관련: T-105, T-169, T-173, T-219(#305), ADR-038, ADR-039, ADR-055, ADR-059

## 컨텍스트

T-105는 v2(자체 통합 candidate, ADR-039)를 **확장성·일관성·유지보수성** 기준으로 재감사했다.
미배포 candidate라 breaking change가 가능하나, 각 변경은 backend DTO + frontend typegen을 동반하고
OpenAPI/`api.gen.ts` drift 0을 유지해야 한다. 차원별 현재/목표는 `docs/api-reference/v2/conventions.md`에 정리했다.
주요 발견: (a) `regions/within-radius`만 공통 envelope(`status`/`query_id`/`input`)가 없음, (b) 페이지네이션 3종
혼재(limit / page+total / 그룹 배열), (c) published enum에 미emit 값 혼재(`detail`·`exact`·`interpolated`·
`approximate`; T-169가 예약 명목으로 보존), (d) v2 전용 error 모델 부재(성공/에러 envelope 분기, trace 단절),
(e) `include_geometry`/`bbox` endpoint 간 비대칭, (f) 출력 후보 좌표 `{x,y}` vs 입력 `lon/lat`·반경 `_m`/`_km`
단위 혼재, (g) v2 응답에 `ServiceMeta`/버전 메타 부재.

## 결정

1. **컨벤션 source of truth**는 `docs/api-reference/v2/conventions.md`로 두고, 실제 코드 변경은 차원별 후속 task로 분리한다(우선순위 최하위, ADR-059와 동일한 "근거 생길 때 breaking 분리" 원칙).
2. **enum 정직화(T-169 재고)**: published 응답 enum은 **현재 emit되는 값만** 담는다. 예약/확장 예정 값(`match_kind="detail"`, `point_precision` `exact`/`interpolated`/`approximate`)은 schema에서 빼고 conventions 문서의 "예약 목록"으로 관리한다(producer가 생기면 그때 enum+typegen 추가). 조건부 live 값(`source` `vworld`/`juso`)은 schema description에 "fallback 경로 전용"으로 주석한다. — **T-169의 "예약값 schema 보존" 결정을 이 지점에서 재고한다.**
3. **envelope 통일**: 모든 v2 응답은 공통 header `{status, query_id, input}` 위에 결과 본문을 둔다. `regions/within-radius`를 이 형태로 올린다(breaking, 후속).
4. **error 모델**: v2 전용 error envelope(`{status:"ERROR", query_id, error:{code, message, hint?, field?}}`)을 도입하고 OpenAPI에 v2 4xx를 명세한다. v2 공개 경로의 구조화 4xx는 의도된 input-safety(T-173)이며, T-219 M4(#305)의 핸들러 범위 결정과 합쳐 처리한다(ADR 후속).
5. **geometry 대칭**: candidate를 반환하는 모든 v2 endpoint(geocode/reverse/search)가 `include_geometry`(기본 false, ADR-059)를 동일하게 받는다(additive, 우선 처리). `bbox` 공간 필터는 geocode/search에만.
6. **페이지네이션 규약**: ranked-candidate(geocode/reverse)=`limit` no-page, collection(search)=`page`/`size`+`total`, regions=그룹별 count 노출. 문서로 고정.
7. **좌표·단위 규약**: 외부 v2 좌표는 `lon`/`lat`로 노출(후보 point의 `{x,y}` → `{lon,lat}`는 최하 우선 breaking), 반경은 단위 suffix(`_m`/`_km`) 필수 규약으로 명문화.
8. **method·버전**: v2는 POST 고정(structured body). trace는 `query_id`를 공식 키로 명문화하고, 버전 메타 추가 여부는 envelope 통일 task에서 함께 결정한다. v1 `ServiceMeta`(vworld 호환)와 분리.
9. **적용 순서**: ① additive·doc(§5 geometry, §3/§6/§7 문서) → ② enum 정직화(§2) → ③ envelope+error 묶음(§1/§4) → ④ 좌표 lon/lat(§6). breaking 묶음은 v2 배포 직전 한 번에 적용해 typegen/UI 분기 비용을 최소화한다.

## 근거

- 미emit 값을 schema에 두면 소비자가 "서버가 보낼 수 있다"고 오해한다. "정직한 enum + 문서화된 예약 목록"이 확장성과 정직성을 동시에 만족한다(T-169의 honesty 취지를 더 밀어붙인 것).
- envelope/error 통일은 SDK·UI가 endpoint마다 다른 분기를 짜지 않게 해 유지보수성을 높인다. `query_id` trace를 에러까지 일관 유지한다.
- geometry opt-in 대칭은 출력 필드(이미 모든 candidate에 존재)와 입력 능력을 맞춘다 — additive라 위험이 낮아 먼저 한다.
- breaking을 묶어 배포 직전 적용하는 것은 ADR-059가 확립한 "wire mode 분기 비용 최소화" 원칙과 일치한다.

## 결과

- 이 PR은 **문서·ADR만** 추가한다(코드·OpenAPI·typegen 변경 0). 컨벤션과 우선순위가 고정된다.
- 각 차원의 실제 반영은 별도 후속 task(backend+frontend 동반)로 등록·진행한다.
- v1 vworld 호환(ADR-038)은 본 결정의 영향 밖이다.
