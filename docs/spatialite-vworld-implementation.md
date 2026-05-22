# PostGIS · vworld 호환 구현 (구 SpatiaLite 문서)

> **이름 보존 안내**: 본 파일은 이전(v1) `SpatiaLite + vworld 호환` 구현 계획 문서의 자리를 그대로 잇는다. master에서는 PostgreSQL + PostGIS로 전환했으므로 본문도 새 사양에 맞춰 갱신했다. 이전 SpatiaLite 기반 계획은 `v1` 브랜치에서 동일 파일명으로 확인할 수 있다(ADR-001).

본 문서는 `addr-kr`이 vworld OpenAPI와 동일한 응답 구조를 유지하면서 1차 데이터를 PostgreSQL + PostGIS에서 직접 처리하는 방식을 정리한다.

## 데이터 우선순위

1. `tl_spbd_entrc` — 출입구 좌표 (지오코딩 1차)
2. `tl_spbd_buld` — 건물 다각형 (출입구가 없을 때 centroid 대안)
3. `tl_sprd_manage` / `tl_sprd_rw` — 도로명·도로 폴리라인 (역지오코딩 보조)
4. `tl_kodis_bas` — 우편번호 polygon
5. `tl_scco_*` — 시도·시군구·읍면동·리 행정 경계 (검증 및 fallback)
6. 외부 API (vworld, juso) — `fallback="api"` 옵션 시 폴백

## 핵심 테이블

자세한 컬럼·인덱스는 `docs/data-model.md` 참조.

- `tl_spbd_buld(sig_cd, bul_man_no)` — 건물. 생성 컬럼 `bjd_cd`, `rncode_full`, `buld_nm_nrm`.
- `tl_spbd_entrc(sig_cd, ent_man_no)` — 출입구 (POINT, 5179).
- `tl_kodis_bas(bas_mgt_sn)` — 우편번호 polygon.
- `mv_geocode_target` — 지오코딩이 사용하는 평면화 MV. 도로명/지번 매칭 인덱스를 모두 갖춤.

## 인덱싱

```sql
CREATE INDEX idx_buld_road_match  ON tl_spbd_buld (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_buld_jibun_match ON tl_spbd_buld (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX idx_entrc_geom       ON tl_spbd_entrc USING GIST (geom);
CREATE INDEX idx_kodis_bas_geom   ON tl_kodis_bas USING GIST (geom);
CREATE INDEX idx_sprd_manage_rn_trgm
  ON tl_sprd_manage USING GIN (rn_nrm gin_trgm_ops);
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

`addr-kr refresh mv` → `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`. 다음 PR 단위 또는 야간 cron으로 `addr-kr refresh vacuum`(`VACUUM (ANALYZE)`)와 (선택) `CLUSTER tl_spbd_buld USING idx_buld_road_match`를 실행한다. `maintenance_work_mem`은 트랜잭션 단위로만 상승(`SET LOCAL`).

## 디버거에서 운영까지 동일 환경

`/v1/admin/explain`은 `AsyncAddressClient.engine`을 그대로 사용해 `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`를 실행한다. 디버거에서 본 plan은 운영 쿼리와 같은 search_path, statement_timeout, pool 옵션에서 평가된다 — 디버거가 잘 도는데 운영에서 다르게 동작할 가능성이 차단된다.

## 참고

- 백엔드 사양: `docs/backend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
- 결정: `docs/decisions.md` (ADR-001 ~ ADR-006, ADR-013)
