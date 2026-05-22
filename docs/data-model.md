# DATA MODEL — PostgreSQL + PostGIS 스키마

본 문서는 `addr-kr`이 사용하는 PostgreSQL + PostGIS 테이블 구조의 reference다. DDL 자체는 `sql/ddl/` 하위 파일과 `alembic/versions/`에 둔다.

## 한눈에

| 구분 | 테이블/뷰 | 역할 |
|------|-----------|------|
| 마스터 (11개) | `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`, `tl_scco_li`, `tl_kodis_bas`, `tl_sprd_manage`, `tl_sprd_intrvl`, `tl_sprd_rw`, `tl_spbd_eqb`, `tl_spbd_buld`, `tl_spbd_entrc` | 도로명주소 전자지도 원천 |
| 보조 | `postal_pobox`, `postal_bulk_delivery` | 사서함·다량배달처 (epost 다운로드) |
| 메타 | `load_manifest`, `load_codes`, `geo_cache` | 적재 상태·MVM 매핑·외부 API 캐시 |
| 평면화 | `mv_geocode_target` | 지오코딩 쿼리용 머티리얼라이즈드 뷰 |

## 11개 마스터 (도로명주소 전자지도)

| 테이블 | PK | 핵심 컬럼 (요약) | 비고 |
|--------|----|------------------|------|
| `tl_scco_ctprvn` | `ctprvn_cd` | `ctp_kor_nm`, `geom (MULTIPOLYGON, 5179)` | 시도 |
| `tl_scco_sig` | `sig_cd` | `sig_kor_nm`, `sig_nm_nrm`, `geom` | 시군구 |
| `tl_scco_emd` | `emd_cd` | `emd_kor_nm`, `sig_cd`, `geom` | 읍면동 |
| `tl_scco_li` | `li_cd` | `li_kor_nm`, `emd_cd_8`, `geom` | 리 |
| `tl_kodis_bas` | `bas_mgt_sn` | `bas_id (= 우편번호 5)`, `geom` | 기초구역(우편번호 폴리곤) |
| `tl_sprd_manage` | `(sig_cd, rds_man_no)` | `rn_cd`, `rn`, `rn_nrm`, `rncode_full` (생성칼럼) | 도로명 관리 |
| `tl_sprd_intrvl` | `(sig_cd, rds_man_no, bsi_int_sn)` | 도로 구간, 기점/종점 | |
| `tl_sprd_rw` | `(sig_cd, rw_sn)` | 도로 폴리라인 `geom (MULTILINESTRING)` | |
| `tl_spbd_eqb` | `(sig_cd, eqb_man_sn)` | 부속건물 매핑 | |
| `tl_spbd_buld` | `(sig_cd, bul_man_no)` | `bd_mgt_sn (25)`, `buld_mnnm/slno`, `bsi_zon_no (=우편번호)`, `geom (MULTIPOLYGON)`, 생성칼럼 `bjd_cd`, `rncode_full`, `buld_nm_nrm` | 건물 |
| `tl_spbd_entrc` | `(sig_cd, ent_man_no)` | 출입구 `geom (POINT)`, 도로/지번 키 | 지오코딩 1차 좌표 |

### 생성 컬럼 (Generated Columns)

PostgreSQL의 `GENERATED ALWAYS AS (...) STORED`로 조인 키를 표준화한다. ORM은 read-only로 매핑한다(ADR-004).

- `tl_spbd_buld.bjd_cd` = 시도2 + 시군구3 + 읍면동3 + 리2 (10)
- `tl_spbd_buld.rncode_full` = `sig_cd || rn_cd` (12)
- `tl_spbd_buld.buld_nm_nrm` = `regexp_replace(buld_nm, '\s+', '', 'g')`

### 인덱스 (핵심)

```sql
-- 도로명 매칭 (geocode primary)
CREATE INDEX idx_buld_road_match
  ON tl_spbd_buld (rncode_full, buld_mnnm, buld_slno, buld_se_cd);

-- 지번 매칭 (geocode secondary)
CREATE INDEX idx_buld_jibun_match
  ON tl_spbd_buld (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);

-- 우편번호 polygon (reverse zipcode)
CREATE INDEX idx_kodis_bas_geom ON tl_kodis_bas USING GIST (geom);

-- 출입구 nearest (reverse geocode)
CREATE INDEX idx_entrc_geom ON tl_spbd_entrc USING GIST (geom);
CREATE INDEX idx_entrc_main
  ON tl_spbd_entrc (rncode_full, buld_mnnm, buld_slno);

-- 도로명 trigram fuzzy
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_sprd_manage_rn_trgm
  ON tl_sprd_manage USING GIN (rn_nrm gin_trgm_ops);
```

`pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` (예: `SET LOCAL pg_trgm.similarity_threshold = 0.42`). 전역 변경 금지(SKILL.md §4-3, ADR-009 후속).

## 평면화: `mv_geocode_target`

지오코딩이 사용하는 단일 머티리얼라이즈드 뷰. 건물·출입구·도로·동을 평면화해 단일 인덱스 lookup으로 응답한다.

```sql
CREATE MATERIALIZED VIEW mv_geocode_target AS
SELECT
  b.bd_mgt_sn,
  b.rncode_full,
  b.buld_mnnm,
  b.buld_slno,
  b.buld_se_cd,
  b.buld_nm,
  b.buld_nm_nrm,
  b.bjd_cd,
  b.mntn_yn,
  b.lnbr_mnnm,
  b.lnbr_slno,
  b.bsi_zon_no    AS zip_no,
  r.rn           AS road_nm,
  s.sig_kor_nm   AS sgg_nm,
  c.ctp_kor_nm   AS si_nm,
  e.emd_kor_nm   AS emd_nm,
  ent.geom       AS ent_pt_5179,
  ST_Transform(ent.geom, 4326) AS ent_pt_4326
FROM tl_spbd_buld b
LEFT JOIN tl_sprd_manage r ON r.rncode_full = b.rncode_full
LEFT JOIN tl_scco_sig    s ON s.sig_cd      = b.sig_cd
LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd   = substr(b.bjd_cd, 1, 2)
LEFT JOIN tl_scco_emd    e ON e.emd_cd      = substr(b.bjd_cd, 1, 8)
LEFT JOIN tl_spbd_entrc ent ON ent.sig_cd = b.sig_cd AND ent.bul_man_no = b.bul_man_no
WITH DATA;

CREATE UNIQUE INDEX idx_mv_geocode_target_pk ON mv_geocode_target (bd_mgt_sn);
CREATE INDEX idx_mv_road  ON mv_geocode_target (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_mv_jibun ON mv_geocode_target (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX idx_mv_geom4326 ON mv_geocode_target USING GIST (ent_pt_4326);
```

적재 후 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`. ANALYZE는 자동 통계만 의존하지 말고 명시 실행한다.

## 보조 우편번호

### `postal_pobox` (사서함)

```sql
CREATE TABLE postal_pobox (
  bd_mgt_sn   TEXT PRIMARY KEY,
  zip_no      TEXT NOT NULL,
  rn_code     TEXT,
  pobox_kind  TEXT CHECK (pobox_kind IN ('PO','PG')),   -- PO: 사서함, PG: 우편집중
  pobox_name  TEXT,
  pobox_no_mn INT,
  pobox_no_sl INT DEFAULT 0,
  si_nm       TEXT,
  sgg_nm      TEXT,
  emd_nm      TEXT,
  bjd_cd      TEXT,
  loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `postal_bulk_delivery` (다량배달처)

```sql
CREATE TABLE postal_bulk_delivery (
  bulk_id        BIGSERIAL PRIMARY KEY,
  zip_no         TEXT NOT NULL,
  bd_mgt_sn      TEXT,
  bulk_name      TEXT NOT NULL,
  detail         TEXT,
  loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bulk_bd_mgt_sn ON postal_bulk_delivery (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;
```

`/v1/address/zipcode`의 lookup 우선순위는 본 두 테이블을 포함한다. 자세한 우선순위 표는 `docs/backend-package.md` §3.7과 ADR로 별도 관리.

## 메타 테이블

### `load_manifest`

매니페스트는 파일/DB 양쪽에 미러링된다. 자세한 pydantic 모델은 `docs/backend-package.md` §9.1.

```sql
CREATE TABLE load_manifest (
  table_name         TEXT PRIMARY KEY,
  last_full_load_at  TIMESTAMPTZ,
  last_delta_at      TIMESTAMPTZ,
  last_mvmn_de       TEXT,
  row_count          BIGINT NOT NULL DEFAULT 0,
  source_zip         TEXT,
  source_checksum    TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `load_codes` (MVM_RES_CD 매핑)

코드 매핑을 settings/DB에서 읽어 핫픽스를 쉽게 한다(SKILL.md §4-6, ADR-006 후속).

```sql
CREATE TABLE load_codes (
  code   TEXT PRIMARY KEY,        -- '31','33','34',...
  action TEXT NOT NULL CHECK (action IN ('insert','update','delete')),
  note   TEXT
);
-- 기본값
INSERT INTO load_codes(code, action) VALUES
  ('31','insert'), ('33','insert'),
  ('34','update'), ('35','update'), ('36','update'),
  ('63','delete'), ('64','delete')
ON CONFLICT DO NOTHING;
```

### `geo_cache`

외부 API 호출 결과 캐시. TTL은 `Settings.cache_ttl_days`로 관리.

```sql
CREATE TABLE geo_cache (
  cache_key    TEXT PRIMARY KEY,        -- sha256("vworld:getcoord:address=...")
  service      TEXT NOT NULL,
  payload      JSONB NOT NULL,
  hit_count    BIGINT NOT NULL DEFAULT 0,
  last_hit_at  TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_geo_cache_expires ON geo_cache (expires_at);
```

## MVM_RES_CD 정책

증분 적재의 신규/수정/삭제 분기 키. 코드 값은 데이터셋 README와 도로명주소 안내시스템 코드정의서로 검증한다. 시간 흐름에 따라 코드 추가 가능.

| MVM_RES_CD (예시) | 의미 | 처리 |
|--------------------|------|------|
| 31, 33 | 신규 (도로명 부여 등) | `INSERT ... ON CONFLICT DO NOTHING` (idempotent) |
| 34, 35, 36 | 수정 (속성/위치 변경) | UPSERT (`DO UPDATE`) |
| 63, 64 | 삭제 (말소, 통합 흡수) | `DELETE FROM master WHERE PK matches` |
| 기타 (변동 없는 행 포함) | 참고 | skip |

PK 매핑은 `docs/backend-package.md` §9.3의 `PK_MAP` 상수와 일치.

## 좌표계

- **저장**: EPSG:5179 (대한민국 GRS80 UTM-K)
- **응답**: 기본 EPSG:4326 (WGS84). `crs` 입력으로 다른 EPSG도 허용.
- **변환**: `ST_Transform(geom, target_srid)`. 응답에서 `(lon, lat)`는 `(ST_X, ST_Y)` 순서 (SKILL.md §4-5).

`mv_geocode_target`은 두 좌표계(`ent_pt_5179`, `ent_pt_4326`)를 미리 가지고 있어 응답 시 변환 비용을 줄인다.
