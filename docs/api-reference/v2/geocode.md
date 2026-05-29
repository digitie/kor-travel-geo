# v2 Geocode

## 요약

`POST /v2/geocode`는 외부 API 스타일의 장점을 참고한 자체 candidate 목록을 반환하는 신규 주소 → 좌표 API다. Kakao/Naver/Google/VWorld API를 직접 wrapping하지 않는다.

## 입력

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `query` | string | 없음 | 통합 주소 질의 |
| `road_address` | string | 없음 | 도로명 주소로 강제할 때 사용 |
| `jibun_address` | string | 없음 | 지번 주소로 강제할 때 사용 |
| `keyword` | string | 없음 | 장소/키워드 후보 검색 |
| `sig_cd` | string | 없음 | 2자리 시도 또는 5자리 시군구 hint |
| `bjd_cd` | string | 없음 | 8자리 또는 10자리 법정동 hint |
| `bbox` | object | 없음 | `min_lon`, `min_lat`, `max_lon`, `max_lat`로 표현하는 EPSG:4326 비교 범위. 1차 구현은 입력과 응답 schema를 보존하고, 엄격한 공간 필터는 후속으로 확장한다. |
| `limit` | integer | `10` | 최대 후보 수 |
| `fallback` | `none`, `api` | `none` | 외부 API fallback 사용 여부 |

`query`, `road_address`, `jibun_address`, `keyword` 중 하나는 반드시 필요하다.

## 출력

```json
{
  "status": "OK",
  "query_id": "...",
  "input": {"query": "테헤란로 152"},
  "candidates": [
    {
      "confidence": 0.97,
      "match_kind": "road",
      "source": "local",
      "point": {"x": 127.036, "y": 37.501},
      "point_precision": null,
      "distance_m": null,
      "bbox": null,
      "address": {
        "type": "road",
        "full": "서울특별시 강남구 테헤란로 152",
        "road_name_code": "116803122001",
        "postal_code": "06236"
      },
      "region": {"sig_cd": "11680", "bjd_cd": "1168010100"}
    }
  ]
}
```

## 후보 해석

- `match_kind`: `road`, `parcel`, `postal`, `keyword`, `category`, `region`, `sppn`
- `source`: `local`, `vworld`, `juso`, `cache`
- `distance_m`: reverse/nearby/keyword처럼 후보와 기준점 사이의 거리가 있는 경우 정식 필드로 노출한다. geocode 단일 주소 변환에서는 보통 `null`이다.
- `point_precision`: Google `location_type` 패턴을 참고한 좌표 정밀도 필드다. `exact`, `interpolated`, `centroid`, `approximate` 중 하나이며, 현재 local geocode에서는 국가지점번호처럼 면 중심 성격이 분명한 경우 `approximate`만 채운다.
- `confidence`: endpoint-local 점수다. geocode는 v1 매칭 신뢰도, reverse는 검색 반경 대비 거리 기반 점수, search는 검색 score를 뜻한다. 서로 다른 endpoint의 `confidence`를 그대로 비교하지 않는다.
- `bbox`: Google-style viewport/bounds 표현을 참고한 후보 범위 필드다. 현재 로컬 geocode 변환에서는 없을 수 있다.
- `metadata`: 로컬 DB 또는 기존 v1 fallback에서 온 보조 필드다. 안정 공개 필드로 의존하기 전에는 문서화가 필요하다.

## 예시

```bash
curl -X POST "http://localhost:8000/v2/geocode" \
  -H "Content-Type: application/json" \
  -d '{"query":"서울특별시 강남구 테헤란로 152","fallback":"api","sig_cd":"11680"}'
```

```python
async with AsyncAddressClient() as client:
    response = await client.geocode(
        query="서울특별시 강남구 테헤란로 152",
        fallback="api",
        sig_cd="11680",
        bbox={"min_lon": 127.0, "min_lat": 37.45, "max_lon": 127.08, "max_lat": 37.55},
    )
```
