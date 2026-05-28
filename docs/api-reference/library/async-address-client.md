# AsyncAddressClient

`AsyncAddressClient`는 라이브러리 사용자용 async-only 진입점이다. REST API와 같은 core/repository 경로를 사용한다.

## v1 호환 메서드

```python
async with AsyncAddressClient() as client:
    geocode = await client.geocode("서울특별시 강남구 테헤란로 152")
    reverse = await client.reverse_geocode(127.036, 37.501)
    search = await client.search("테헤란로", type="road")
    zipcode = await client.zipcode(address="서울특별시 강남구 테헤란로 152")
```

- `geocode(..., fallback="api")`는 local `NOT_FOUND` 뒤 외부 provider를 시도한다.
- `sig_cd`와 `bjd_cd`는 geocode/search/reverse 모두에서 선택 hint로 사용할 수 있다.
- 응답 구조는 vworld 호환이다.

## v2 메서드

```python
async with AsyncAddressClient() as client:
    geocode = await client.geocode_v2(query="서울특별시 강남구 테헤란로 152")
    reverse = await client.reverse_v2(127.036, 37.501)
    search = await client.search_v2(query="테헤란로", type="road")
```

v2는 `candidates[]` 중심이다. 신규 UI나 provider 비교 로직은 v2를 우선 사용한다.

- `geocode_v2()`는 `query`, `road_address`, `jibun_address`, `keyword` 중 하나를 받는다.
- `geocode_v2()`와 `search_v2()`는 `bbox={"min_lon": ..., "min_lat": ..., "max_lon": ..., "max_lat": ...}` 형식의 EPSG:4326 범위를 받을 수 있다.
- `fallback="api"`는 기존 v1 fallback 결과를 v2 candidate로 감싸는 옵션이며, Kakao/Naver/Google live 호출을 뜻하지 않는다.
- v2 `CandidateV2.distance_m`은 거리 기반 후보의 정식 필드다. `confidence`는 endpoint마다 의미가 다르므로 동일 endpoint 안의 정렬/표시 보조값으로만 사용한다.

## 설정

`settings`를 직접 주입하거나 `.env`의 `KRADDR_GEO_*` 값을 사용한다. 외부 API 키는 `SecretStr`로 다루며 로그에 평문으로 남기지 않는다.
