# T-052: 외부 provider 비교 + API v1(vworld 호환)/v2(신규) 분리 + AI-friendly 문서화

## 상태

- 상태: 설계 (구현 전)
- 대상 브랜치: `agent/<agent>-t052-*`
- 관련 ADR: ADR-038(예정)
- 사용자 RFC: 2026-05-27 — "vworld API 외 vworld API, kakao API, naver API를 확인하여 geo의 기능에 맞는 함수 및 API 제공 (vworld 호환 API는 v1, 새로운 API는 v2). 그리고 상세 문서화 진행 (사람/AI agent가 활용할 수 있도록)."

## 목적

`python-kraddr-geo`는 vworld OpenAPI 응답 형식을 호환하는 것이 핵심 정체성(ADR-007/-012). 하지만 운영자와 사용자 입장에서는 kakao Local API와 naver Geocoding/Reverse API에서 제공하는 기능(예: 카테고리 기반 장소 검색, 키워드 검색, 좌표-주소 reverse 통합)도 유용하다. 본 task는 다음을 분리해 정리한다.

1. 세 provider의 기능 차이를 매핑하고, 본 라이브러리가 노출해야 할 함수/표면을 결정한다.
2. 기존 vworld 호환 응답 표면을 **API v1**(`/v1/*`)로 동결한다. SDK 사용자가 기존 응답 형식을 유지할 수 있게 한다.
3. kakao/naver 형식을 흡수한 신규 통합 응답을 **API v2**(`/v2/*`)로 분리한다. `category`, `place_keyword`, `address_grade`, `road_address_full`, `bounded_within` 같은 신규 필드를 1차 시민으로 둔다.
4. 사람과 AI agent가 동시에 읽을 수 있도록 OpenAPI + Markdown 한 쌍의 `docs/api-reference/` 문서를 작성한다.

T-052는 코드 한 줄도 아직 안 쓴다. 본 문서가 v2 design 1차 reference다.

## 외부 provider 매핑

| 기능 | vworld OpenAPI | kakao Local API | naver Geocoding/Reverse API | kraddr-geo 현재 | kraddr-geo v2 결정 |
|------|----------------|-----------------|------------------------------|------------------|---------------------|
| 정주소 → 좌표 | `address/getCoord` | `/v2/local/search/address.json` | `/map-geocode/v2/geocode` | `core.geocoder.geocode` (v1 호환) | v2 `geocode(...) → GeocodeV2Response` (road/jibun/postal/keyword 모두 시도) |
| 좌표 → 주소 | `coord/getAddress` | `/v2/local/geo/coord2address.json`, `coord2regioncode.json` | `/map-reversegeocode/v2/gc` | `core.reverse_geocoder.reverse` | v2 `reverse(...) → ReverseV2Response` (road/jibun/admin region/legal region 동시) |
| 키워드 검색 | (제한적, `search/address`) | `/v2/local/search/keyword.json` | (별도 search API, `place_search`) | `core.searcher.search` (도로명/지번 trgm) | v2 `search(...) → SearchV2Response` + `category_group_code` hint |
| 카테고리 검색 | 없음 | `/v2/local/search/category.json` | (별도) | 없음 | v2 `search(... category_group_code=)` 로 흡수 |
| 우편번호 → 주소 | 없음 (juso 별도) | 없음 | 없음 (juso 별도) | `core.zipcoder` + `pobox` | v1 그대로 유지 |
| 행정구역 polygon | 없음 (vworld WMS 별도) | `/v2/local/geo/coord2regioncode.json` | 없음 | `tl_scco_*`, `mv_geocode_target` | v2 `reverse(... include_region=true)` |
| coordinate transform | vworld `coord/transform` | 없음 | 없음 | `infra.crs` 내부 | v2 endpoint `/v2/transform` 후보 (낮은 우선순위) |

매핑 원칙:

- kraddr-geo는 자체 PostGIS 데이터로 응답한다. 외부 provider는 fallback(`fallback="api"`)에서만 호출한다(ADR-019).
- vworld와의 응답 호환은 v1에서만 보장한다. v2는 kakao/naver 표현을 흡수해 명확한 자체 schema를 갖는다.
- kakao의 `category_group_code`(`MT1`, `CS2`, `PS3` 등)는 본 라이브러리 단계에서는 도입하지 않는다. v2 schema는 같은 의미를 갖는 자체 enum `place_category_code`를 갖고, kakao adapter는 매핑만 책임진다.

## v1 (기존, vworld 호환) 표면 동결

`v1` namespace는 다음 표면을 그대로 유지한다.

- REST: `POST /v1/geocode`, `POST /v1/reverse`, `GET /v1/search`, `GET /v1/zipcode`, `GET /v1/pobox`, `/v1/admin/*`(운영 화면).
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
POST /v2/geocode              # query string 또는 JSON body
POST /v2/reverse              # (lon, lat) 입력, 모든 응답 한 번에
GET  /v2/search               # 통합 검색: 도로명/지번/키워드/카테고리
GET  /v2/zipcode/{zip_no}
GET  /v2/region/lookup        # 시군구/법정동/행정동 자동완성
POST /v2/transform            # EPSG 변환 (낮은 우선순위)
```

`/v1/*`는 그대로. `/v2/*`는 별도 router로 분리.

### DTO 초안

```python
# dto/v2/geocode.py
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

class GeocodeV2Candidate(FrozenModel):
    confidence: float                       # 0~1
    match_kind: Literal["road","jibun","postal","keyword","region"]
    address: GeocodeV2Address                # 통합 address 표현
    point: GeocodeV2Point                    # (lon, lat) + EPSG
    region: GeocodeV2Region | None = None    # 시도/시군구/법정동/행정동
    place: GeocodeV2Place | None = None      # 키워드/카테고리 매칭 시
    source: Literal["local","vworld","kakao","naver"] = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)

class GeocodeV2Response(FrozenModel):
    candidates: tuple[GeocodeV2Candidate, ...]
    region_hint_applied: GeocodeV2RegionHint | None = None
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

## 외부 provider adapter 정책

- 본 라이브러리의 default mode는 local PostGIS 응답이다. 외부 API는 `fallback="api"` 또는 v2의 `source=` 명시 시에만 호출.
- T-056에서 추가한 `core.address` helper를 provider adapter의 공통 주소 코드 정규화 계층으로 사용한다. Juso 계열 `admCd`/`rnMgtSn`/`udrtYn`/`buldMnnm`/`buldSlno`, vworld/kakao/naver가 반환하는 법정동/도로명관리번호 유사 필드는 adapter 안에서 먼저 정규화한 뒤 v2 candidate로 변환한다.
- adapter 책임:
  - `infra/external/vworld.py` — 기존(ADR-019). 응답을 v1 또는 v2 candidate로 변환.
  - `infra/external/kakao.py` — 신규. kakao Local API 응답을 v2 candidate로 변환. API key는 `KRADDR_GEO_KAKAO_REST_API_KEY` (옵션).
  - `infra/external/naver.py` — 신규. naver Geocoding/Reverse API 응답을 v2 candidate로 변환. API key는 `KRADDR_GEO_NAVER_CLIENT_ID`/`KRADDR_GEO_NAVER_CLIENT_SECRET` (옵션).
- 외부 provider 키가 설정되지 않으면 adapter는 사용 불가 상태로 두고, fallback 호출은 즉시 `NOT_FOUND` 또는 적절한 `source="local"` 응답만 반환.
- 모든 외부 호출은 `geo_cache`에 캐시(ADR-009/-019 패턴).
- 호출 한도와 약관은 운영자 책임(README 법적 고지).

## AI-friendly 문서화

### `docs/api-reference/` 구조

```
docs/api-reference/
├── README.md                    # 표면 한눈에 보기 + AI agent 진입점
├── v1/
│   ├── geocode.md               # v1 응답 schema, vworld 호환 보장, 예시 request/response
│   ├── reverse.md
│   ├── search.md
│   ├── zipcode.md
│   └── pobox.md
├── v2/
│   ├── geocode.md               # v2 응답 schema, region hint, category, source
│   ├── reverse.md
│   ├── search.md
│   ├── region-lookup.md
│   └── transform.md
├── library/
│   ├── async-address-client.md  # AsyncAddressClient 함수별 signature/예시
│   └── error-codes.md           # E0100, E0200, ... 매핑
└── operators/
    ├── api-keys.md              # vworld/kakao/naver 키 발급/설정/한도
    └── caching.md               # geo_cache TTL/예시
```

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
- `docs/api-reference/openapi.json` 링크: 기계가 직접 import 가능한 표면.
- 각 함수의 docstring을 `numpy` 스타일로 통일하고 예시 포함. `kraddr.geo` import 시 docstring으로 충분히 학습 가능.

## 구현 순서

1. `docs/api-reference/` skeleton 생성 + `llm-summary.md`.
2. T-056 `core.address` helper를 기준으로 provider별 주소 코드 field mapping 표를 확정.
3. v1 표면 동결 — 현재 응답 형식을 `api-reference/v1/*.md`로 캡처.
4. v2 DTO 초안 (`src/kraddr/geo/dto/v2/__init__.py`).
5. v2 router skeleton (`src/kraddr/geo/api/v2/*`) — 응답은 local 우선, candidate-list.
6. `AsyncAddressClient.geocode_v2/reverse_v2/search_v2` 추가.
7. kakao/naver adapter (`infra/external/kakao.py`, `naver.py`) — fallback에서만 호출.
8. OpenAPI export에 `/v2/*` 포함, `kraddr-geo-ui`도 `types/api.gen.ts` 자동 갱신.
9. `docs/api-reference/v2/*.md` 완성.

## 검증 기준

- v1 `openapi.json` schema diff 없음 (회귀 0).
- v2 응답 schema 단위 테스트 — DTO validation, candidate sorting by confidence, region hint propagation.
- kakao/naver adapter 응답 변환 단위 테스트 — recorded fixture 기반.
- `docs/api-reference/`의 모든 예시가 실제 응답과 일치(CI에서 sample request 실행).
- `AsyncAddressClient.geocode_v2` 라이브러리 사용 시 명시적 import만으로 동작.

## 남은 위험

- kakao/naver는 약관에 따라 캐싱·재배포 제한이 다르다. cache TTL과 source 표기 정책을 ADR-019 후속에서 보강.
- v1과 v2를 동시에 유지하면 maintenance 비용 ↑. 6~12개월 단위로 v1 deprecation 일정을 검토.
- v2 응답이 vworld key 명명과 분리되면 일부 SDK 사용자가 두 schema를 모두 다뤄야 한다. migration guide를 `docs/api-reference/v2/migration-from-v1.md`에 작성.

## 관련 ADR/Task

- ADR-007/-012/-019: 응답 호환과 외부 fallback 원칙.
- ADR-038(예정): API v1/v2 분리와 외부 provider 흡수 정책.
- T-053: Admin UI에서 v1/v2 결과를 같은 화면에서 비교할 수 있도록.
- T-057: region hint 기반 검색 가속(v2 입력 필드와 직접 연결).
