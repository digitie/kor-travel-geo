# LLM Summary

## 핵심 규칙

- 모든 좌표 입력과 출력은 외부 표면에서 `(lon, lat)` 순서다. DTO `Point`는 `x=lon`, `y=lat`다.
- v1은 vworld 호환 표면이다. 응답 최상위에는 자체 필드를 추가하지 않고, provider 출처와 보강 정보는 `x_extension`에 둔다.
- v2는 후보 목록 표면이다. `candidates[]`의 `address`, `point`, `bbox`, `region`, `place`, `source`, `metadata`를 보고 자체 로컬 데이터를 풍부하게 해석한다.
- Python 라이브러리의 `AsyncAddressClient.geocode()`, `reverse()`, `search()`는 후보 목록 응답만 반환한다. vworld 호환 응답은 REST `/v1/*`에서만 공개한다.
- `CandidateV2.distance_m`은 거리 기반 후보에서 정식 필드다. `metadata.distance_m`가 있더라도 클라이언트는 `distance_m`을 우선 사용한다.
- `CandidateV2.confidence`는 endpoint-local 점수다. geocode는 주소 매칭 신뢰도, reverse는 `1 - distance_m / radius_m`, search는 검색 score를 의미하므로 endpoint 사이에서 단순 비교하지 않는다.
- `CandidateV2.point_precision`은 `exact`, `interpolated`, `centroid`, `approximate` 중 하나다. 현재 1차 구현에서는 precision을 확실히 아는 경우만 채운다.
- `/v2/geocode`의 `include_geometry=true`는 기존 `CandidateV2.point`를 도형으로 대체하지 않는다. 응답은 `point + geometry` 구조이며, `geometry.kind`는 `building`, `region`, `road` 중 하나다.
- `sig_cd`는 2자리 시도 또는 5자리 시군구, `bjd_cd`는 8자리 prefix 또는 10자리 법정동 코드다.
- 외부 API fallback은 명시적으로 `fallback="api"`를 지정할 때만 동작한다.

## 엔드포인트

| API | 메서드/경로 | 입력 핵심 | 출력 핵심 |
|-----|-------------|-----------|-----------|
| v1 geocode | `GET /v1/address/geocode` | `address`, `type`, `fallback`, `sig_cd`, `bjd_cd` | `status`, `refined`, `result.point`, `x_extension` |
| v1 reverse | `GET /v1/address/reverse` | `x`, `y`, `type`, `radius_m`, `sig_cd`, `bjd_cd` | `result[]` |
| v1 search | `GET /v1/address/search` | `query`, `type`, `page`, `size`, `sig_cd`, `bjd_cd` | `result[]`, `total` |
| v2 geocode | `POST /v2/geocode` | `query` 또는 `road_address`/`jibun_address`/`keyword`, `bbox`, `fallback`, `include_geometry` | `candidates[]`, 선택 `geometry` |
| v2 reverse | `POST /v2/reverse` | `lon`, `lat`, `radius_m`, `include_zipcode` | `candidates[]` |
| v2 search | `POST /v2/search` | `query`, `type`, `category_group_code`, `bbox` | `candidates[]`, `total` |

## Source 출처

- `local`: PostGIS 로컬 DB.
- `vworld`: 기존 v1 `fallback="api"`가 vworld에서 온 경우.
- `juso`: 기존 v1 `fallback="api"`가 juso에서 온 경우.
- `cache`: 캐시된 결과.

Kakao/Naver/Google은 live provider로 호출하지 않는다. v2는 이들 API의 좋은 schema 스타일을 참고한 `kraddr-geo` 자체 API다. 향후 live adapter를 추가하면 source enum 확장은 별도 task/ADR에서 약관, 캐시, quota, 출처 표기 정책과 함께 결정한다.

## 선택 기준

- 기존 vworld 호환 소비자와 과거 HTTP 스크립트는 REST v1을 사용한다.
- Python 라이브러리 사용자, 신규 애플리케이션, provider 비교, C1~C10 분석 UI처럼 후보별 출처와 metadata가 중요한 화면은 후보 목록 표면을 사용한다.
- 외부 provider live 비교가 꼭 필요하면 별도 task/ADR에서 약관, 캐시, quota, 출처 표기 정책을 먼저 정해야 한다.
