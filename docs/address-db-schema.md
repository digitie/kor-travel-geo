# 주소 DB 스키마 (요약)

`kraddr-geo`의 1차 저장소는 PostgreSQL + PostGIS다. 본 문서는 상위 요약만 두고, 컬럼·인덱스·MV·메타 테이블 전체 정의는 `docs/data-model.md`에 둔다.

> 이전(v1) SQLite + SpatiaLite 기반 스키마(`juso_address_points`, `juso_boundary_polygons`, `juso_spatial_metadata`)는 `v1` 브랜치에 보존되어 있다. master는 더 이상 그 스키마를 유지보수하지 않는다(ADR-001).

## 한눈에

| 구분 | 테이블/뷰 | 역할 |
|------|-----------|------|
| 마스터 (11개) | `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li`, `tl_kodis_bas`, `tl_sprd_manage`, `tl_sprd_intrvl`, `tl_sprd_rw`, `tl_spbd_eqb`, `tl_spbd_buld`, `tl_spbd_entrc` | 도로명주소 전자지도 원천 |
| 보조 | `postal_pobox`, `postal_bulk_delivery` | 사서함·다량배달처 (epost 다운로드) |
| 메타 | `load_manifest`, `load_codes`, `geo_cache` | 적재 상태, MVM_RES_CD 매핑, 외부 API 캐시 |
| 평면화 | `mv_geocode_target` | 지오코딩 쿼리용 MV (도로/지번 단일 lookup) |

## 좌표계

- 저장: EPSG:5179 (대한민국 GRS80 UTM-K)
- 응답: 기본 EPSG:4326. `crs` 입력으로 다른 EPSG 허용.
- 응답에서 `(lon, lat)`는 `(ST_X, ST_Y)` 순서. 외부 인터페이스는 모두 `(lon, lat)` 고정 (SKILL.md §4-5).

## 핵심 식별자

| 약어 | 의미 |
|------|------|
| BJD_CD | 법정동코드 10자리 (시도2 + 시군구3 + 읍면동3 + 리2) |
| RNCODE_FULL | 도로명코드 12자리 (SIG_CD 5 + RN_CD 7) |
| BD_MGT_SN | 건물관리번호 25자리, 전국 unique |
| BSI_ZON_NO | 건물의 기초구역번호 = 우편번호 5자리 |
| BAS_ID | `TL_KODIS_BAS`의 기초구역번호 = 우편번호 |
| MVM_RES_CD | 이동사유코드 (신규/수정/삭제 분기 키) |
| MVMN_DE | 이동일자 YYYYMMDD |

`tl_spbd_buld`에는 `bjd_cd`, `rncode_full`, `buld_nm_nrm` 같은 조인 키가 PostgreSQL의 `GENERATED ALWAYS AS (...) STORED` 컬럼으로 미리 계산되어 있다.

## 인덱스 (핵심)

- 도로명 매칭: `tl_spbd_buld(rncode_full, buld_mnnm, buld_slno, buld_se_cd)`
- 지번 매칭: `tl_spbd_buld(bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)`
- 우편번호 polygon: `tl_kodis_bas USING GIST(geom)`
- 출입구 nearest: `tl_spbd_entrc USING GIST(geom)`
- 도로명 trigram fuzzy: `tl_sprd_manage USING GIN(rn_nrm gin_trgm_ops)` (`pg_trgm`)

`pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` (SKILL.md §4-3).

## `mv_geocode_target`

건물·출입구·도로·동을 평면화한 머티리얼라이즈드 뷰. 지오코딩 라우터는 본 MV 단일 lookup으로 응답한다. 적재 후 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target` + `ANALYZE`.

전체 DDL과 추가 인덱스는 `docs/data-model.md`를 본다.

## Alembic

`alembic/versions/`에서 DDL을 관리한다. 마스터/보조/메타/MV 모두 IDempotent 마이그레이션 — 운영 중 재실행도 안전하도록 `IF NOT EXISTS` 또는 `DROP ... IF EXISTS` 명시.
