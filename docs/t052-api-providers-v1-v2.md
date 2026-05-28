# T-052: 외부 API 스타일 비교 + API v1(vworld 호환)/v2(신규) 분리 + AI-friendly 문서화

## 상태

- 상태: 1차 구현 완료 (PR 준비)
- 대상 브랜치: `codex/t052-api-v2-providers`
- 관련 ADR: ADR-038
- 사용자 RFC: 2026-05-27 — "vworld API 외 vworld API, kakao API, naver API를 확인하여 geo의 기능에 맞는 함수 및 API 제공 (vworld 호환 API는 v1, 새로운 API는 v2). 그리고 상세 문서화 진행 (사람/AI agent가 활용할 수 있도록)."
- 사용자 재확인: 2026-05-28 — v2는 Kakao/Naver/Google/VWorld를 직접 호출하는 wrapper가 아니라, 각 API 스타일의 장점을 참고해 `kraddr-geo` 자체 API를 새로 만드는 것이다.

## 목적

`python-kraddr-geo`는 vworld OpenAPI 응답 형식을 호환하는 것이 핵심 정체성(ADR-007/-012)이다. 다만 신규 API는 vworld 응답 key 명명에 갇히지 않고, Kakao Local API의 검색/카테고리 표현, Naver Geocoding의 주소 구성요소 표현, Google Geocoding/Places 계열의 후보 목록·viewport·place 표현, VWorld의 공공 좌표/주소 호환성에서 장점을 취한 자체 schema로 제공한다. 본 task는 다음을 분리해 정리한다.

1. 외부 API 스타일의 기능 차이를 매핑하고, 본 라이브러리가 자체 데이터로 노출해야 할 함수/표면을 결정한다.
2. 기존 vworld 호환 응답 표면을 **API v1**(`/v1/*`)로 동결한다. SDK 사용자가 기존 응답 형식을 유지할 수 있게 한다.
3. Kakao/Naver/Google/VWorld 스타일의 장점을 참고한 신규 통합 응답을 **API v2**(`/v2/*`)로 분리한다. `candidate`, `match_kind`, `address`, `region`, `place`, `bbox`, `metadata`를 1차 시민으로 둔다.
4. 사람과 AI agent가 동시에 읽을 수 있도록 OpenAPI + Markdown 한 쌍의 `docs/api-reference/` 문서를 작성한다.

T-052 1차 PR은 v1 표면을 유지하면서 v2 DTO/router/client와 AI-friendly API reference를 추가한다. v2는 외부 provider live adapter를 추가하지 않고 local DB 응답을 자체 candidate schema로 투영한다. 기존 v1 `fallback="api"`의 vworld/juso 호출 정책은 그대로 유지한다.

## 1차 구현 결과

- `src/kraddr/geo/dto/v2.py`: `GeocodeV2Input/Response`, `ReverseV2Input/Response`, `SearchV2Input/Response`, `CandidateV2`, `AddressV2`, `RegionV2`, `PlaceV2`를 추가했다. PR #69 리뷰 후속으로 `distance_m`과 `point_precision`도 v2 candidate의 정식 필드로 올렸다.
- `src/kraddr/geo/api/routers/v2.py`: `POST /v2/geocode`, `POST /v2/reverse`, `POST /v2/search`를 추가했다.
- `AsyncAddressClient`: `geocode_v2()`, `reverse_v2()`, `search_v2()`를 추가했다.
- `core/v2.py`: v1 응답을 v2 candidate schema로 변환한다. 기존 fallback 출처인 `api_vworld`, `api_juso`는 v2에서 각각 `vworld`, `juso`로 정규화한다.
- `docs/api-reference/`: 사람과 AI agent가 함께 읽을 API reference와 LLM 요약을 추가했다.
- `openapi.json`과 `kraddr-geo-ui` 생성 타입은 v2 schema를 포함하도록 갱신한다.

## 외부 API 스타일 매핑

| 기능/스타일 | VWorld 장점 | Kakao 장점 | Naver 장점 | Google 장점 | kraddr-geo v2 결정 |
|-----------|------------|------------|------------|------------|---------------------|
| 주소 → 좌표 | 공공 주소 호환성 | road/jibun 분리와 키워드 검색 흐름 | 주소 구성요소 표현 | 후보 목록, geometry, viewport | `GeocodeV2Response.candidates[]`로 통합 |
| 좌표 → 주소 | 좌표계/공공 reverse 흐름 | 주소와 행정구역 reverse 분리 | road/jibun reverse 구성 | `address_components`, `formatted_address` | `ReverseV2Response.candidates[]`에 address/region 동시 표현 |
| 통합 검색 | 주소 검색 중심 | keyword/category 검색 | structured geocode | Places-style candidate | `SearchV2Response`에 `place`, `category_group_code`, `region`을 흡수 |
| 후보 비교 | 단일 결과 중심 | 문서 배열 | 주소 배열 | `results[]` + confidence/viewport | `candidate.confidence`, `bbox`, `metadata` |
| 거리/정밀도 | 제한적 | `distance` | `distance` | `location_type`, `partial_match`, `viewport` | `distance_m`, `point_precision`, endpoint-local `confidence` |
| 자체 데이터 우선 | 공공 데이터와 호환 | UI 검색 경험 | 구성요소 세분화 | 풍부한 schema | 외부 provider 호출 없이 local DB 결과를 자체 schema로 투영 |

매핑 원칙:

- kraddr-geo v2는 자체 PostGIS 데이터로 응답한다. Kakao/Naver/Google/VWorld API를 단순 전달하거나 wrapper로 노출하지 않는다.
- vworld와의 응답 호환은 v1에서만 보장한다. v2는 외부 API들의 좋은 표현 방식을 참고하되 `kraddr-geo` 자체 schema를 갖는다.
- `category_group_code`는 Kakao 코드를 그대로 고정하는 필드가 아니라, 향후 이 프로젝트의 장소/관리 UI 분류 hint를 담을 확장 지점이다.

## v1 (기존, vworld 호환) 표면 동결

`v1` namespace는 다음 표면을 그대로 유지한다.

- REST: `GET /v1/address/geocode`, `GET /v1/address/reverse`, `GET /v1/address/search`, `GET /v1/zipcode`, `GET /v1/pobox`, `/v1/admin/*`(운영 화면).
- DTO: 현재 `dto/geocode.py`/`dto/reverse.py`/`dto/search.py`의 응답 모델. vworld key 명명(`addresses[]`, `result.point`, `x_extension.*`)을 보존.
- 라이브러리: `AsyncAddressClient.geocode()`, `.reverse()`, `.search()`, `.zipcode()`, `.pobox()`.
- OpenAPI: `openapi.json`의 `/v1/*` paths.

이 동결은 `kraddr-geo-ui`(디버그/관리 UI), 외부 vworld-호환 SDK 사용자, 운영 cron 스크립트를 깨지 않기 위한 것이다.

## v2 (신규 통합) 표면 design

### 책임 분리

- v2 응답은 vworld key 명명에 의존하지 않는다. 새 `dto/v2/*.py` 모듈에서 명확한 자체 schema를 정의한다.
- v2는 v1보다 풍부한 정보를 한 번에 반환한다. address grade, road_address_full, postal_code, region(법정동/행정동/시군구), category, place_keyword 등.
- v2는 hint 입력(T-057 region hint)을 1차 시민으로 받는다. `sig_cd`, `bjd_cd`, `bbox`, `category_group_code`.

### REST 표면 후보

```text
POST /v2/geocode              # JSON body
POST /v2/reverse              # (lon, lat) 입력, 모든 응답 한 번에
POST /v2/search               # 통합 검색: 도로명/지번/키워드/카테고리
GET  /v2/zipcode/{zip_no}
GET  /v2/region/lookup        # 시군구/법정동/행정동 자동완성
POST /v2/transform            # EPSG 변환 (낮은 우선순위)
```

`/v1/*`는 그대로. `/v2/*`는 별도 router로 분리.

### DTO 초안

```python
# dto/v2.py
class GeocodeV2Input(FrozenModel):
    query: str | None = None
    road_address: str | None = None
    jibun_address: str | None = None
    keyword: str | None = None
    sig_cd: str | None = None      # T-057 region hint
    bjd_cd: str | None = None      # T-057 region hint
    bbox: tuple[float, float, float, float] | None = None  # (minx, miny, maxx, maxy) EPSG:4326
    limit: int = 10
    fallback: Literal["none", "api"] = "none"

class CandidateV2(FrozenModel):
    confidence: float                       # 0~1
    match_kind: Literal["road","parcel","postal","keyword","category","region","sppn"]
    address: GeocodeV2Address                # 통합 address 표현
    point: GeocodeV2Point                    # (lon, lat) + EPSG
    point_precision: Literal["exact","interpolated","centroid","approximate"] | None = None
    distance_m: float | None = None
    region: GeocodeV2Region | None = None    # 시도/시군구/법정동/행정동
    place: GeocodeV2Place | None = None      # 키워드/카테고리 매칭 시
    bbox: GeocodeV2BBox | None = None
    source: Literal["local","vworld","juso","cache"] = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)

class GeocodeV2Response(FrozenModel):
    candidates: tuple[CandidateV2, ...]
    region_hint_applied: RegionHint | None = None
    query_id: str
```

`dto/v2/reverse.py`, `dto/v2/search.py`도 유사한 candidate-list 형태.

### 라이브러리 표면

```python
class AsyncAddressClient:
    # v1은 그대로
    async def geocode(self, ...) -> GeocodeResponse: ...

    # v2 신규
    async def geocode_v2(
        self,
        *,
        query: str | None = None,
        road_address: str | None = None,
        jibun_address: str | None = None,
        keyword: str | None = None,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 10,
        fallback: Literal["none","api"] = "none",
    ) -> GeocodeV2Response: ...

    async def reverse_v2(self, lon: float, lat: float, *, include_region: bool = True, ...) -> ReverseV2Response: ...
    async def search_v2(self, *, query: str, category_group_code: str | None = None, sig_cd: str | None = None, ...) -> SearchV2Response: ...
```

## 외부 API 직접 호출 정책

- 본 라이브러리의 default mode는 local PostGIS 응답이다. 외부 API는 `fallback="api"`일 때만 호출한다.
- T-052 범위에서 새 외부 provider 직접 호출은 추가하지 않는다. 기존 ADR-019의 vworld/juso geocode fallback만 유지한다.
- v2 `fallback="api"`는 기존 v1 fallback 결과를 candidate schema로 감싸기 위한 호환 옵션이다. 이 옵션이 Kakao/Naver/Google 호출을 의미하지 않는다.
- 외부 API 스타일 분석은 schema 설계를 위한 참고 자료다. 운영 키, quota, provider 약관, 캐시 정책을 새로 늘리지 않는다.
- `V2Source`는 현재 구현 가능한 `local`, `vworld`, `juso`, `cache`만 허용한다. Kakao/Naver/Google live adapter가 실제로 필요해지면 source enum 확장도 별도 task/ADR에서 함께 처리한다.

## AI-friendly 문서화

### `docs/api-reference/` 구조

```
docs/api-reference/
├── README.md                    # 표면 한눈에 보기 + AI agent 진입점
├── v1/
│   ├── geocode.md               # v1 응답 schema, vworld 호환 보장, 예시 request/response
│   ├── reverse.md
│   └── search.md
├── v2/
│   ├── geocode.md               # v2 응답 schema, region hint, category, source
│   ├── reverse.md
│   └── search.md
├── library/
│   └── async-address-client.md  # AsyncAddressClient 함수별 signature/예시
└── operators/
    └── api-keys.md              # vworld/juso/epost 키 발급/설정/한도
```

`zipcode`, `pobox`, `region-lookup`, `transform`, `error-codes`, `caching` 같은 문서는 1차 구현 범위에서는 별도 파일로 만들지 않고, 실제 endpoint/API 확장이 확정되는 후속 task에서 추가한다.

각 markdown 파일은 다음 구조를 갖는다.

```markdown
# {endpoint name}

## 요약 (1줄)
## 사용 시나리오 (사람/agent 양쪽)
## 입력 schema (필드별 타입/예시/제약)
## 출력 schema (필드별 타입/예시/제약)
## 예시 (curl + Python `AsyncAddressClient` + JSON)
## 에러 (E*, HTTP code)
## 관련 ADR/타 endpoint
```

### AI agent용 추가 자료

- `docs/api-reference/llm-summary.md`: 전체 표면을 LLM이 한 화면에서 파악할 수 있는 압축 요약(엔드포인트/파라미터/응답 핵심만).
- 저장소 루트 `openapi.json`: 기계가 직접 import 가능한 표면.
- 각 함수의 docstring을 `numpy` 스타일로 통일하고 예시 포함. `kraddr.geo` import 시 docstring으로 충분히 학습 가능.

## 구현 순서

1. 완료: `docs/api-reference/` skeleton 생성 + `llm-summary.md`.
2. 완료: T-056 `core.address` helper를 기준으로 juso 좌표 API 필수 코드 정규화를 재사용.
3. 완료: v1 표면 동결 — 현재 응답 형식을 `api-reference/v1/*.md`로 캡처.
4. 완료: v2 DTO 초안 (`src/kraddr/geo/dto/v2.py`).
5. 완료: v2 router skeleton (`src/kraddr/geo/api/routers/v2.py`) — 응답은 local 우선, candidate-list.
6. 완료: `AsyncAddressClient.geocode_v2/reverse_v2/search_v2` 추가.
7. 완료: 새 외부 provider adapter는 추가하지 않는 것으로 확정. v2는 local/vworld/juso/cache source만 표현한다.
8. 완료: OpenAPI export에 `/v2/*` 포함, `kraddr-geo-ui`도 `types/api.gen.ts` 자동 갱신.
9. 완료: `docs/api-reference/v2/*.md` 1차 작성.

## 검증 기준

- v1 path와 기존 query parameter는 유지한다. `x_extension.source` enum은 기존 `local/api_vworld/api_juso/cache`를 유지한다.
- v2 응답 schema 단위 테스트 — DTO validation, candidate 변환, region hint propagation.
- v2 router/client 변환 단위 테스트 — local/vworld/juso fallback 결과를 자체 candidate schema로 변환한다.
- `docs/api-reference/`의 모든 예시가 실제 응답과 일치(CI에서 sample request 실행).
- `AsyncAddressClient.geocode_v2` 라이브러리 사용 시 명시적 import만으로 동작.

## 남은 위험

- 외부 API 스타일을 참고한 필드가 실제 로컬 데이터로 얼마나 채워지는지 endpoint별 문서와 UI에서 명확히 표시해야 한다.
- v1과 v2를 동시에 유지하면 maintenance 비용 ↑. 6~12개월 단위로 v1 deprecation 일정을 검토.
- v2 응답이 vworld key 명명과 분리되면 일부 SDK 사용자가 두 schema를 모두 다뤄야 한다. migration guide를 `docs/api-reference/v2/migration-from-v1.md`에 작성.

## 관련 ADR/Task

- ADR-007/-012/-019: 응답 호환과 외부 fallback 원칙.
- ADR-038: API v1/v2 분리와 자체 통합 candidate 정책.
- T-053: Admin UI에서 v1/v2 결과를 같은 화면에서 비교할 수 있도록.
- T-057: region hint 기반 검색 가속(v2 입력 필드와 직접 연결).
