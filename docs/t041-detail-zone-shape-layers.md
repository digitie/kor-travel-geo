# T-041: 상세주소 동 도형과 구역 추가 레이어 검토

## 상태

- 상태: 구현/결정 완료
- 대상 브랜치: `codex/t041-extra-shape-layer-review`
- 대상 원천:
  - `data/juso/unused/건물군 내 상세주소 동 도형/건물군내동도형_전체분_세종특별자치시.zip`
  - `data/juso/unused/건물군 내 상세주소 동 도형/건물군내동도형_전체분_경상남도.zip`
  - `data/juso/unused/구역의 도형/구역의도형_전체분_세종특별자치시.zip`
  - `data/juso/unused/구역의 도형/구역의도형_전체분_경상남도.zip`
  - 비교 기준: `data/juso/도로명주소 전자지도/{세종특별자치시,경상남도}`
- 관련 ADR: ADR-023, ADR-026

## 결론

T-041에서도 기본 `full_load_batch`와 `mv_geocode_target`에는 새 레이어를 섞지 않는다.

`건물군 내 상세주소 동 도형`은 상세주소 동 polygon과 동 출입구 point를 제공한다. 하지만 세종/경남 실제 파일 기준으로 polygon의 `BD_MGT_SN + EQB_MAN_SN` key는 기존 전자지도 `TL_SPBD_BULD`의 부분집합이었다. 즉, 주소 대표 좌표를 보강하는 새 원천이라기보다 상세주소 동/건물군 내부 표시를 위한 분석 원천에 가깝다.

`구역의 도형`은 기존 전자지도와 이름이 같은 5개 레이어(`TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`)가 세종/경남에서 key 기준 완전히 일치했다. 새 가치가 있는 레이어는 `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA` 두 개뿐이다.

T-041 최초 결론에서는 두 레이어 모두 overlay/분석 후보로 보류했다. 하지만 `TL_SPPN_MAKAREA`는 단순 화면 overlay가 아니라 **국가지점번호 표기 의무지역 polygon**이다. 주소가 없는 산악·해안·하천·도서 등 비거주지역에서 geocode/reverse geocode를 보조할 수 있는 데이터이므로, T-042에서 `tl_sppn_makarea` 별도 테이블로 적재하도록 구현했다. 단, 이 레이어는 개별 국가지점번호판 point 목록이 아니라 "지점번호를 표기해야 하는 구역"의 면 데이터다. 따라서 현행 `mv_geocode_target`의 도로명/지번 주소 1행 계약에 섞지 않고, 국가지점번호 전용 보조 후보와 `x_extension` 확장으로 노출한다.

이번 PR의 산출물은 다음으로 제한한다.

- 공용 DBF/SHP 분석 helper: `src/kortravelgeo/loaders/shape_dbf.py`
- T-041 비교 helper: `src/kortravelgeo/loaders/extra_shape_layers.py`
- 재현 스크립트: `scripts/compare_extra_shape_layers.py`
- 실제 세종 빠른 테스트와 경남 선택형 slow 테스트
- ADR-026과 본 문서의 후속 loader 설계 원칙

## 실제 레이어 구조

### 건물군 내 상세주소 동 도형

| 지역 | layer | geometry | rows | 주요 필드 |
|------|-------|----------|-----:|-----------|
| 세종 | `TL_SGCO_RNADR_DONG` | Polygon | 40,478 | `ADR_MNG_NO`, `BD_MGT_SN`, `SIG_CD`, `BUL_MAN_NO`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `EQB_MAN_SN` |
| 세종 | `TL_SPBD_ENTRC_DONG` | Point | 4,098 | `SIG_CD`, `ENT_MAN_NO`, `BUL_MAN_NO`, `ENTRC_SE`, `OPERT_DE`, `ENTRC_DC` |
| 경남 | `TL_SGCO_RNADR_DONG` | Polygon | 923,702 | 위와 동일 |
| 경남 | `TL_SPBD_ENTRC_DONG` | Point | 35,649 | 위와 동일 |

상세주소 동 polygon 비교 key:

```text
BD_MGT_SN, EQB_MAN_SN
```

동 출입구가 어느 상세주소 동 polygon의 건물을 참조하는지 보는 key:

```text
SIG_CD, BUL_MAN_NO
```

### 구역의 도형

| 지역 | layer | geometry | rows | 현행 전자지도와 관계 |
|------|-------|----------|-----:|----------------------|
| 세종 | `TL_SCCO_CTPRVN` | Polygon | 1 | key 완전 중복 |
| 세종 | `TL_SCCO_SIG` | Polygon | 1 | key 완전 중복 |
| 세종 | `TL_SCCO_EMD` | Polygon | 33 | key 완전 중복 |
| 세종 | `TL_SCCO_LI` | Polygon | 117 | key 완전 중복 |
| 세종 | `TL_KODIS_BAS` | Polygon | 155 | key 완전 중복 |
| 세종 | `TL_SCCO_GEMD` | Polygon | 24 | 추가 레이어 |
| 세종 | `TL_SPPN_MAKAREA` | Polygon | 146 | 추가 레이어 |
| 경남 | `TL_SCCO_CTPRVN` | Polygon | 1 | key 완전 중복 |
| 경남 | `TL_SCCO_SIG` | Polygon | 22 | key 완전 중복 |
| 경남 | `TL_SCCO_EMD` | Polygon | 546 | key 완전 중복 |
| 경남 | `TL_SCCO_LI` | Polygon | 1,832 | key 완전 중복 |
| 경남 | `TL_KODIS_BAS` | Polygon | 2,338 | key 완전 중복 |
| 경남 | `TL_SCCO_GEMD` | Polygon | 305 | 추가 레이어 |
| 경남 | `TL_SPPN_MAKAREA` | Polygon | 3,486 | 추가 레이어 |

중복 판정 key:

| layer | key |
|-------|-----|
| `TL_SCCO_CTPRVN` | `CTPRVN_CD` |
| `TL_SCCO_SIG` | `SIG_CD` |
| `TL_SCCO_EMD` | `EMD_CD` |
| `TL_SCCO_LI` | `LI_CD` |
| `TL_KODIS_BAS` | `BAS_ID` |

추가 레이어 key:

| layer | key | 해석 |
|-------|-----|------|
| `TL_SCCO_GEMD` | `EMD_CD` | 전자지도 `TL_SCCO_EMD.EMD_CD`와 겹치지 않는 별도 고시 읍면동 계열 코드로 보인다. 세종/경남 모두 기존 `TL_SCCO_EMD`와 교집합 0건이었다. |
| `TL_SPPN_MAKAREA` | `SIG_CD`, `MAKAREA_ID` | 지점번호표기 의무지역 polygon이다. `MAKAREA_NM`은 사용자 표시명으로 보존하되 중복 가능성이 있으므로 key로 쓰지 않는다. |

## 비교 결과

### 상세주소 동 polygon ↔ 전자지도 건물 polygon

| 지역 | detail rows/distinct | 전자지도 rows/distinct | 교집합 | detail only | 전자지도 only |
|------|---------------------:|-----------------------:|-------:|------------:|--------------:|
| 세종 | 40,478 / 40,478 | 55,819 / 55,819 | 40,478 | 0 | 15,341 |
| 경남 | 923,702 / 923,702 | 1,269,029 / 1,269,029 | 923,702 | 0 | 345,327 |

해석:

- 두 지역 모두 상세주소 동 polygon은 전자지도 `TL_SPBD_BULD`의 `BD_MGT_SN + EQB_MAN_SN` 부분집합이다.
- 현행 serving 대표 좌표나 건물 polygon 정합성(C1/C2/C4/C5)을 이 레이어로 바꾸면 "전자지도 전체 건물"이 아니라 "상세주소 동 대상 건물"만 보게 된다.
- `ADR_MNG_NO`는 세종 12,453 distinct / 40,478 rows, 경남 310,945 distinct / 923,702 rows다. 같은 주소관리번호 아래 여러 상세 동 또는 상세 건물이 묶이는 구조로 해석해야 한다.

### 상세주소 동 출입구 ↔ 상세주소 동 polygon 참조

| 지역 | entrance rows/distinct `SIG_CD+BUL_MAN_NO` | polygon rows/distinct `SIG_CD+BUL_MAN_NO` | 교집합 | entrance only | polygon only |
|------|-------------------------------------------:|------------------------------------------:|-------:|--------------:|-------------:|
| 세종 | 4,098 / 2,182 | 40,478 / 40,478 | 2,182 | 0 | 38,296 |
| 경남 | 35,649 / 16,260 | 923,702 / 923,702 | 16,260 | 0 | 907,442 |

해석:

- 동 출입구는 모든 상세주소 동 polygon에 붙어 있지 않고 일부 건물군에만 제공된다.
- 같은 `SIG_CD+BUL_MAN_NO`에 출입구 point가 여러 개 있을 수 있다. 세종은 4,098행이 2,182개 building ref로 줄고, 경남은 35,649행이 16,260개 building ref로 줄어든다.
- 이 자료를 API 응답에 바로 펼치면 1주소 1대표 좌표 계약이 아니라 상세 동/출입구 다중 overlay 계약이 필요하다.

### 구역의 도형 duplicate layer ↔ 전자지도

| 지역 | layer | 교집합 | zone only | 전자지도 only |
|------|-------|-------:|----------:|--------------:|
| 세종 | `TL_SCCO_CTPRVN` | 1 | 0 | 0 |
| 세종 | `TL_SCCO_SIG` | 1 | 0 | 0 |
| 세종 | `TL_SCCO_EMD` | 33 | 0 | 0 |
| 세종 | `TL_SCCO_LI` | 117 | 0 | 0 |
| 세종 | `TL_KODIS_BAS` | 155 | 0 | 0 |
| 경남 | `TL_SCCO_CTPRVN` | 1 | 0 | 0 |
| 경남 | `TL_SCCO_SIG` | 22 | 0 | 0 |
| 경남 | `TL_SCCO_EMD` | 546 | 0 | 0 |
| 경남 | `TL_SCCO_LI` | 1,832 | 0 | 0 |
| 경남 | `TL_KODIS_BAS` | 2,338 | 0 | 0 |

해석:

- 현재 전자지도 로더가 이미 적재하는 행정구역/기초구역 5개 레이어는 `구역의 도형` ZIP에서 다시 적재할 이유가 없다.
- 기본 full-load에 넣으면 같은 데이터를 한 번 더 읽어 load time과 스키마 표면만 늘어난다.

### 구역 추가 레이어

| 지역 | `TL_SCCO_GEMD` rows/distinct | 기존 `TL_SCCO_EMD`와 교집합 | `TL_SPPN_MAKAREA` rows/distinct key |
|------|-----------------------------:|-----------------------------:|------------------------------------:|
| 세종 | 24 / 24 | 0 | 146 / 146 |
| 경남 | 305 / 305 | 0 | 3,486 / 3,486 |

해석:

- `TL_SCCO_GEMD`는 이름은 읍면동 계열이지만 기존 `TL_SCCO_EMD.EMD_CD`와 key가 겹치지 않는다. 같은 테이블에 넣으면 코드 의미가 섞일 위험이 있다.
- `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key다. `MAKAREA_NM`은 중복될 수 있으므로 사용자 표시명으로만 다룬다.

## `TL_SPPN_MAKAREA` 상세 해석

`TL_SPPN_MAKAREA`는 행정안전부 도로명주소 전자지도 계열의 "지점번호표기 의무지역" 레이어로 해석한다. 네이밍은 다음처럼 읽는다.

| 부분 | 의미 |
|------|------|
| `TL` | Table 또는 Layer |
| `SPPN` | Spot Point Position Number, 국가지점번호/지점번호 계열 |
| `MAKAREA` | Marking Area, 표기 의무 구역 |

즉 `TL_SPPN_MAKAREA`는 **국가지점번호를 표기해야 하는 지역의 경계 polygon**이다. 행정안전부 설명자료 기준으로 국가지점번호 제도는 산악·해안 등 건물이 없는 비거주지역에서 사고나 재난이 발생했을 때 정확한 위치 안내를 돕기 위한 제도다. 같은 설명자료는 표기 대상 지역을 도로명이 부여된 도로에서 100m 이상 떨어진 지역 중 시·도지사가 필요하다고 고시한 지역으로 설명하고, 표기 대상 시설물을 지면 또는 수면에서 50cm 이상 노출된 고정 시설물로 설명한다.

이 레이어의 중요한 한계는 다음과 같다.

- polygon은 "표기 의무지역"의 범위이지, 개별 국가지점번호판이나 시설물 point가 아니다.
- polygon만으로는 `라마 1234 5678` 같은 특정 국가지점번호 문자열을 직접 만들 수 없다. 국가지점번호 문자열의 격자 좌표 변환 규칙은 별도 parser/generator가 필요하다.
- `MAKAREA_NM`은 사람이 읽는 구역명으로 보존하되, 검색 key나 unique key가 될 수 없다.
- 현행 주소 geocode의 도로명/지번/건물 결과와 cardinality가 다르다. 이 데이터를 `mv_geocode_target`에 union하면 주소가 아닌 구역 polygon이 주소 결과처럼 보이는 문제가 생긴다.

따라서 후속 구현은 `TL_SPPN_MAKAREA`를 **주소 검색 결과의 대체재가 아니라 국가지점번호 보조 데이터**로 다룬다.

### geocode 활용

geocode에서 이 데이터를 활용하는 흐름은 두 단계로 나눈다.

1. 입력 문자열이 국가지점번호 형식인지 별도 parser가 먼저 판단한다.
2. parser가 좌표를 계산하면 그 좌표가 `tl_sppn_makarea.geom` 안에 있는지 확인해 `sppn_area` metadata를 붙인다.

즉 `TL_SPPN_MAKAREA`는 "문자열 → 좌표" 계산의 주체가 아니라, 계산된 좌표가 국가지점번호 표기 의무지역에 속하는지 검증하고 행정/구역 문맥을 붙이는 보조 layer다. 구역명(`MAKAREA_NM`)만으로 geocode를 수행하는 기능은 기본 주소 geocode와 다른 "구역 검색" 성격이므로, 도입한다면 `search` 또는 관리 UI overlay 검색으로 먼저 분리한다. 구역명으로 좌표를 반환해야 할 때는 centroid를 낮은 confidence로 반환하고, polygon/bbox를 함께 노출해야 한다.

### reverse geocode 활용

reverse geocode에서는 입력 좌표가 도로명/지번 주소 후보를 찾지 못하거나, 주소 후보 confidence가 낮은 비거주지역일 때 `tl_sppn_makarea`를 보조 후보로 조회한다.

권장 쿼리 형태:

```sql
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179) AS geom
)
SELECT
  m.sig_cd,
  m.makarea_id,
  m.makarea_nm,
  ST_Distance(ST_PointOnSurface(m.geom), p.geom) AS point_on_surface_distance_m
FROM tl_sppn_makarea m, target_pt p
WHERE ST_Covers(m.geom, p.geom)
ORDER BY ST_Area(m.geom) ASC
LIMIT 5;
```

좌표가 여러 polygon에 포함되면 더 작은 면적의 polygon을 우선한다. `ST_Contains` 대신 `ST_Covers`를 사용해 경계선 위의 좌표도 놓치지 않는다. T-042 구현 결과는 vworld 호환 주소 필드에 억지로 끼워 넣지 않고 `x_extension.sppn_makarea`로 표현한다.

### 제안 테이블

후속 구현에서 DDL은 다음 형태를 기준으로 한다. 실제 필드명은 로컬 SHP/DBF header를 다시 확인한 뒤 확정한다.

```sql
CREATE TABLE tl_sppn_makarea (
  sig_cd        TEXT NOT NULL,
  makarea_id    TEXT NOT NULL,
  makarea_nm    TEXT,
  geom          geometry(MultiPolygon, 5179) NOT NULL,
  source_file   TEXT NOT NULL,
  source_yyyymm TEXT,
  loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id)
);

CREATE INDEX idx_sppn_makarea_geom
  ON tl_sppn_makarea
  USING GIST (geom);

CREATE INDEX idx_sppn_makarea_sig
  ON tl_sppn_makarea (sig_cd);
```

선택 확장:

- `geom_4326` generated column 또는 view: 디버그 UI overlay 직렬화용.
- `point_on_surface_5179` generated column 또는 materialized view: 구역명 검색에서 낮은 confidence 대표점이 필요할 때 사용.
- `source_kind='sppn_makarea'`: `load_manifest`와 정합성 sample에서 원천 종류를 명확히 구분.

### 정합성/품질 검증

후속 loader는 최소 다음 검증을 포함해야 한다.

| 검증 | 목적 |
|------|------|
| `SIG_CD + MAKAREA_ID` 중복 0건 | primary key 안정성 |
| `geom IS NOT NULL` 전수 확인 | reverse geocode 가능성 |
| `ST_IsValid(geom)` 또는 `ST_MakeValid` 적용 여부 기록 | polygon 품질 |
| `ST_Area(geom) > 0` | 빈 geometry 방지 |
| `TL_SCCO_SIG`와 `SIG_CD` 참조율 | 시군구 코드 품질 |
| 기준월 `source_yyyymm` 기록 | C10/혼합 기준월 해석 |

### 후속 구현 범위

T-042에서 1~3번은 구현했다. 남은 UI overlay는 T-044의 `maplibre-vworld-js` 0.1.0 문서-only 재확인 결과를 바탕으로 별도 UI 구현 PR에서 처리한다.

1. 완료: `TL_SPPN_MAKAREA` loader와 `tl_sppn_makarea` DDL 추가.
2. 완료: reverse geocode에서 기존 도로명/지번 후보와 응답 계약이 섞이지 않도록 `x_extension.sppn_makarea`로 보조 문맥을 노출.
3. 완료: 국가지점번호 문자열 parser/formatter를 `core.sppn`에 추가하고, parser가 계산한 좌표의 polygon 포함 여부를 `tl_sppn_makarea`로 검증.
4. 대기: 디버그 UI 지도 overlay에서 `TL_SPPN_MAKAREA` polygon과 reverse 결과를 함께 표시.

## 후속 설계 원칙

후속 loader가 필요하면 전자지도 테이블에 섞지 않고 별도 테이블로 둔다.

| 후보 테이블 | 원천 layer | 용도 |
|-------------|------------|------|
| `tl_detail_dong_polygon` | `TL_SGCO_RNADR_DONG` | 상세주소 동/건물군 내부 polygon overlay, 상세주소 기능 |
| `tl_detail_dong_entrc` | `TL_SPBD_ENTRC_DONG` | 상세주소 동 출입구 overlay, 건물군 내부 진입점 검토 |
| `tl_scco_gemd` | `TL_SCCO_GEMD` | 고시 읍면동 또는 별도 구역 overlay |
| `tl_sppn_makarea` | `TL_SPPN_MAKAREA` | 국가지점번호 표기 의무지역 polygon. reverse geocode 보조 후보, 국가지점번호 geocode 검증/문맥 보강, 디버그 UI overlay |

기본 `full_load_batch`에 자동 포함하는 조건:

1. 이 레이어들을 조회하는 명확한 API 또는 관리 UI 화면이 먼저 정의되어야 한다.
2. `mv_geocode_target`의 1주소 1행 계약과 대표 좌표 계약을 바꾸지 않아야 한다.
3. 현재 전자지도 중복 레이어는 다시 적재하지 않고, 추가 가치가 있는 레이어만 적재해야 한다.
4. 기준월이 `202605` 계열이므로 기존 `202603~202604` full-load와 섞을 때 C10 경고 또는 별도 consistency note가 남아야 한다.
5. `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key가 겹치지 않으므로 같은 테이블에 union하지 않아야 한다.
6. `TL_SPPN_MAKAREA`는 국가지점번호 보조 데이터로 승격하되, 주소 MV에 union하지 않고 별도 table + reverse/geocode enrichment 경로로 연결해야 한다.

## 참고 근거

- 행정안전부 설명자료: `https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000009&nttId=66987`
- 로컬 실제 파일: `data/juso/unused/구역의 도형/*/TL_SPPN_MAKAREA.*`

## 재현 명령

세종 빠른 비교:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/compare_extra_shape_layers.py \
  --detail-dong-zip "/mnt/f/dev/geodata/juso/unused/건물군 내 상세주소 동 도형/건물군내동도형_전체분_세종특별자치시.zip" \
  --zone-zip "/mnt/f/dev/geodata/juso/unused/구역의 도형/구역의도형_전체분_세종특별자치시.zip" \
  --electronic-map-sido "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 전자지도/세종특별자치시"
```

경남 선택형 비교:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_SLOW_REAL_DATA=1 \
  .venv/bin/python -m pytest \
  tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q
```

## 검증

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_building_shape_bundle.py tests/unit/test_extra_shape_layers.py tests/integration/test_real_extra_shape_sources.py -q` → 11 passed, 2 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_SLOW_REAL_DATA=1 .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q` → 1 passed in 16.74s.
- `scripts/compare_extra_shape_layers.py`로 세종 실제 파일 JSON 출력을 확인했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 148 passed, 5 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo scripts/compare_extra_shape_layers.py scripts/compare_building_shape_bundle.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `git diff --check` → 통과.
