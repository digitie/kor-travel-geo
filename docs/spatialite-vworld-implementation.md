# PostGIS · vworld 호환 구현 (구 SpatiaLite 문서)

> **이름 보존 안내**: 본 파일은 이전(v1) `SpatiaLite + vworld 호환` 구현 계획 문서의 자리를 그대로 잇는다. `main`에서는 PostgreSQL + PostGIS로 전환했으므로 본문도 새 사양에 맞춰 갱신했다. 이전 SpatiaLite 기반 계획은 `v1` 브랜치에서 동일 파일명으로 확인할 수 있다(ADR-001).

본 문서는 `kraddr-geo`이 vworld OpenAPI와 동일한 응답 구조를 유지하면서 1차 데이터를 PostgreSQL + PostGIS에서 직접 처리하는 방식을 정리한다.

## 데이터 우선순위

지오코딩/역지오코딩의 1차 데이터는 텍스트 정본 위에 만든 서빙 MV다(ADR-007/ADR-012). 마스터 테이블을 직접 조회하지 않는다.

1. `mv_geocode_target` — 텍스트 정본 `tl_juso_text`를 평면화한 서빙 MV (지오코딩/역지오코딩 1차). 대표 좌표(`pt_5179`/`pt_4326`)와 출처(`pt_source`)를 포함한다. 역지오코딩도 이 MV의 `pt_5179`로 nearest/radius를 수행한다.
2. 대표 좌표 우선순위 — `tl_locsum_entrc`(위치정보요약DB 대표 출입구, 1순위) → 같은 기준월일 때만 `tl_roadaddr_entrc`(도로명주소 출입구, fallback) → `tl_navi_buld_centroid`(내비게이션용DB 건물 중심, centroid fallback). 이 우선순위는 `mv_geocode_target` 빌드 시 흡수된다.
3. `mv_geocode_text_search` — fuzzy geocode/broad search 후보용 helper MV (T-061). `mv_geocode_target`에서 재생성하는 read-only 보조 객체.
4. `tl_spbd_buld_polygon` — 건물 polygon. 정합성 검증(C2/C4/C5)용 도형 보조 전용이며 서빙 좌표원이 아니다.
5. `tl_sprd_manage` / `tl_sprd_rw` — 도로명·도로 폴리라인/도로면 polygon (정합성 C8 도로 인접성 보조)
6. `tl_kodis_bas` — 우편번호 polygon
7. `tl_scco_*` — 시도·시군구·읍면동·리 행정 경계 (검증 및 fallback)
8. 외부 API (vworld, juso) — `fallback="api"` 옵션 시 폴백

## 핵심 테이블

자세한 컬럼·인덱스는 `docs/data-model.md` 참조.

- `tl_juso_text(bd_mgt_sn)` — 도로명주소 한글_전체분 텍스트 정본. 생성 컬럼 `rncode_full`, `rn_nrm`, `buld_nm_nrm`, `pnu`.
- `tl_locsum_entrc(sig_cd, ent_man_no)` — 위치정보요약DB 대표 출입구 좌표 (POINT, 5179). 대표 좌표 1순위.
- `tl_navi_buld_centroid(bd_mgt_sn)` — 내비게이션용DB 건물 중심 (POINT, 5179). centroid fallback.
- `tl_spbd_buld_polygon(bd_mgt_sn)` — 건물 polygon (MULTIPOLYGON, 5179). 도형 보조 전용.
- `tl_kodis_bas(bas_mgt_sn)` — 우편번호 polygon.
- `mv_geocode_target` — 지오코딩/역지오코딩이 사용하는 평면화 서빙 MV. 도로명/지번 매칭 인덱스와 `pt_5179` GiST 인덱스를 모두 갖춤.
- `mv_geocode_text_search` — fuzzy/broad search 후보용 helper MV (T-061).

## 인덱싱

```sql
-- 텍스트 정본 매칭 (geocode primary/secondary)
CREATE INDEX idx_juso_text_road  ON tl_juso_text (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_juso_text_jibun ON tl_juso_text (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
-- 대표 출입구 좌표 nearest/대표 선택
CREATE INDEX idx_locsum_geom     ON tl_locsum_entrc USING GIST (geom);
-- 서빙 MV nearest/radius (reverse 1차 경로)
CREATE INDEX idx_mv_geom5179     ON mv_geocode_target USING GIST (pt_5179);
CREATE INDEX idx_kodis_bas_geom  ON tl_kodis_bas USING GIST (geom);
CREATE INDEX idx_juso_text_rn_trgm
  ON tl_juso_text USING GIN (rn_nrm gin_trgm_ops);
```

`pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` (SKILL.md §4-3).

## vworld 호환 표면

`AsyncAddressClient`가 노출하는 진입점은 vworld의 4개 API와 1:1 대응:

| vworld | `AsyncAddressClient` 메서드 | DTO |
|--------|------------------------------|-----|
| `getcoord` (주소→좌표) | `geocode(address, type, crs, refine, simple, fallback)` | `GeocodeInput`, `GeocodeResponse` |
| `getAddress` (좌표→주소) | `reverse_geocode(lon, lat, crs, type, zipcode, radius_m)` | `ReverseInput`, `ReverseResponse` |
| 통합 검색 | `search(query, type, ...)` | `SearchInput`, `SearchResponse` |
| 우편번호 lookup | `zipcode(address/point/bd_mgt_sn, include_bulk)` | `ZipcodeInput`, `ZipcodeResponse` |

응답 최상위 키(`service`, `status`, `input`, `refined`, `result`)는 vworld와 동일. 자체 부가 정보는 `x_extension` 키 하나에 모은다(ADR-003).

## 외부 API 폴백

`fallback` 옵션:

- `"off"`: 정확 매칭만. 실패 시 `NOT_FOUND`.
- `"local_only"`: 정확 매칭 실패 시 `pg_trgm` fuzzy 후보 5개로 재시도. 외부 호출 없음.
- `"api"`: 위 모두 실패 시 vworld → juso 순서로 외부 폴백. 결과 출처는 `x_extension.source`에 표시(`api_vworld` / `api_juso`).

외부 호출 정책(재시도·회로차단·쿼터 보호)은 `docs/external-apis.md`.

## 적재 후 최적화

`kraddr-geo refresh mv`(`--swap` 옵션으로 shadow 빌드 후 RENAME swap)는 평시 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`(+ helper `mv_geocode_text_search` 동세대 갱신)을 수행한다. `VACUUM (ANALYZE)`는 별도 CLI 서브커맨드가 아니라 DB 측 수동 유지보수 단계이므로, 풀로드/대량 변동분 직후 야간 cron에서 `psql`로 직접 실행한다(예: `VACUUM (ANALYZE) tl_juso_text;`, `ANALYZE mv_geocode_target;`). `maintenance_work_mem`은 트랜잭션 단위로만 상승(`SET LOCAL`).

## 디버거에서 운영까지 동일 환경

`/v1/admin/explain`은 `AsyncAddressClient.engine`을 그대로 사용해 `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`를 실행한다. 디버거에서 본 plan은 운영 쿼리와 같은 search_path, statement_timeout, pool 옵션에서 평가된다 — 디버거가 잘 도는데 운영에서 다르게 동작할 가능성이 차단된다.

## 참고

- 백엔드 사양: `docs/backend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
- 결정: `docs/decisions.md` (ADR-001 ~ ADR-006, ADR-013)
