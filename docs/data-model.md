# DATA MODEL — PostgreSQL + PostGIS 스키마

본 문서는 `kraddr-geo`이 사용하는 PostgreSQL + PostGIS 테이블 구조의 reference다. DDL 자체는 `sql/ddl/` 하위 파일과 `alembic/versions/`에 둔다.

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
CREATE INDEX idx_mv_geom5179 ON mv_geocode_target USING GIST (ent_pt_5179);  -- 거리/nearest 1차 경로
CREATE INDEX idx_mv_geom4326 ON mv_geocode_target USING GIST (ent_pt_4326);  -- 응답 직렬화 보조
```

### MV 갱신 모드 (라이브 경합 시간 축소)

`REFRESH MATERIALIZED VIEW CONCURRENTLY`는 무중단 조회를 보장하지만 전국 풀로드 직후엔 정렬·임시 파일·재계산 비용으로 조회 응답이 느려진다. I/O 총량이 줄어드는 건 아니고 **운영 조회와의 경합 시간이 길어진다**.

본 사양은 두 모드를 둔다.

| 상황 | 방법 |
|------|------|
| 평시 변동분 적재(`delta_loader` 후) | `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target;` → `ANALYZE` |
| 분기 풀로드(전국 11개 마스터 재적재 후) | shadow MV 빌드 → 짧은 트랜잭션에서 RENAME swap (아래) |

```sql
-- shadow 빌드 (오프피크에 진행, 운영 조회는 mv_geocode_target에서 계속)
SET lock_timeout = '5s';
CREATE MATERIALIZED VIEW mv_geocode_target_next AS
  SELECT ... -- 기존 정의와 동일
  WITH DATA;
CREATE UNIQUE INDEX ON mv_geocode_target_next (bd_mgt_sn);
CREATE INDEX        ON mv_geocode_target_next (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX        ON mv_geocode_target_next (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX        ON mv_geocode_target_next USING GIST (ent_pt_5179);
CREATE INDEX        ON mv_geocode_target_next USING GIST (ent_pt_4326);
ANALYZE mv_geocode_target_next;

-- 원자 swap (수 ms)
BEGIN;
  SET LOCAL lock_timeout = '2s';
  DROP MATERIALIZED VIEW mv_geocode_target;
  ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target;
COMMIT;
```

주의:
- **인덱스 이름**은 swap 시 새 MV에 함께 RENAME되지 않는다. 명시 이름(`idx_mv_geocode_target_pk` 등)을 유지하려면 swap 후 `ALTER INDEX ... RENAME`이 추가로 필요하다.
- **권한·의존 객체**: `GRANT SELECT ON mv_geocode_target TO addr_kr_ro` 같은 운영 권한과 다른 MV의 의존성이 있으면 swap 전에 동일하게 새 MV에 반영.
- **prepared statement invalidation**: 라우터가 캐시한 prepared statement는 `DROP`/`RENAME` 시 다음 호출에서 `cached plan must not change result type`으로 실패할 수 있다. swap 직후 일부 요청이 한 번 재컴파일되는 비용 또는 `DISCARD PLANS`를 운영 워커 한 곳에서 트리거.
- **`lock_timeout`**: swap 트랜잭션이 운영 조회의 ACCESS SHARE를 못 기다리면 안전하게 abort. 위에 `2s` 정도.

swap 트리거는 `loaders/postload.py`의 `do_full_swap=True` 옵션 또는 `kraddr-geo refresh mv --swap` CLI(T-018). `loaders/swap.py`의 스키마 단위 `atomic_schema_swap`은 별개로 staging 전용이며 본 MV swap과 혼동하지 않는다.

## 공간 쿼리 가이드

매 행 변환을 피하기 위해 **입력 좌표를 CTE에서 한 번만 변환**하고, 술어는 인덱스가 있는 컬럼(`ent_pt_5179` 또는 `ent_pt_4326`)을 그대로 사용한다(SKILL.md §4-11).

**반경/nearest 쿼리는 5179 기준**으로 한다. PostGIS의 geometry 거리는 SRID 단위를 그대로 쓰므로, EPSG:4326에서 `:radius_m`을 넣으면 단위가 **도(degree)**가 되어 의도와 다르다. 5179는 GRS80 UTM-K로 단위가 meter라 `:radius_m`이 그대로 의미를 가진다.

```sql
-- 입력 좌표 (lon, lat, in_srid)를 5179로 한 번만 변환하고 GiST 인덱스 스캔
WITH target_pt AS (
  SELECT ST_Transform(
    ST_SetSRID(ST_MakePoint(:x, :y), :in_srid),
    5179
  ) AS geom
)
SELECT t.bd_mgt_sn, t.road_nm, t.buld_nm,
       ST_X(t.ent_pt_4326) AS lon, ST_Y(t.ent_pt_4326) AS lat,   -- 응답은 4326
       ST_Distance(t.ent_pt_5179, p.geom) AS dist_m
FROM mv_geocode_target t, target_pt p
WHERE ST_DWithin(t.ent_pt_5179, p.geom, :radius_m)
ORDER BY t.ent_pt_5179 <-> p.geom
LIMIT :limit;
```

- `ent_pt_4326`은 응답에서 `(lon, lat)` 추출 전용. **거리 술어에 쓰면 안 된다**.
- 입력 SRID(`:in_srid`)는 사용자 입력 `crs`에서 4326/5179만 허용(`docs/backend-package.md` §4 — `CRS` Annotated 정규화). 추가 SRID가 들어오면 repo 레벨에서 `InvalidCoordinateError`로 거부(SKILL.md §4-5와 별개의 SRID 화이트리스트).

### 행정 polygon의 4326 변환

`tl_kodis_bas`, `tl_scco_*` 등 polygon 테이블은 5179만 보관한다. Kakao Maps 등 4326을 요구하는 응답 경로용으로 변환 view를 둔다.

```sql
CREATE VIEW v_kodis_bas_4326 AS
  SELECT bas_mgt_sn, bas_id, ST_Transform(geom, 4326) AS geom_4326
  FROM tl_kodis_bas;
CREATE VIEW v_scco_emd_4326 AS
  SELECT emd_cd, emd_kor_nm, ST_Transform(geom, 4326) AS geom_4326
  FROM tl_scco_emd;
-- 필요 시 다른 행정 layer도 같은 패턴
```

폴리곤은 자주 변환되지 않는 응답 경로에만 등장하므로 view로 충분. 점이 빈도 높게 변환되는 `mv_geocode_target`만 컬럼으로 저장(ADR-007 후속).

적재 후 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`(평시) 또는 위 swap 절차(분기). ANALYZE는 자동 통계만 의존하지 말고 명시 실행한다.

## PNU 조립 (외부 시스템 연동)

법원 등기·토지대장 등 외부 시스템과 조인하려면 **19자리 표준 PNU**가 필요하다. PNU 11번째 자리(토지구분)는 `1=일반, 2=산`인데 도로명주소 원천의 `mntn_yn`은 `0=대지, 1=산`이라 직접 결합하면 안 된다. 조립은 infra/저장 계층 책임이며 `core/`는 의미론적 `mntn_yn`만 보관한다(ADR-010).

```python
# src/kraddr/geo/infra/_pnu.py (T-016 또는 보조 helper)
def land_type(mntn_yn: str) -> str:
    """mntn_yn ('0'/'1') → PNU 토지구분 ('1'/'2')."""
    return "2" if mntn_yn == "1" else "1"

def pnu_from_row(row: dict) -> str:
    """bjd_cd(10) + land_type(1) + lnbr_mnnm(4) + lnbr_slno(4) = 19자리."""
    return (
        row["bjd_cd"]
        + land_type(row["mntn_yn"])
        + f"{int(row['lnbr_mnnm']):04d}"
        + f"{int(row['lnbr_slno']):04d}"
    )
```

또는 `tl_spbd_buld`에 generated stored column으로 추가도 가능:

```sql
ALTER TABLE tl_spbd_buld ADD COLUMN pnu TEXT GENERATED ALWAYS AS (
  bjd_cd
  || CASE WHEN mntn_yn = '1' THEN '2' ELSE '1' END
  || lpad(lnbr_mnnm::text, 4, '0')
  || lpad(lnbr_slno::text, 4, '0')
) STORED;
CREATE INDEX idx_buld_pnu ON tl_spbd_buld (pnu) WHERE pnu IS NOT NULL;
```

위치는 ADR-010 후속에서 helper vs generated column 결정. 어느 쪽이든 **`core/`에는 PNU 조립 로직을 두지 않는다** — 외부 식별자 표준은 저장/조회 계층의 책임.

## 보조 우편번호

두 테이블 모두 epost OpenAPI **데이터셋 `15000302`**에서 받은 ZIP을 분기 1회 전량 적재한다(`TRUNCATE` → `INSERT`). 변경분(`downloadKnd=2`) 누적은 운영하지 않는다 — 자세한 결정 근거는 ADR-009, 적재 흐름은 `docs/external-apis.md` "epost" 절 참조.

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

### 한 배치당 PK 단일화 가정

`apply_delta`는 한 staging 배치 안에서 (a) UPSERT 일괄 → (b) DELETE 일괄 순서로 수행한다. 같은 PK에 대해 `INSERT`(31)와 `DELETE`(63)가 한 배치에 같이 들어오면 UPSERT 후 DELETE가 실행되어 신규 행이 즉시 지워지는 out-of-order 위험이 있다.

본 사양은 **한 staging 배치 내에서 같은 PK가 최대 1회만 등장한다**고 가정한다(도로명주소 변동분 SHP의 통상 구조). 이 가정이 데이터셋 갱신으로 깨질 경우, `apply_delta`는 staging에서 `MVMN_DE` 기준 마지막 이벤트만 남기는 단일화 단계를 추가한다.

```sql
-- staging 단일화 (가정이 깨졌을 때 활성화)
WITH dedup AS (
  SELECT DISTINCT ON (PK_COLS) *
  FROM staging_schema.tl_xxx
  ORDER BY PK_COLS, mvmn_de DESC
)
DELETE FROM staging_schema.tl_xxx;
INSERT INTO staging_schema.tl_xxx SELECT * FROM dedup;
```

`apply_delta`는 staging 적재 직후 dedup 여부를 한 행 SQL로 점검(`SELECT count(*) - count(DISTINCT (pk))`)하고 0이 아니면 dedup CTE를 자동 트리거 — 운영상 가정 검증 + fail-safe.

## 좌표계

- **저장**: EPSG:5179 (대한민국 GRS80 UTM-K)
- **응답**: 기본 EPSG:4326 (WGS84). `crs` 입력으로 다른 EPSG도 허용.
- **변환**: `ST_Transform(geom, target_srid)`. 응답에서 `(lon, lat)`는 `(ST_X, ST_Y)` 순서 (SKILL.md §4-5).

`mv_geocode_target`은 두 좌표계(`ent_pt_5179`, `ent_pt_4326`)를 미리 가지고 있어 응답 시 변환 비용을 줄인다.
