# AsyncAddressClient

`AsyncAddressClient`는 라이브러리 사용자용 async-only 진입점이다. REST API와 같은 core/repository 경로를 사용한다.

## 공개 메서드

```python
async with AsyncAddressClient() as client:
    geocode = await client.geocode(query="서울특별시 강남구 테헤란로 152")
    reverse = await client.reverse(127.036, 37.501)
    search = await client.search(query="테헤란로", type="road")
    zipcode = await client.zipcode(address="서울특별시 강남구 테헤란로 152")
    regions = await client.regions_within_radius(
        lon=126.978,
        lat=37.5665,
        radius_km=3.0,
        levels=("sigungu", "emd"),
    )
```

- Python 라이브러리의 주소 조회 표면은 후보 목록 응답만 공개한다. 이전 vworld 호환 응답은 REST `/v1/*`에서 유지하고, 라이브러리 내부에서는 REST v1 라우터 전용 내부 어댑터로만 사용한다.
- `geocode()`는 `query`, `road_address`, `jibun_address`, `keyword` 중 하나를 받는다.
- `geocode()`와 `search()`는 `bbox={"min_lon": ..., "min_lat": ..., "max_lon": ..., "max_lat": ...}` 형식의 EPSG:4326 범위를 받을 수 있다.
- `geocode(include_geometry=True)`는 기존 후보 `point`를 유지하면서 `geometry`와 `bbox`를 추가한다. `성복동`은 행정구역 polygon, `성복1로`는 도로 line, `성복1로 35`는 건물 polygon처럼 입력 수준에 맞는 로컬 도형을 붙인다.
- `regions_within_radius()`는 POI `(lon, lat)` 기준 반경 `radius_km` 안에 들어오는 `sido`/`sigungu`/`emd`를 반환한다. `relation="contains"`는 POI 중심점을 포함하는 행정구역이고, `relation="overlaps"`는 중심점은 포함하지 않지만 반경에 걸친 인접 행정구역이다.
- `sig_cd`와 `bjd_cd`는 geocode/search/reverse 모두에서 선택 hint로 사용할 수 있다.
- `fallback="api"`는 기존 v1 fallback 결과를 v2 candidate로 감싸는 옵션이며, Kakao/Naver/Google live 호출을 뜻하지 않는다.
- `CandidateV2.distance_m`은 거리 기반 후보의 정식 필드다. `confidence`는 endpoint마다 의미가 다르므로 동일 endpoint 안의 정렬/표시 보조값으로만 사용한다.
- `geocode_v2()`, `reverse_v2()`, `search_v2()`, `reverse_geocode()`는 공개 Python API가 아니다.

## 설정

`settings`를 직접 주입하거나 `.env`의 `KTG_*` 값을 사용한다. 외부 API 키는 `SecretStr`로 다루며 로그에 평문으로 남기지 않는다.
