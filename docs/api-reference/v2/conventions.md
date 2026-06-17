# v2 API 컨벤션 (T-105 재audit)

날짜: 2026-06-16 · 담당: Agent B / Claude · 상태: **audit (현재/목표 정리)**

이 문서는 v2(자체 통합 candidate) API 표면을 **확장성·일관성·유지보수성** 기준으로 재감사하고,
차원별로 *현재 상태 → 문제 → 목표 컨벤션 → 변경 성격(breaking/additive/doc)* 을 정리한다.
결정과 실행 우선순위는 ADR-060에 기록한다. 비-breaking 규약(§1 envelope 목표·§3 페이지네이션·§5 geometry·§6 단위·§7 method/trace)의 사용자-facing 요약은 `README.md`에 반영했다(T-266/T-267).

전제:
- **v1 vworld 호환(ADR-038)은 절대 변경 금지.** 이 문서/ADR의 모든 항목은 v2 전용이다.
- v2는 아직 미배포 candidate(ADR-039)다. breaking change가 가능하나 **각 변경은 backend DTO + frontend typegen(`api.gen.ts`/`schemas.gen.ts`)을 동반**하고, OpenAPI drift 0을 유지한다.
- 기존 결정을 존중한다: 후보 공통 schema(ADR-059·5), enum 정직화(T-169), `pt_source`는 enum이 아닌 `metadata`(ADR-055), geometry 기본 제외(ADR-059·2).

## 표면 요약 (현재)

| endpoint | method | input | response | 후보 컬렉션 | 페이지네이션 |
|----------|--------|-------|----------|------------|-------------|
| `/v2/geocode` | POST | `GeocodeV2Input` | `GeocodeV2Response` | `candidates: CandidateV2[]` | `limit`(≤100), `total` 없음 |
| `/v2/reverse` | POST | `ReverseV2Input` | `ReverseV2Response` | `candidates: CandidateV2[]` | 없음 |
| `/v2/search` | POST | `SearchV2Input`(extends `Page`) | `SearchV2Response` | `candidates: CandidateV2[]` + `total` | `page`/`size`(≤100) + `total` |
| `/v2/regions/within-radius` | POST | `RegionsWithinRadiusInput` | `RegionsWithinRadiusResponse` | `sido`/`sigungu`/`emd: RegionWithinRadiusItem[]` | 없음(그룹 배열) |

> 위 표는 audit 시점(2026-06-16) 기준이다. T-266~T-268로 ①~④ 차원이 모두 반영됐다 — 각 §의 "반영"
> 표시와 `README.md`(라이브 사용자-facing 규약)가 최신이다. 특히 `/v2/reverse`는 공개 `limit`이 없고
> (`radius_m` 반경 제어), 모든 v2 응답이 공통 header `{status, query_id, input}`를 가지며,
> 후보 `point`는 `PointV2{lon, lat}`다.

---

## 1. 응답 envelope 일관성

- **현재**: `Geocode/Reverse/SearchV2Response`는 `status: Status` + `query_id` + `input`(echo) + `candidates` + `region_hint_applied`를 공유한다. **`RegionsWithinRadiusResponse`는 `status`/`query_id`/`input`이 전혀 없고** `center`/`radius_km`/`sido`/`sigungu`/`emd`만 가진다.
- **문제**: 클라이언트가 v2 엔드포인트 전반에서 `status`/`query_id`(trace)를 균일하게 읽을 수 없다. SDK/UI가 endpoint마다 다른 envelope 분기를 짜야 한다.
- **목표 컨벤션**: 모든 v2 응답은 공통 header `{status, query_id, input}`를 가진다. 결과 본문(`candidates` 또는 도메인 특화 배열)은 header 아래에 둔다.
- **변경 성격**: `regions/within-radius`에 header 추가 = **breaking(additive 필드지만 envelope 재배치)**. 후속 task로 `RegionsWithinRadiusResponse`를 공통 header 위에 올린다.

## 2. 후보 enum (source / match_kind / point_precision)

T-169(enum 정직화)가 `postal`/`category`/`cache`를 제거하고 `detail`(예약)·`poi`를 추가했다. 본 재audit의 producer 추적 결과:

| enum | 값 | producer 현황 |
|------|----|--------------|
| `V2MatchKind` | `road`·`parcel`·`region`·`sppn`·`poi` | **실 producer 있음** |
| `V2MatchKind` | `keyword` | near-dead — keyword-only는 search로 라우팅되어 `poi`가 됨. `keyword`+다른 surface 동시 입력일 때만 emit |
| `V2MatchKind` | `detail` | **미emit — T-169가 typed 상세주소용 예약값으로 의도적 보존** |
| `V2PointPrecision` | `centroid`·`grid_cell` | **실 producer 있음** |
| `V2PointPrecision` | `exact`·`interpolated`·`approximate` | **미emit — "정밀도 계층" 명목으로 보존(producer 없음)** |
| `V2Source` | `local` | 기본·실 producer |
| `V2Source` | `vworld`·`juso` | `fallback="api"` + local NOT_FOUND + region_hint 없음일 때만 emit(조건부 live) |

- **문제**: 미emit 값(`detail`, `exact`, `interpolated`, `approximate`)이 published enum에 섞여, 소비자가 "서버가 이 값을 보낼 수 있다"고 오해한다. "정직한 enum"과 "예약/확장 enum"이 한 Literal에 혼재한다.
- **목표 컨벤션**: **published enum = 현재 emit되는 값.** 예약/확장 예정 값은 schema에 올리지 않고 본 문서·ADR에 "예약 목록"으로 명시한다(producer가 생기면 그때 enum에 추가 + typegen). 조건부 live(`vworld`/`juso`)는 schema description에 "fallback 경로에서만" 주석.
- **변경 성격**: `detail`/`exact`/`interpolated`/`approximate` 제거 = **breaking(응답 enum 축소)**. 단 서버가 보낸 적 없는 값이라 실제 응답 역직렬화는 깨지지 않는다(소비자가 enum을 exhaustive하게 다뤘다면 분기 제거 필요). T-169가 의도적으로 보존했으므로 이 변경은 **T-169 결정의 재고**이며 ADR-060에서 명시 결정한다.

## 3. 페이지네이션 (limit형 vs page형)

- **현재**: 네 가지 컬렉션 모양 — geocode는 `limit`-capped `candidates`(no `total`), **reverse는 공개 `limit`/`page`/`total`이 없고 `radius_m` 반경 내 거리순 후보**, search는 `page`/`size`+`total`, regions는 그룹 배열(no total/page).
- **문제**: 컬렉션 페이징 규약이 endpoint마다 달라 SDK가 일관 페이저를 못 만든다.
- **목표 컨벤션**:
  - **ranked-candidate 엔드포인트**: 페이지네이션 없음. **geocode**는 `limit`(≤100)로 상위 N 후보, **reverse**는 공개 `limit` 없이 `radius_m` 반경 내 거리순 후보. (정렬된 best-match는 페이징 대상이 아니다.) → 문서화.
  - **collection 엔드포인트(search)**: `page`/`size`(≤100) + `total`. → 현 상태 유지·문서화.
  - **regions/within-radius**: 그룹 배열에 각 레벨 `total`(또는 group별 count)을 노출하거나, "공간 조회는 페이징하지 않는다"를 명문화. → 작은 additive 또는 doc.
- **변경 성격**: 주로 **문서화** + regions에 count 추가(additive).

## 4. v2 전용 error 모델

- **현재(T-268 반영 ✅)**: v2 API 검증/도메인 에러는 전용 `V2ErrorEnvelope` `{status:"ERROR", query_id, error:{code, message, hint?, field?}}`를 쓴다(`api/responses.py`의 path-aware `error_payload`). 성공과 같은 trace 키 `query_id`를 공유하고, v2 4경로 모두 OpenAPI에 `400`을 명세하고 자동 `422`를 억제한다. 레거시 `{response:{errorCode}}`는 v2에서 폐기됐다(비-v2 비-vworld 경로 admin/zipcode/pobox만 유지). 교차-cutting 인프라 게이트(GeoIP 403)는 전 표면 공유 legacy 형태 유지.
- **이전 문제(해결됨)**: 성공은 `{status, query_id, ...}`인데 에러는 `{response:{errorCode}}`로 envelope이 갈리고 `query_id`가 에러에 없어 trace가 끊겼다. → `V2ErrorEnvelope`로 통일(T-219 M4/#305 input-safety 결론 + ADR-062).
- **변경 성격**: breaking(에러 body 재구성). T-173 input-safety(구조화 4xx)는 유지하고 shape만 변경. ADR-062.

## 5. `include_geometry` / `bbox` 대칭성

- **현재**: `GeocodeV2Input`만 `include_geometry`(opt-in geometry)와 `bbox`(공간 필터)를 둘 다 가진다. `ReverseV2Input`은 **둘 다 없음**. `SearchV2Input`은 `bbox`는 있으나 `include_geometry` 없음. 그러나 출력 `CandidateV2`는 세 endpoint 모두 `geometry`/`bbox` 필드를 가진다.
- **문제**: reverse/search 호출자는 candidate에 geometry를 채울 방법이 없다(출력엔 필드가 있는데 입력 opt-in이 없다). 비대칭이 "이 endpoint는 geometry를 줄 수 있나?"를 불명확하게 만든다.
- **목표 컨벤션**: geometry는 후보 단위 부가정보이므로 **candidate를 반환하는 모든 v2 endpoint(geocode/reverse/search)가 `include_geometry`(기본 false, ADR-059)를 동일하게 받는다.** `bbox`(공간 필터)는 의미 있는 endpoint(geocode/search)에 두고 reverse(이미 점+radius)에는 두지 않음을 명문화.
- **변경 성격**: reverse/search에 `include_geometry` 추가 = **additive(non-breaking 입력 필드)**. 우선 처리 권장.
- **반영 ✅ (T-266/#308)**: `ReverseV2Input`/`SearchV2Input`에 `include_geometry`(기본 false)를 추가하고, geocode의 후보 도형 enrich 로직을 공용 `_enrich_candidates_with_geometry`로 추출해 세 endpoint가 동일 규칙(`region`→region polygon, `road`/`parcel`+건물 key→building polygon, else `null`)을 쓴다. geocode 동작은 무변경. **실제 채워지는 범위**(#317 리뷰 반영): search `type="district"` 후보가 region 도형을 받는다(시도 2자리 포함 — 2자리 코드를 `sig_cd`로 보존해 `region_geometry`의 ctprvn 조회로 해석). **현재 `null`인 케이스**: ① reverse local 후보(도로명/지번)와 ② search 도로명/지번/장소 후보는 건물 도형 조회 key(`bd_mgt_sn`/`rncode_full`/`bjd_cd`/건물번호)가 각각 v1 reverse 결과·v1→v2 search 변환에서 보존되지 않아 building polygon을 못 받는다. 이 key/좌표 기반 조회 보강은 후속으로 남긴다. `bbox`(reverse 제외)는 현행 유지. 후보의 채워지지 않은 선택
필드(`geometry`/`bbox`/`point_precision`/`distance_m`)는 DTO에서는 `None`이고, v2 라우터가
`response_model_exclude_none=True`라 **REST 응답에서는 해당 필드가 생략**된다(`null` 아님).

## 6. 좌표·반경 네이밍·단위

- **현재**:
  - 입력 좌표: `lon`/`lat`(reverse·regions), `min_lon`/…(BBoxV2). **출력 후보 좌표는 `Point{x, y}`**(x=lon, y=lat).
  - 반경: `ReverseV2Input.radius_m`(미터) vs `RegionsWithinRadiusInput.radius_km`(킬로미터).
- **문제**: 외부 계약에서 입력은 `lon`/`lat`인데 출력 후보 점은 `{x,y}`라 명명이 갈린다(x=lon은 주석으로만). 반경 단위가 endpoint마다 다르다(`_m` vs `_km`).
- **목표 컨벤션**:
  - 외부 v2 좌표는 **항상 `lon`/`lat`** 으로 노출한다(내부 PostGIS x/y와 분리). `CandidateV2.point`도 `{lon, lat}` 모양으로 노출(또는 명시적으로 x=lon 문서화). 
  - 반경은 **단위 suffix 필수** 규약을 명문화(`radius_m` = 미터, `radius_km` = 킬로미터). 점-수준 조회는 미터, 지역-수준 조회는 km가 자연스러우므로 단위 통일보다 **suffix로 단위를 항상 드러내는 규약**을 채택.
- **변경 성격**: 후보 point를 `{lon,lat}`로 = **breaking(출력 좌표 키 변경)**. 반경 suffix는 이미 명시적이라 **doc**.

## 7. GET/POST · 버저닝 · service 메타

- **현재**: v2 4개 endpoint 모두 **POST**(structured body). v1 vworld는 GET. v2 응답엔 `query_id`만 있고 **`ServiceMeta`(name/version/operation)가 없다**(v1은 있음). 버전 필드 없음.
- **문제**: v2 trace/버전 표기 규약이 암묵적이다. v1과 다른 게 의도인지 불명확.
- **목표 컨벤션**:
  - **POST 고정**: v2는 구조화 쿼리(다중 surface·bbox·region hint)라 POST body가 맞다. GET 미지원을 명문화.
  - **버전·trace**: v2 envelope에 선택적 메타(`service: {version}` 또는 최소 `api_version`)를 두거나, `query_id`를 공식 trace 키로 명문화. v1의 `ServiceMeta`(vworld 호환용)와 분리.
- **변경 성격**: POST 고정은 **doc**. 버전 메타 추가는 **additive**(택1: envelope 메타 vs query_id-only 명문화 — ADR 결정).

## 8. OpenAPI / `api.gen.ts` 정합

- **현재**: v2 라우트는 `response_model`로 직렬화(v1과 달리 raw response 아님)라 OpenAPI가 wire를 대체로 반영. CI가 `openapi.json` drift 0 + frontend typegen drift 0을 강제(ADR-059 결과). 본 audit producer 추적상 enum schema는 DTO와 byte-일치(드리프트 없음).
- **목표 컨벤션**: 모든 v2 변경은 `python scripts/export_openapi.py` + `npm run gen:types` 재생성을 동반하고 CI drift 0을 유지한다. (현행 유지.)
- **변경 성격**: **doc/프로세스**(현행 유지).

---

## 우선순위(권고)

ADR-060에서 확정하되, 권고 순서는 다음과 같다(낮은 위험·높은 일관성 우선):

1. **additive·doc 먼저** — §5 reverse/search `include_geometry` 추가 **✅(T-266/#308)**, §3·§6·§7·§1 규약 문서화 **✅(T-267, `README.md`)**. (non-breaking, 완료)
2. **enum 정직화 재고**(§2) — `detail`/`exact`/`interpolated`/`approximate`를 published enum에서 빼고 예약 목록으로. **✅(T-268)**
3. **envelope 통일**(§1) + **error 모델**(§4, #305 합류) — `regions/within-radius` 공통 header化 + v2 error envelope 도입. **✅(T-268)**
4. **좌표 출력 lon/lat**(§6) — `CandidateV2.point` `{x,y}`→`{lon,lat}`(`PointV2`). **✅(T-268)**

①(T-266/T-267)은 non-breaking으로 먼저, breaking 묶음 ②③④는 **T-268에서 일괄 적용**했다(v2 미배포 중 사용자 지시로 배포 전 정리; ADR-062). v2 error envelope 범위는 API 검증/도메인 에러에 한정하고 교차-cutting 인프라 게이트(GeoIP 403)는 공유 legacy 형태를 유지한다.
