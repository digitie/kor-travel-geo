# ADR-027: `TL_SPPN_MAKAREA`는 국가지점번호 보조 지오코딩 데이터로 별도 적재한다

- 상태: accepted (문서 설계, 구현 전)
- 날짜: 2026-05-26
- 결정자: codex, 사용자 T-041 보강 지시

## 컨텍스트

ADR-026은 `구역의 도형` ZIP에서 추가 가치가 있는 레이어로 `TL_SCCO_GEMD`와 `TL_SPPN_MAKAREA`를 식별했지만, 둘 다 기본 serving path에는 넣지 않고 overlay/분석 후보로 보류했다. 이후 `TL_SPPN_MAKAREA`의 의미를 다시 확인했다.

`TL_SPPN_MAKAREA`는 "지점번호표기 의무지역" polygon으로 해석한다.

| 이름 부분 | 의미 |
|-----------|------|
| `TL` | Table 또는 Layer |
| `SPPN` | Spot Point Position Number, 국가지점번호/지점번호 계열 |
| `MAKAREA` | Marking Area, 표기 의무 구역 |

행정안전부 설명자료는 국가지점번호 제도를 산악·해안 등 건물이 없는 비거주지역에서 사고·재난 발생 시 정확한 위치 안내를 돕기 위한 제도로 설명한다. 같은 설명자료는 표기 대상 지역을 도로명이 부여된 도로에서 100m 이상 떨어진 지역 중 시·도지사가 필요하다고 고시한 지역으로 설명하고, 표기 대상 시설물을 지면 또는 수면에서 50cm 이상 노출된 고정 시설물로 설명한다.

따라서 `TL_SPPN_MAKAREA`는 주소가 없거나 주소 후보 confidence가 낮은 비거주지역에서 geocode/reverse geocode를 보조할 수 있다. 다만 이 레이어는 개별 국가지점번호판이나 시설물 point 목록이 아니라 의무지역의 경계 polygon이다.

## 결정

`TL_SPPN_MAKAREA`를 별도 테이블 `tl_sppn_makarea`로 적재한다. T-042에서 DDL, loader, 국가지점번호 parser/formatter, geocode/reverse 보조 조회, source set optional child를 1차 구현했다.

1. `mv_geocode_target`에는 union하지 않는다. 이 MV는 도로명/지번 주소 1행 계약을 유지한다.
2. reverse geocode는 입력 좌표가 `tl_sppn_makarea.geom`에 포함될 때 국가지점번호 표기 의무지역 metadata를 보조 후보로 반환할 수 있다.
3. geocode는 국가지점번호 문자열 parser가 좌표를 계산한 뒤, 그 좌표가 `tl_sppn_makarea` 안에 있는지 검증하고 `MAKAREA_NM` 등 구역 문맥을 붙인다. EPSG:5179 좌표에서 국가지점번호 문자열을 만드는 formatter는 실제 polygon 내부 점 기반 테스트와 UI 표시를 지원한다.
4. `MAKAREA_NM`만으로 정확한 geocode 좌표를 만들지는 않는다. 구역명 검색은 polygon centroid/bbox를 낮은 confidence로 반환하는 별도 `search` 또는 관리 UI overlay 기능으로 분리한다.
5. 응답 확장은 vworld 호환 필드를 오염시키지 않고 `x_extension.sppn_makarea`로 둔다. reverse geocode 결과의 도로명/지번 후보는 기존 `result`에 유지하고, 표기 의무지역 polygon 문맥은 보조 확장 배열에 담는다.
6. 후속 loader는 `SIG_CD + MAKAREA_ID`를 primary key로 사용하고, `source_file`, `source_yyyymm`, `loaded_at`을 남긴다.

## 제안 테이블

```sql
CREATE TABLE tl_sppn_makarea (
  sig_cd        TEXT NOT NULL,
  makarea_id    TEXT NOT NULL,
  ntfc_yn       TEXT,
  makarea_nm    TEXT,
  ntfc_de       TEXT,
  mvm_res_cd    TEXT,
  mvmn_resn     TEXT,
  opert_de      TEXT,
  makarea_ar    NUMERIC(12,3),
  mvmn_desc     TEXT,
  geom          geometry(MultiPolygon, 5179) NOT NULL,
  source_file   TEXT NOT NULL,
  source_yyyymm TEXT,
  loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id)
);

CREATE INDEX idx_sppn_makarea_geom
  ON tl_sppn_makarea
  USING GIST (geom);
```

원천 SHP는 T-041 세종/경남 측정 기준 `Polygon`으로 제공된다. 운영 테이블은 다른 polygon 계열과 같은 방식으로 `MultiPolygon`으로 통일하고, loader에서 `ST_Multi()` 또는 GDAL `PROMOTE_TO_MULTI`로 변환한다.

## 쿼리 원칙

reverse geocode는 입력 좌표를 한 번만 EPSG:5179로 변환하고, polygon 컬럼에는 함수를 씌우지 않는다.

```sql
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179) AS geom
)
SELECT m.sig_cd, m.makarea_id, m.makarea_nm
FROM tl_sppn_makarea m, target_pt p
WHERE ST_Covers(m.geom, p.geom)
ORDER BY ST_Area(m.geom) ASC
LIMIT 5;
```

`ST_Contains` 대신 `ST_Covers`를 사용해 경계 위 좌표도 포함한다. 여러 구역이 겹치면 작은 면적을 우선하고, 필요하면 행정구역 코드(`SIG_CD`)와 거리/면적 metric을 함께 반환한다.

## 결과

- T-041 문서와 데이터 모델 문서에서 `TL_SPPN_MAKAREA`를 단순 overlay 후보가 아니라 국가지점번호 보조 geocode/reverse 데이터 후보로 승격한다.
- T-042에서 `tl_sppn_makarea` DDL/Alembic, loader, CLI/API job kind, source set optional child, `SppnMakareaContext`, 국가지점번호 parser/formatter, geocode/reverse `x_extension.sppn_makarea`를 구현했다.
- Docker PostGIS `kor_travel_geo_t042_sppn`에서 세종 `구역의 도형` 실제 ZIP을 적재해 146행/146 distinct key/전체 valid MultiPolygon을 확인했다.
- `금이산` polygon 내부 점을 EPSG:5179 formatter로 `다바 7363 4856`으로 만든 뒤 geocode와 reverse 보조 조회가 같은 polygon 문맥을 반환하는 것을 확인했다.
- T-027 최종 클린 로드는 `sppn_makarea` optional source를 포함할 수 있다. 다만 원천 기준월이 다른 경우 ADR-029/T-045의 혼합 기준월 확인 UX를 그대로 따른다.

## 남은 위험

- `TL_SPPN_MAKAREA`는 개별 국가지점번호판 point 목록이 아니므로, polygon 포함 여부는 "해당 좌표가 표기 의무지역 안에 있다"는 문맥만 제공한다. 실제 시설물 point 원천을 확보하면 별도 source와 confidence 정책을 둔다.
- reverse geocode는 도로명/지번 후보 유무와 관계없이 `sppn_makarea` 보조 조회를 수행한다. 응답 크기와 latency가 문제되면 T-047에서 후보 confidence 또는 radius 정책으로 제한한다.
- 국가지점번호 parser/formatter는 공개 설명의 100km 한글 격자와 10m cell 규칙을 구현했다. 도로명주소 전자지도 PDF 사양서에 더 엄격한 표기 변형이 있으면 T-047/T-044 전에 parser 허용 범위를 재검토한다.
- 디버그 UI polygon overlay는 아직 구현하지 않았다. T-044의 0.1.0 문서-only 재확인 결과를 바탕으로 별도 UI 구현 PR에서 `PolygonArea` 또는 동등한 지도 primitive로 추가한다.

## 참고

- 행정안전부 설명자료: `https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000009&nttId=66987`
