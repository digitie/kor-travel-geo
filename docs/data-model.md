# DATA MODEL — PostgreSQL + PostGIS 스키마

본 문서는 `kraddr-geo`이 사용하는 PostgreSQL + PostGIS 테이블 구조의 reference다. DDL 자체는 `sql/ddl/` 하위 파일과 `alembic/versions/`에 둔다.

> **적재 정본 정책 (ADR-012)**: 본 사양은 행안부 텍스트 정본 3종(도로명주소 한글_전체분, 위치정보요약DB_전체분, 내비게이션용DB_전체분)을 1차 데이터로 삼고, SHP 전자지도는 polygon·폴리라인 도형만 보조로 적재한다. ADR-005의 GDAL Python binding은 SHP 적재 경로에만 한정된다.

## 한눈에

| 구분 | 테이블/뷰 | 역할 | 출처 |
|------|-----------|------|------|
| 텍스트 1차 (4) | `tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc` | 행정/도로명/지번/우편번호 정본 매핑, 출입구 좌표, 내비 진입점/centroid | 행안부 텍스트 (월간) |
| SHP polygon/폴리라인 (9) | `tl_scco_ctprvn/sig/emd/li`, `tl_kodis_bas`, `tl_spbd_buld_polygon`, `tl_sprd_manage/intrvl/rw` | 행정구역·우편번호·건물 polygon, 도로 관리/구간/폴리라인 | 도로명주소 전자지도 SHP (월간) |
| 우편번호 보조 (2) | `postal_pobox`, `postal_bulk_delivery` | 사서함·다량배달처 | epost OpenAPI (분기, ADR-009) |
| 메타 (5) | `load_manifest`, `load_codes`, `load_jobs`, `load_consistency_reports`, `geo_cache` | 적재 watermark·MVM 매핑·작업 큐(ADR-011)·정합성 리포트(ADR-016)·외부 API 캐시 | |
| 평면화 (1) | `mv_geocode_target` | 지오코딩 쿼리용 MV (ADR-007) | 위 1·2를 join |

## 텍스트 1차 정본 (`loaders/text/`, ADR-012)

행안부가 정기 배포하는 텍스트 자료를 정본으로 적재한다. 모두 `|` 구분자 + CP949(또는 UTF-8 BOM) 인코딩, 헤더 없음. 적재는 stdlib `csv` + `psycopg.copy()`로 GDAL 의존 없이 수행한다(`docs/backend-package.md` §9).

### `tl_juso_text` — 도로명주소 한글_전체분

행안부 도로명주소 안내시스템의 **정본 매핑**. BD_MGT_SN을 키로 도로명/지번/행정/우편번호가 한 행에 모인다.

```sql
CREATE TABLE tl_juso_text (
  bd_mgt_sn         TEXT PRIMARY KEY,         -- 건물관리번호. 사양은 25자리이나 실제 2026-03 서울 파일은 26자리
  -- 행정
  sig_cd            TEXT NOT NULL,            -- 시군구 코드 5
  ctp_kor_nm        TEXT,                     -- 시도명
  sig_kor_nm        TEXT,                     -- 시군구명
  emd_kor_nm        TEXT,                     -- 읍면동명
  li_kor_nm         TEXT,                     -- 리명 (없을 수 있음)
  bjd_cd            TEXT NOT NULL,            -- 법정동 코드 10
  adm_cd            TEXT,                     -- 행정동 코드 10 (vworld level4AC)
  adm_kor_nm        TEXT,                     -- 행정동명 (vworld level4A)
  -- 도로명
  rn_cd             TEXT,                     -- 도로명 코드 7
  rncode_full       TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn                TEXT,                     -- 도로명
  rn_nrm            TEXT GENERATED ALWAYS AS (regexp_replace(rn, '\s+', '', 'g')) STORED,
  buld_se_cd        TEXT,                     -- 지하 여부 ('0' 지상 / '1' 지하)
  buld_mnnm         INT,                      -- 건물 본번
  buld_slno         INT,                      -- 건물 부번 (기본 0)
  buld_nm           TEXT,                     -- 시군구 건물명
  buld_nm_nrm       TEXT GENERATED ALWAYS AS (regexp_replace(buld_nm, '\s+', '', 'g')) STORED,
  -- 지번
  mntn_yn           CHAR(1),                  -- 산 여부 ('0' 대지 / '1' 산)
  lnbr_mnnm         INT,                      -- 지번 본번
  lnbr_slno         INT,                      -- 지번 부번
  -- 우편번호 정본
  zip_no            TEXT,                     -- 우편번호 5
  -- PNU (ADR-010, 외부 시스템 조인용).
  -- bjd_cd/mntn_yn/lnbr_mnnm 중 하나라도 NULL이면 NULL.
  -- COALESCE(lnbr_mnnm, 0)는 조용한 가짜 PNU를 만들기 때문에 금지.
  -- lnbr_slno만 NULL인 경우는 본번-only 지번으로 보고 0 보정.
  pnu               TEXT GENERATED ALWAYS AS (
    CASE
      WHEN bjd_cd IS NULL
        OR mntn_yn IS NULL
        OR mntn_yn NOT IN ('0', '1')
        OR lnbr_mnnm IS NULL
      THEN NULL
      ELSE bjd_cd
        || CASE WHEN mntn_yn = '1' THEN '2' ELSE '1' END
        || lpad(lnbr_mnnm::text, 4, '0')
        || lpad(COALESCE(lnbr_slno, 0)::text, 4, '0')
    END
  ) STORED,
  -- 적재 메타
  source_file       TEXT,                     -- 원본 파일명 (시도별)
  source_yyyymm     TEXT,                     -- 자료 기준월
  loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_juso_text_road  ON tl_juso_text (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_juso_text_jibun ON tl_juso_text (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX idx_juso_text_rn_trgm ON tl_juso_text USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX idx_juso_text_pnu   ON tl_juso_text (pnu) WHERE pnu IS NOT NULL;
```

텍스트 로더의 `source_file`은 `rnaddrkor_seoul.txt`, `entrc_seoul.txt`처럼 원본 파일명을 보관한다. PR #17부터 SHP 보조 로더도 같은 컬럼을 채운다. SHP의 경우 값은 `<시도>/<시군구코드>/<레이어>.shp` 형식이며, 예를 들어 `Seoul/11000/TL_SPBD_BULD.shp`처럼 적재된 시도와 레이어까지 추적할 수 있어야 한다. PR #17 이전에 적재된 실제 T-027 DB는 SHP `source_file`이 NULL이므로, C2/C4 원천 파일 역추적이 필요하면 SHP 보조 레이어를 재적재한다.

#### 파일 포맷 (도로명주소 한글_전체분)

행안부 배포 ZIP을 풀면 시도별 `.txt` 파일이 들어 있다(예: `rnaddrkor_seoul.txt`). 각 행은 `|`로 구분된 약 30개 컬럼.

| 컬럼 (예) | 의미 | DB 매핑 |
|-----------|------|---------|
| 도로명코드 (12자리, sig_cd + rn_cd) | 도로명 식별자 | `sig_cd` + `rn_cd` → `rncode_full` (생성 컬럼) |
| 시도명 | "서울특별시" 등 | `ctp_kor_nm` |
| 시군구명 | | `sig_kor_nm` |
| 읍면동명 | | `emd_kor_nm` |
| 도로명 | | `rn` |
| 지하여부 | '0'/'1' | `buld_se_cd` |
| 건물본번 | int | `buld_mnnm` |
| 건물부번 | int | `buld_slno` |
| 시군구 건물명 | | `buld_nm` |
| 행정동코드 | 10자리 | `adm_cd` |
| 행정동명 | | `adm_kor_nm` |
| 법정동코드 | 10자리 | `bjd_cd` |
| 지번 본번 | int | `lnbr_mnnm` |
| 지번 부번 | int | `lnbr_slno` |
| 산여부 | '0'/'1' | `mntn_yn` |
| 우편번호 | 5자리 | `zip_no` |
| 건물관리번호 | 25자리 또는 26자리 | `bd_mgt_sn` |

> **구현 기준 컬럼 순서(2026-03 실제 파일 검증)**: `rnaddrkor_*.txt`는 헤더 없는 `|` 구분 텍스트 파일이며, 현재 구현은 실제 `data/juso/202603_도로명주소 한글_전체분/rnaddrkor_seoul.txt`의 첫 행을 기준으로 `0=bd_mgt_sn`, `1=bjd_cd`, `2=시도`, `3=시군구`, `4=읍면동`, `5=리`, `6=mntn_yn`, `7=lnbr_mnnm`, `8=lnbr_slno`, `9=rncode_full`, `10=rn`, `11=buld_se_cd`, `12=buld_mnnm`, `13=buld_slno`, `14=adm_cd`, `15=adm_kor_nm`, `16=zip_no`, `22=buld_nm`을 사용한다. 파일 끝에는 빈 컬럼이 붙을 수 있으므로 로더는 필요한 인덱스만 명시적으로 읽는다. 인코딩은 BOM이 있으면 `utf-8-sig`, 그 외에는 `cp949` 검증을 먼저 시도하고 실패하면 `utf-8`을 시도한다. 서울 파일 524,678건은 `rncode_full` 결측이 0건이고 `bd_mgt_sn` 길이는 모두 26자리로 확인했다.

### `tl_locsum_entrc` — 위치정보요약DB

건물 출입구 좌표의 **정본**. 한 건물에 출입구가 여러 개일 수 있고 `ent_se_cd`로 대표/부속을 구분한다.

중요: 실제 `202604_위치정보요약DB_전체분.zip`의 `entrc_*.txt`는 `bd_mgt_sn`을 직접 제공하지 않는다. 원본은 `sig_cd`, `ent_man_no`, `bjd_cd`, `rncode_full`, 지상/지하, 건물 본·부번, 우편번호, 용도, 출입구 구분, 행정동명, X/Y 좌표를 제공한다. 따라서 테이블은 원본 natural key를 보존하고, 후처리(`loaders/postload.py`)에서 `tl_juso_text`와 `rncode_full + buld_se_cd + buld_mnnm + buld_slno + bjd_cd (+ zip_no)`로 조인해 `bd_mgt_sn`을 해소한다. 이 해소가 실패한 행은 reverse/geocode MV의 대표 출입구 후보에서 제외하되, 정합성 리포트에서 비율을 추적한다.

```sql
CREATE TABLE tl_locsum_entrc (
  sig_cd        TEXT NOT NULL,
  ent_man_no    BIGINT NOT NULL,          -- 출입구 관리번호(시군구 내 일련)
  bd_mgt_sn     TEXT,                     -- 후처리에서 해소. 원본에는 없음.
  bjd_cd        TEXT NOT NULL,
  ctp_kor_nm    TEXT,
  sig_kor_nm    TEXT,
  emd_kor_nm    TEXT,
  rn_cd         TEXT NOT NULL,
  rncode_full   TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn            TEXT,
  buld_se_cd    TEXT,
  buld_mnnm     INT,
  buld_slno     INT,
  zip_no        TEXT,
  buld_use      TEXT,
  ent_se_cd     CHAR(1),                  -- '0' 대표, '1'~ 부속
  adm_kor_nm    TEXT,
  geom          geometry(Point, 5179) NOT NULL,
  source_file   TEXT,
  source_yyyymm TEXT,
  loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, ent_man_no)
);
CREATE INDEX idx_locsum_geom    ON tl_locsum_entrc USING GIST (geom);
CREATE INDEX idx_locsum_bd      ON tl_locsum_entrc (bd_mgt_sn) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX idx_locsum_rep     ON tl_locsum_entrc (bd_mgt_sn, ent_se_cd, ent_man_no) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX idx_locsum_resolve ON tl_locsum_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no);
```

ADR-007의 "대표 출입구 1건" 규칙이 본 테이블의 `ent_se_cd`에 직접 의존한다.

좌표 X/Y가 비어 있는 행이 실제 파일에 존재한다. `geom`은 `NOT NULL`이므로 현재 로더는 좌표가 모두 있는 행만 적재한다. 좌표 결측 행 수는 원본 품질 지표이며, 필요하면 `load_consistency_reports`의 C3 세부 metric으로 남긴다.

### `tl_navi_buld_centroid` — 내비게이션용DB 건물 중심

출입구가 없거나 비대표인 건물의 fallback 좌표(ADR-012 후속).

```sql
CREATE TABLE tl_navi_buld_centroid (
  bd_mgt_sn      TEXT PRIMARY KEY,
  bjd_cd          TEXT,
  sig_cd          TEXT,
  rn_cd           TEXT,
  rncode_full     TEXT GENERATED ALWAYS AS (
    CASE WHEN sig_cd IS NULL OR rn_cd IS NULL THEN NULL ELSE sig_cd || rn_cd END
  ) STORED,
  centroid_5179  geometry(Point, 5179) NOT NULL,
  source_file    TEXT,
  source_yyyymm  TEXT,
  loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_navi_centroid_geom ON tl_navi_buld_centroid USING GIST (centroid_5179);
CREATE INDEX idx_navi_centroid_resolve
  ON tl_navi_buld_centroid (rncode_full, buld_se_cd, buld_mnnm, buld_slno, (left(bjd_cd, 8)));
```

2026년 실제 내비게이션용DB의 `bd_mgt_sn`은 25자리이고 도로명주소 한글 정본의 `bd_mgt_sn`은 26자리라 직접 조인하지 않는다. 또한 내비 `bjd_cd`는 리 코드가 `00`인 경우가 많으므로 centroid fallback은 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 기준으로 대표 centroid를 선택한다.

### `tl_navi_entrc` — 내비게이션용DB 진입점 (부속 출입구/차량 진입)

내비 진입점, 차량 진입점, 부속 출입구 등을 `kind`로 구분 보관. 본 사양에서는 reverse_geocode/매칭의 1차 경로에 사용하지 않고, 향후 `include=entrance_kind` 같은 옵션이 추가되면 활용.

```sql
CREATE TABLE tl_navi_entrc (
  sig_cd      TEXT NOT NULL,
  entry_no    BIGINT NOT NULL,
  bd_mgt_sn   TEXT,                       -- match_rs_entrc 원본에는 없음. 후처리 해소.
  bjd_cd      TEXT,
  rn_cd       TEXT NOT NULL,
  rncode_full TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  buld_se_cd  TEXT,
  buld_mnnm   INT,
  buld_slno   INT,
  kind        TEXT NOT NULL CHECK (kind IN ('navi','vehicle','parcel','aux')),
  geom        geometry(Point, 5179) NOT NULL,
  source_file TEXT,
  source_yyyymm TEXT,
  loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, entry_no)
);
CREATE INDEX idx_navi_entrc_geom ON tl_navi_entrc USING GIST (geom);
CREATE INDEX idx_navi_entrc_bd   ON tl_navi_entrc (bd_mgt_sn, kind) WHERE bd_mgt_sn IS NOT NULL;
CREATE INDEX idx_navi_entrc_resolve ON tl_navi_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd);
```

## SHP 보조 (polygon/폴리라인 전용, ADR-005)

도형이 필요한 테이블만 SHP 적재. 속성은 텍스트 정본을 신뢰하며 SHP 적재는 도형 + JOIN 키만 가져온다.

| 테이블 | PK | 도형 | 비고 |
|--------|----|------|------|
| `tl_scco_ctprvn` | `ctprvn_cd` | MULTIPOLYGON 5179 | 시도 polygon |
| `tl_scco_sig` | `sig_cd` | MULTIPOLYGON 5179 | 시군구 polygon |
| `tl_scco_emd` | `emd_cd` | MULTIPOLYGON 5179 | 읍면동 polygon |
| `tl_scco_li` | `li_cd` | MULTIPOLYGON 5179 | 리 polygon |
| `tl_kodis_bas` | `bas_mgt_sn` | MULTIPOLYGON 5179 | 우편번호(기초구역) polygon |
| `tl_spbd_buld_polygon` | `bd_mgt_sn` | MULTIPOLYGON 5179 | 건물 polygon. 원천 `BD_MGT_SN`은 실제 파일 기준 25자리라 정본 26자리 `bd_mgt_sn`과 직접 조인하지 않고, `rncode_full + 건물구분 + 본번/부번 + bjd_cd` natural key 검증용 속성을 함께 보관한다. `LI_CD=''`는 generated `bjd_cd`에서 `00`으로 보정해 정본 10자리 법정동 코드와 맞춘다. |
| `tl_sprd_manage` | `(sig_cd, rds_man_no)` | MULTILINESTRING 5179 | 도로 관리 LineString. C8 도로 인접성 검증은 이 geometry를 사용한다. |
| `tl_sprd_intrvl` | `(sig_cd, rds_man_no, bsi_int_sn)` | 속성 보조 | 도로 구간 |
| `tl_sprd_rw` | `(sig_cd, rw_sn)` | MULTIPOLYGON 5179 | 도로 폭/도로면 polygon. 2026년 실제 도로명주소 전자지도 `TL_SPRD_RW` SHP 헤더가 `Polygon`이므로 테이블도 `MULTIPOLYGON`으로 보관한다. C8 인접성 검증은 `rds_man_no`가 있는 `tl_sprd_manage.geom`을 기준으로 수행한다. |

GDAL 적재는 `gdal.VectorTranslate(...)`와 `gdal.config_options({"PG_USE_COPY": "YES", "SHAPE_ENCODING": "CP949"})` 조합을 사용한다(ADR-005). GDAL 3.8 Python binding은 `VectorTranslateOptions(openOptions=...)`를 받지 않으므로 CP949 지정은 config option으로 고정한다. 각 polygon 테이블에 GiST 인덱스를 둔다.

`tl_sprd_intrvl`은 T-034부터 예외적으로 GDAL을 거치지 않는다. 이 테이블은 geometry가 없는 도로 구간 속성 보조 테이블이고 실제 DBF의 필요한 필드가 모두 고정되어 있으므로, `TL_SPRD_INTRVL.dbf`를 직접 scan한 뒤 `COPY tl_sprd_intrvl (...) FROM STDIN`으로 적재한다. 이 경로는 기존 `source_file`/`source_yyyymm` 추적 컬럼을 유지하되, GDAL PostgreSQL driver의 append insert 병목을 피하기 위한 성능 전용 경로다.

## 정합성 검증 (텍스트 ↔ SHP, ADR-016)

텍스트 정본과 SHP polygon은 같은 BD_MGT_SN을 다른 경로로 적재하므로 **정기 정합성 검증**이 필수다. `kraddr-geo validate consistency` CLI 또는 라이브러리 `AsyncAddressClient.run_consistency_check()`(ADR-016)가 다음 케이스를 검사한다.

### 정합성 케이스 분류

| 케이스 | SQL 시그니처 | 의미 | 대응 |
|--------|--------------|------|------|
| **C1: 텍스트에만 존재** (BD_MGT_SN) | `juso \ buld_polygon` | 도로명주소 정본에는 있는데 SHP polygon이 없음 | 신축·미반영. `WARN` (확인 항목) |
| **C2: SHP에만 존재** | `buld_polygon \ juso` | polygon은 있는데 텍스트가 누락, 또는 SHP natural key 자체가 비어 비교 불가 | `ERROR` — metric의 `missing_text`/`missing_resolve_key`를 나눠 후속 분석 |
| **C3: 출입구 0개 건물 비율** | `juso \ locsum` | 위치정보요약DB에 출입구가 없는 건물 | `INFO` — `navi_centroid` fallback으로 흡수. 비율이 임계(예: 5%) 초과 시 `WARN` |
| **C4: 출입구 좌표 ↔ 건물 polygon 거리** | `ST_Distance(locsum.geom, buld_polygon.geom)` | 출입구가 건물 polygon 외부, 또는 멀리 떨어짐 | 5m 이내 `OK`, 50m 초과 `WARN`, 500m 초과 `ERROR`; `error_count`는 500m 초과 건수 |
| **C5: navi centroid ↔ 건물 polygon centroid 일치** | `ST_Distance(navi.centroid_5179, ST_Centroid(buld_polygon.geom))` | 두 centroid 거리 | 1m 이내 `OK`, 10m 초과 `WARN` |
| **C6: 우편번호 텍스트 ↔ kodis_bas polygon** | `ST_Covers(kodis_bas.geom, locsum.geom)` 와 `juso.zip_no = kodis_bas.bas_id` 비교 | 좌표가 우편번호 polygon 안 또는 경계 위인가 + 텍스트 zip_no와 일치하는가 | 일치 `OK`, polygon 외 `WARN`, zip_no 불일치 `ERROR` |
| **C7: 행정구역 ↔ 좌표 polygon 일치** | `ST_Covers(scco_emd.geom, locsum.geom)` 와 `juso.bjd_cd[1..8] = scco_emd.emd_cd` 비교 | 좌표가 법정동 polygon 안 또는 경계 위인가 | `OK` / `WARN`(polygon 외) / `ERROR`(코드 불일치) |
| **C8: 도로명 ↔ 도로 폴리라인 인접성** | `ST_DWithin(locsum.geom, tl_sprd_manage.geom, 100m)` filtered by `rncode_full` | 좌표가 같은 도로명 관리 LineString의 100m 이내인가 | 일치 `OK`, 외 `WARN` |
| **C9: PNU 자릿수 검증** | `length(pnu) = 19 AND substr(pnu, 11, 1) IN ('1','2')` | ADR-010 매핑이 올바른가 | `length != 19` 시 `ERROR` |
| **C10: 변동분 기준일 정합** | `load_manifest.source_yyyymm` 비교 | 텍스트 적재월과 SHP 적재월이 같은가 | 다르면 `WARN` (월 차이 1 이내 OK) |

각 케이스의 결과는 `load_consistency_reports` 테이블에 구조화된 JSON으로 저장된다.

T-031 후속 분석에서는 `kraddr-geo validate data-quality-samples`가 C2/C4/C6/C7에 대해 별도 CSV를 생성한다. 이 CSV는 운영 gate가 아니라 리뷰/지도 확인용 산출물이며, C2 reason별 sample, C4 거리 bucket과 좌표 차이, C6/C7 region summary를 포함한다. `artifacts/`는 git에 커밋하지 않고 PR 본문에는 핵심 표와 재현 명령만 옮긴다.

```sql
CREATE TABLE load_consistency_reports (
  report_id      TEXT PRIMARY KEY,         -- uuid 또는 'consistency_YYYYMMDD_HHMMSS'
  scope          TEXT NOT NULL,            -- 'full' / 'sido:seoul' / 'recent:7d'
  started_at     TIMESTAMPTZ NOT NULL,
  finished_at    TIMESTAMPTZ,
  source_set     JSONB NOT NULL,           -- {juso_yyyymm, locsum_yyyymm, navi_yyyymm, shp_yyyymm}
  cases          JSONB NOT NULL,           -- {C1: {count, severity, sample: [...]}, C2: ...}
  severity_max   TEXT NOT NULL CHECK (severity_max IN ('OK','INFO','WARN','ERROR')),
  generated_by   TEXT                      -- 'cli' / 'api' / 'cron'
);
CREATE INDEX idx_consistency_started ON load_consistency_reports (started_at DESC);
```

### `cases` JSONB 구조 예시

```json
{
  "C1_text_only": {
    "count": 1284,
    "severity": "WARN",
    "threshold": "5% 초과 시 WARN",
    "ratio": 0.0042,
    "sample": ["1168010100100000007370003241", "1117010100..."]
  },
  "C4_entrance_polygon_distance": {
    "count_total": 8401234,
    "p50_m": 1.2, "p95_m": 4.8, "p99_m": 24.1,
    "severity": "WARN",
    "outliers_over_50m": 312,
    "outliers_over_500m": 4,
    "sample_outliers": [{"bd_mgt_sn": "...", "dist_m": 612.3}]
  },
  "C9_pnu_format": {
    "count": 0, "severity": "OK"
  }
}
```

라이브러리·API에서의 노출은 `docs/backend-package.md` §9.8 (정합성 리포트) 참조.

### 생성 컬럼 (Generated Columns)

PostgreSQL의 `GENERATED ALWAYS AS (...) STORED`로 조인 키를 표준화한다. ORM은 read-only로 매핑한다(ADR-004).

- `tl_juso_text.rncode_full` = `sig_cd || rn_cd` (12)
- `tl_juso_text.rn_nrm`, `tl_juso_text.buld_nm_nrm` = 공백 제거
- `tl_juso_text.pnu` = bjd_cd + 토지구분(`mntn_yn 0→1, 1→2`) + 지번본번(4) + 지번부번(4) (19, ADR-010)

### 인덱스 (핵심)

```sql
-- 도로명 매칭 (geocode primary, 텍스트 정본)
CREATE INDEX idx_juso_text_road
  ON tl_juso_text (rncode_full, buld_mnnm, buld_slno, buld_se_cd);

-- 지번 매칭 (geocode secondary, 텍스트 정본)
CREATE INDEX idx_juso_text_jibun
  ON tl_juso_text (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);

-- 우편번호 polygon (reverse zipcode)
CREATE INDEX idx_kodis_bas_geom ON tl_kodis_bas USING GIST (geom);

-- 출입구 nearest (reverse geocode) — 위치정보요약DB 텍스트 정본 사용
CREATE INDEX idx_locsum_geom ON tl_locsum_entrc USING GIST (geom);
CREATE INDEX idx_locsum_bd   ON tl_locsum_entrc (bd_mgt_sn);
CREATE INDEX idx_locsum_rep  ON tl_locsum_entrc (bd_mgt_sn, ent_se_cd, ent_man_no);  -- 대표 출입구 선택용

-- centroid fallback (출입구 없는 건물)
CREATE INDEX idx_navi_centroid_geom ON tl_navi_buld_centroid USING GIST (centroid_5179);

-- 도로명 trigram fuzzy — 텍스트 정본의 도로명 인덱스
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_juso_text_rn_trgm
  ON tl_juso_text USING GIN (rn_nrm gin_trgm_ops);
```

`pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` (예: `SET LOCAL pg_trgm.similarity_threshold = 0.42`). 전역 변경 금지(SKILL.md §4-3).

## 평면화: `mv_geocode_target` (ADR-007, ADR-012)

지오코딩이 사용하는 단일 머티리얼라이즈드 뷰. **텍스트 정본**(`tl_juso_text`)에 **대표 출입구 좌표**(`tl_locsum_entrc`)와 **centroid fallback**(`tl_navi_buld_centroid`)을 합쳐 단일 lookup으로 응답한다. `pt_source` 컬럼이 응답 좌표의 출처를 노출한다.

```sql
CREATE MATERIALIZED VIEW mv_geocode_target AS
WITH best_entrc AS (
  -- ADR-007 대표 출입구 1건 선택 (ent_se_cd='0' 우선 → ent_man_no 오름차순)
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom AS ent_pt_5179
  FROM tl_locsum_entrc
  ORDER BY bd_mgt_sn,
           (CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END),
           ent_man_no
)
SELECT
  j.bd_mgt_sn,
  j.rncode_full,
  j.buld_mnnm,
  j.buld_slno,
  j.buld_se_cd,
  j.buld_nm,
  j.buld_nm_nrm,
  j.bjd_cd,
  j.adm_cd,                                            -- 행정동 코드 (vworld level4AC)
  j.adm_kor_nm,                                        -- 행정동명 (vworld level4A)
  j.mntn_yn,
  j.lnbr_mnnm,
  j.lnbr_slno,
  j.zip_no,
  j.rn        AS road_nm,
  j.sig_kor_nm AS sgg_nm,
  j.ctp_kor_nm AS si_nm,
  j.emd_kor_nm AS emd_nm,
  j.pnu,                                               -- ADR-010
  COALESCE(be.ent_pt_5179, nc.centroid_5179) AS pt_5179,
  ST_Transform(COALESCE(be.ent_pt_5179, nc.centroid_5179), 4326) AS pt_4326,
  CASE
    WHEN be.ent_pt_5179 IS NOT NULL THEN 'entrance'   -- 위치정보요약DB 대표 출입구
    WHEN nc.centroid_5179 IS NOT NULL THEN 'centroid' -- 내비게이션용DB 건물 중심
    ELSE NULL                                          -- 좌표 없음 (응답 시 status='NOT_FOUND' 또는 polygon centroid fallback)
  END AS pt_source
FROM tl_juso_text j
LEFT JOIN best_entrc be ON be.bd_mgt_sn = j.bd_mgt_sn
LEFT JOIN best_navi nc
  ON nc.rncode_full = j.rncode_full
 AND nc.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
 AND nc.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
 AND nc.buld_slno IS NOT DISTINCT FROM j.buld_slno
 AND nc.bjd_emd_cd = left(j.bjd_cd, 8)
WITH DATA;

CREATE UNIQUE INDEX idx_mv_geocode_target_pk ON mv_geocode_target (bd_mgt_sn);
CREATE INDEX idx_mv_road  ON mv_geocode_target (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX idx_mv_jibun ON mv_geocode_target (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX idx_mv_geom5179 ON mv_geocode_target USING GIST (pt_5179);  -- 거리/nearest 1차 경로
CREATE INDEX idx_mv_geom4326 ON mv_geocode_target USING GIST (pt_4326);  -- 응답 직렬화 보조
CREATE INDEX idx_mv_pt_source ON mv_geocode_target (pt_source);          -- entrance vs centroid 통계
```

응답에는 `x_extension.pt_source = "entrance"|"centroid"`로 좌표 출처를 노출(ADR-003 호환). 라우터는 `pt_source = 'centroid'` 결과에 신뢰도(`confidence`)를 낮춰 반환 — `entrance` 매칭보다 정밀도가 떨어지기 때문.

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
  WITH best_entrc AS (...) -- 본 MV 정의와 동일 (ADR-007 대표 출입구 + centroid fallback)
  SELECT ... FROM tl_juso_text j
       LEFT JOIN best_entrc be ON ...
       LEFT JOIN tl_navi_buld_centroid nc ON ...
  WITH DATA;
CREATE UNIQUE INDEX ON mv_geocode_target_next (bd_mgt_sn);
CREATE INDEX        ON mv_geocode_target_next (rncode_full, buld_mnnm, buld_slno, buld_se_cd);
CREATE INDEX        ON mv_geocode_target_next (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno);
CREATE INDEX        ON mv_geocode_target_next USING GIST (pt_5179);
CREATE INDEX        ON mv_geocode_target_next USING GIST (pt_4326);
CREATE INDEX        ON mv_geocode_target_next (pt_source);
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

매 행 변환을 피하기 위해 **입력 좌표를 CTE에서 한 번만 변환**하고, 술어는 인덱스가 있는 컬럼(`pt_5179` 또는 `pt_4326`)을 그대로 사용한다(SKILL.md §4-11).

**반경/nearest 쿼리는 5179 기준**으로 한다. PostGIS의 geometry 거리는 SRID 단위를 그대로 쓰므로, EPSG:4326에서 `:radius_m`을 넣으면 단위가 **도(degree)**가 되어 의도와 다르다. 5179는 GRS80 UTM-K로 단위가 meter라 `:radius_m`이 그대로 의미를 가진다.

```sql
-- 입력 좌표 (lon, lat, in_srid)를 5179로 한 번만 변환하고 GiST 인덱스 스캔
WITH target_pt AS (
  SELECT ST_Transform(
    ST_SetSRID(ST_MakePoint(:x, :y), :in_srid),
    5179
  ) AS geom
)
SELECT t.bd_mgt_sn, t.road_nm, t.buld_nm, t.pt_source,
       ST_X(t.pt_4326) AS lon, ST_Y(t.pt_4326) AS lat,   -- 응답은 4326
       ST_Distance(t.pt_5179, p.geom) AS dist_m
FROM mv_geocode_target t, target_pt p
WHERE ST_DWithin(t.pt_5179, p.geom, :radius_m)
ORDER BY t.pt_5179 <-> p.geom
LIMIT :limit;
```

- `pt_4326`은 응답에서 `(lon, lat)` 추출 전용. **거리 술어에 쓰면 안 된다**.
- `pt_source = 'centroid'` 결과는 `entrance` 결과보다 정밀도가 낮으므로 라우터가 `confidence`를 낮춰 반환(ADR-012 후속).
- 입력 SRID(`:in_srid`)는 사용자 입력 `crs`에서 4326/5179만 허용(`docs/backend-package.md` §4 — `CRS` Annotated 정규화). 추가 SRID가 들어오면 repo 레벨에서 `InvalidCoordinateError`로 거부(SKILL.md §4-5와 별개의 SRID 화이트리스트).

### 행정 polygon의 4326 변환

`tl_kodis_bas`, `tl_scco_*` 등 polygon 테이블은 5179만 보관한다. VWorld/MapLibre 지도와 vworld 호환 API 응답처럼 4326을 요구하는 경로용으로 변환 view를 둔다.

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

def pnu_from_row(row: dict) -> str | None:
    """bjd_cd(10) + land_type(1) + lnbr_mnnm(4) + lnbr_slno(4) = 19자리.

    bjd_cd, mntn_yn, lnbr_mnnm이 없으면 조용히 0000을 만들지 말고 NULL
    또는 검증 오류로 처리한다. lnbr_slno만 없으면 본번-only 지번으로 보고 0.
    """
    if not row["bjd_cd"] or row["mntn_yn"] not in {"0", "1"} or row["lnbr_mnnm"] is None:
        return None
    return (
        row["bjd_cd"]
        + land_type(row["mntn_yn"])
        + f"{int(row['lnbr_mnnm']):04d}"
        + f"{int(row.get('lnbr_slno') or 0):04d}"
    )
```

현재 구현은 `tl_juso_text`에 generated stored column으로 둔다:

```sql
ALTER TABLE tl_juso_text ADD COLUMN pnu TEXT GENERATED ALWAYS AS (
  CASE
    WHEN bjd_cd IS NULL
      OR mntn_yn IS NULL
      OR mntn_yn NOT IN ('0', '1')
      OR lnbr_mnnm IS NULL
    THEN NULL
    ELSE bjd_cd
      || CASE WHEN mntn_yn = '1' THEN '2' ELSE '1' END
      || lpad(lnbr_mnnm::text, 4, '0')
      || lpad(COALESCE(lnbr_slno, 0)::text, 4, '0')
  END
) STORED;
CREATE INDEX idx_juso_text_pnu ON tl_juso_text (pnu) WHERE pnu IS NOT NULL;
```

Python helper(`src/kraddr/geo/infra/pnu.py`)는 로더 단위 테스트와 외부 연동 보조용으로만 둔다. **`core/`에는 PNU 조립 로직을 두지 않는다** — 외부 식별자 표준은 저장/조회 계층의 책임.

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

### `load_jobs` (ADR-011)

적재 작업의 영속 상태. lifespan startup에서 잔존 `running → failed` 마크, `queued`는 payload가 DB에 남아 있으면 drain을 재개한다. 다중 워커 환경에서는 `pg_try_advisory_xact_lock` + `FOR UPDATE SKIP LOCKED`로 작업 픽업을 보호한다. 컬럼 정의는 `docs/backend-package.md` §9.7 참조.

PR #10 리뷰 반영으로 `load_batch_id`, `parent_job_id`를 추가했다(ADR-017). 전국 풀로드는 `full_load_batch` root job을 만들고 그 아래 `juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load` child를 묶는다. source child가 모두 성공해야 큐가 `consistency_check`를 자동 등록하고, 정합성 리포트가 `ERROR`가 아닐 때만 `mv_refresh`를 `strategy='swap'`으로 등록한다. 따라서 `load_jobs`는 단순 작업 이력 테이블이 아니라 적재 DAG의 현재 위치와 차단 사유를 설명하는 운영 감사 로그다.

### `load_consistency_reports` (ADR-016)

텍스트 ↔ SHP 정합성 검증 리포트. 상세 정의는 본 문서 "정합성 검증" 절. `severity_max`로 운영 대시보드에서 회귀 감지.

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

`mv_geocode_target`은 두 좌표계(`pt_5179`, `pt_4326`)를 미리 가지고 있어 응답 시 변환 비용을 줄인다.
