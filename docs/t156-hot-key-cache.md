# T-156 geocode/reverse hot-key 결과 캐시

## 범위

T-156은 이미 존재하던 `geo_cache` 테이블과 `/v1/admin/cache/metrics`를 실제 geocode/reverse hot path에 연결한다. 새 DB 객체나 OpenAPI 변경은 만들지 않는다.

적용 대상은 다음으로 좁힌다.

- v1 local geocode: `AsyncAddressClient._geocode_v1()`
- v1 local reverse: `AsyncAddressClient._reverse_geocode_v1()`
- v2 geocode/reverse: 내부적으로 위 v1 경로를 통과하는 기본 요청

다음 요청은 캐시 대상에서 제외한다.

- `fallback="api"` geocode. 외부 provider 응답 캐시는 quota·약관·provider별 TTL 정책이 필요하므로 별도 과제로 둔다.
- `keyword` 기반 geocode/search, district/road geometry fallback, `include_geometry=true`의 추가 geometry 조회. 이 경로는 후보 병합·도형 enrich가 섞이므로 T-156의 “hot-key exact/reverse” 범위 밖이다.
- `NOT_FOUND` 응답. 새 적재 직후 negative stale을 줄이기 위해 OK 응답만 저장한다.

## 구현

- `src/kortravelgeo/infra/cache.py`
  - `make_cache_key(service, params)`가 schema version, service, 요청 파라미터를 canonical JSON으로 직렬화한 뒤 SHA-256 digest key를 만든다. key에는 원문 주소 문자열을 직접 넣지 않는다.
  - `GeoCacheRepository.get_json()`은 만료되지 않은 row만 `UPDATE ... RETURNING payload`로 읽고, 같은 transaction에서 `hit_count`와 `last_hit_at`을 갱신한다.
  - `GeoCacheRepository.set_json()`은 `ON CONFLICT (cache_key)` upsert로 payload와 TTL을 갱신하고 hit counter를 0으로 리셋한다.
  - `GeoCacheRepository.clear()`는 serving 데이터 변경 후 `geo_cache`를 비운다.

- `src/kortravelgeo/client.py`
  - geocode/reverse local OK 응답을 `geo_cache.payload` JSONB에 저장한다.
  - cache hit 응답은 v1 `x_extension.source` 또는 reverse item `source`를 `cache`로 표시한다.
  - v2는 ADR-056/T-169 기준으로 v1 `cache` source를 공개 provider가 아닌 `local` source로 접는다.
  - v1 DTO의 VWorld serializer가 `road`/`parcel`을 `ROAD`/`PARCEL`로 바꾸므로, 캐시 저장 payload는 내부 round-trip 검증이 되도록 type field를 소문자로 보정한다.

- `src/kortravelgeo/loaders/postload.py`
  - `refresh_mv()`가 concurrent refresh와 shadow swap 모두 성공한 뒤 `GeoCacheRepository.clear()`를 호출한다.
  - full-load batch, API `mv_refresh`, CLI `ktgctl refresh mv`가 모두 이 helper를 지나므로 MV refresh 후 stale cache가 남지 않는다.

## 설정과 관측

- 기존 설정을 그대로 사용한다.
  - `KTG_CACHE_ENABLED` / `Settings.cache_enabled`
  - `KTG_CACHE_TTL_DAYS` / `Settings.cache_ttl_days`
- 기존 관측면을 그대로 사용한다.
  - `GET /v1/admin/cache/metrics`
  - Prometheus `kor_travel_geo_cache_entries`, `kor_travel_geo_cache_hits`, `kor_travel_geo_cache_expired_entries`

## 검증

- Windows focused unit:
  - `python -m pytest tests/unit/test_t156_geo_cache.py tests/unit/test_postload_mv.py -q` → 14 passed
  - 변경 파일 Ruff 통과
  - 변경 source mypy 통과

- WSL live smoke:
  - artifact: `artifacts/perf/t156-hot-key-cache-smoke-r2/summary.json`
  - 주소: `서울특별시 종로구 자하문로 94`
  - 같은 cache key 반복 호출 뒤 geocode/reverse `hit_count=21`을 확인했다.

| 경로 | cold p50 | cold p95 | hot p50 | hot p95 |
|------|----------|----------|---------|---------|
| geocode | 11.659ms | 11.871ms | 4.269ms | 4.630ms |
| reverse | 13.233ms | 37.455ms | 4.456ms | 4.757ms |

Smoke는 이번 cache key만 삭제하며 기존 `geo_cache` 전체를 비우지 않는다. Reverse cold p95는 5회 표본 중 max 37.455ms가 반영된 값이므로, 개선 판단은 같은 key의 hot hit 여부와 p50/p95 하락을 함께 본다.
