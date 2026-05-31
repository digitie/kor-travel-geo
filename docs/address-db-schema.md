# 주소 DB 스키마 (요약)

`kraddr-geo`의 1차 저장소는 PostgreSQL + PostGIS다. 본 문서는 상위 요약만 두고, 컬럼·인덱스·MV·메타 테이블 전체 정의는 `docs/data-model.md`에 둔다.

> 이전(v1) SQLite + SpatiaLite 기반 스키마(`juso_address_points`, `juso_boundary_polygons`, `juso_spatial_metadata`)는 `v1` 브랜치에 보존되어 있다. `main`은 더 이상 그 스키마를 유지보수하지 않는다(ADR-001).

> **적재 정본 정책 (ADR-007, ADR-012)**: 본 스키마는 행안부 **텍스트 정본**(도로명주소 한글_전체분, 위치정보요약DB, 내비게이션용DB, 도로명주소 출입구 정보)을 1차 데이터로 삼고, SHP 전자지도는 polygon·폴리라인 **도형만** 보조로 적재한다. 과거 `tl_spbd_buld`/`tl_spbd_entrc`/`tl_spbd_eqb` 같은 SHP "마스터" 속성 테이블은 더 이상 존재하지 않는다.

## 한눈에

| 구분 | 테이블/뷰 | 역할 |
|------|-----------|------|
| 텍스트 정본 (1차) | `tl_juso_text` | 도로명/지번/행정/우편번호 정본 매핑 (BD_MGT_SN 키) |
| 좌표 원천 | `tl_locsum_entrc`(1순위), `tl_roadaddr_entrc`(same-month fallback), `tl_navi_buld_centroid`·`tl_navi_entrc` | 출입구 좌표 / direct 출입구 / 건물 중심 centroid·진입점 |
| SHP 보조 (도형 전용) | `tl_spbd_buld_polygon`, `tl_kodis_bas`, `tl_scco_ctprvn/sig/emd/li`, `tl_sprd_manage/intrvl/rw` | 건물·우편번호·행정구역 polygon, 도로 LineString |
| 보조 매핑 | `tl_sppn_makarea`, `tl_juso_parcel_link` | 국가지점번호 polygon, 건물↔지번 1:N 링크 |
| 우편번호 보조 | `postal_pobox`, `postal_bulk_delivery` | 사서함·다량배달처 (epost) |
| 메타/운영 | `load_manifest`, `load_codes`, `load_jobs`, `load_consistency_reports`, `geo_cache`, `ops.*` | 적재 watermark, MVM 매핑, 작업 큐, 정합성 리포트, 외부 API 캐시, 운영 감사/스냅샷/릴리스/artifact |
| 평면화 (serving) | `mv_geocode_target`, `mv_geocode_text_search` | 지오코딩 serving MV + fuzzy 검색 helper MV |

## 좌표계

- 저장: EPSG:5179 (대한민국 GRS80 UTM-K). 반경/nearest 술어는 5179 기준(meter 단위).
- 응답: 기본 EPSG:4326. `crs` 입력으로 4326/5179만 허용.
- 응답에서 `(lon, lat)`는 `(ST_X, ST_Y)` 순서. 외부 인터페이스는 모두 `(lon, lat)` 고정 (SKILL.md §4-5).

## 핵심 식별자

| 약어 | 의미 |
|------|------|
| BJD_CD | 법정동코드 10자리 (시도2 + 시군구3 + 읍면동3 + 리2) |
| RNCODE_FULL | 도로명코드 12자리 (SIG_CD 5 + RN_CD 7), 생성 컬럼 |
| BD_MGT_SN | 건물관리번호. 도로명주소 한글 텍스트 정본(2026-03 실제 파일)은 **26자리**. 내비게이션용DB·SHP polygon 원천은 **25자리**라 정본과 직접 조인하지 않고 natural key로 매칭한다. |
| ZIP_NO / BAS_ID | 우편번호 5자리 (`tl_juso_text.zip_no` = `tl_kodis_bas.bas_id`) |
| PNU | 19자리 표준 토지 식별자 (ADR-010). `tl_juso_text.pnu` 생성 컬럼 |
| MVM_RES_CD | 이동사유코드 (신규/수정/삭제 분기 키, 변동분 적재) |

`tl_juso_text`에는 `rncode_full`, `rn_nrm`, `buld_nm_nrm`, `pnu` 같은 조인/정규화 키가 PostgreSQL의 `GENERATED ALWAYS AS (...) STORED` 컬럼으로 미리 계산되어 있다(ORM은 read-only 매핑, ADR-004).

## 인덱스 (핵심)

텍스트 정본과 serving MV에 주요 lookup 인덱스를 둔다.

- 도로명 매칭: `tl_juso_text(rncode_full, buld_mnnm, buld_slno, buld_se_cd)`, `mv_geocode_target` 동일 컬럼
- 지번 매칭: `tl_juso_text(bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)`, `mv_geocode_target` 동일 컬럼
- 우편번호 polygon: `tl_kodis_bas USING GIST(geom)`
- 출입구 nearest (좌표 정본): `tl_locsum_entrc USING GIST(geom)`, same-month `tl_roadaddr_entrc USING GIST(geom)`
- serving nearest/radius: `mv_geocode_target USING GIST(pt_5179)`
- 도로명 trigram fuzzy: `tl_juso_text`/`mv_geocode_target USING GIN(rn_nrm gin_trgm_ops)` (`pg_trgm`)

`pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` (SKILL.md §4-3).

## `mv_geocode_target`

지오코딩 serving용 단일 머티리얼라이즈드 뷰. **텍스트 정본**(`tl_juso_text`)에 **대표 출입구 좌표**(`tl_locsum_entrc`, 같은 기준월일 때만 `tl_roadaddr_entrc` direct 출입구 fallback)와 **centroid fallback**(`tl_navi_buld_centroid`)을 합쳐 단일 lookup으로 응답한다. `pt_source` 컬럼(`entrance`/`centroid`)이 응답 좌표의 출처를 노출한다(ADR-003/ADR-012 호환). 라우터는 `centroid` 결과에 `confidence`를 낮춰 반환한다.

`mv_geocode_text_search`는 `mv_geocode_target`에서 재생성하는 read-only fuzzy 검색 helper MV(T-061)다. MV 갱신은 두 객체를 함께 다루는 orchestration 경로(`kraddr-geo refresh mv`)만 사용한다.

전체 DDL과 추가 인덱스, swap 갱신 전략은 `docs/data-model.md`를 본다.

## Alembic / DDL

테이블·인덱스·MV 정의는 `src/kraddr/geo/infra/sql.py`(`SCHEMA_SQL`/`INDEX_SQL`/`MV_SQL`)와 `alembic/versions/`에서 관리한다. `kraddr-geo init-db`가 스키마·확장·인덱스·빈 MV를 생성한다. 보조/메타/MV 모두 idempotent — 운영 중 재실행도 안전하도록 `IF NOT EXISTS` 또는 `DROP ... IF EXISTS` 명시.
