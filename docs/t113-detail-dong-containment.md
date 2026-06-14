# T-113 C13 상세주소 동 containment 검증 prototype

## 목적

`detail_dong_shape_bundle`의 상세주소 동 polygon(`TL_SGCO_RNADR_DONG`)과 상세주소 동 출입구 point(`TL_SPBD_ENTRC_DONG`)를 PostGIS staging에 올리고, `상세주소DB_전체분`의 `adrdc_*.txt`와 key overlap을 측정한다. 이 작업은 상세주소 기능 후보 검증용이며 일반 도로명주소 대표 좌표, serving SQL, API 응답은 변경하지 않는다.

## 입력 계약

상세주소 동 도형 ZIP은 기존 `extra_shape_layers.py`의 레이어명을 그대로 쓴다.

| 원천 | 레이어/파일 | 역할 |
|------|-------------|------|
| `detail_dong_shape_bundle` | `TL_SGCO_RNADR_DONG` | 상세주소 동 polygon. `ADR_MNG_NO`, `BD_MGT_SN`, `SIG_CD`, `BUL_MAN_NO`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `EQB_MAN_SN`을 staging에 보존한다. |
| `detail_dong_shape_bundle` | `TL_SPBD_ENTRC_DONG` | 상세주소 동 출입구 point. `SIG_CD`, `ENT_MAN_NO`, `BUL_MAN_NO`, `ENTRC_SE`, `OPERT_DE`, `ENTRC_DC`를 staging에 보존한다. |
| `detail_address_db_full` | `adrdc_*.txt` | 상세주소 TXT. 시도별 member를 `adrdc_sejong.txt` 같은 영문명으로 매핑한다. |

`상세주소DB 활용가이드` 기준 전체분 TXT는 header 없는 MS949 pipe 파일이며 16컬럼이다.

| 순번 | 컬럼 | C13 내부 이름 |
|------|------|---------------|
| 1 | 시군구코드 | `sig_cd` |
| 2 | 동일련번호 | `dong_serial_no` |
| 3 | 층일련번호 | `floor_serial_no` |
| 4 | 호일련번호 | `unit_serial_no` |
| 5 | 호접미사일련번호 | `unit_suffix_serial_no` |
| 6 | 동명칭 | `dong_name` |
| 7 | 층명칭 | `floor_name` |
| 8 | 호명칭 | `unit_name` |
| 9 | 호접미사명칭 | `unit_suffix_name` |
| 10 | 지하구분 | `underground_flag` |
| 11 | 건물관리번호 | `building_management_no` |
| 12 | 법정동코드 | `legal_dong_cd` |
| 13 | 도로명코드 | `road_name_cd`, `road_name_no` |
| 14 | 지하여부 | `road_underground_yn` |
| 15 | 건물본번 | `building_main_no` |
| 16 | 건물부번 | `building_sub_no` |

TXT 자체에는 좌표가 없다. 따라서 C13의 `ST_Covers` containment는 상세주소 동 polygon이 같은 `SIG_CD + BUL_MAN_NO`를 가진 상세주소 동 출입구 point를 덮는지 측정한다. 상세주소DB는 containment 대상 geometry가 아니라, polygon 집합이 상세주소 행과 얼마나 연결되는지 판단하는 key context로 사용한다.

## 구현

추가 모듈:

- `src/kortravelgeo/loaders/c13_detail_dong.py`

주요 공개 helper:

- `iter_detail_address_rows()`: `adrdc_*.txt`를 MS949로 읽고 16컬럼 계약을 검증한다.
- `discover_c13_detail_dong_source_groups()`: 시도별 상세주소 동 도형 ZIP과 전국 상세주소DB ZIP member 존재를 묶어 `SidoSourceGroup`으로 반환한다.
- `compare_c13_detail_dong_containment()`: PostGIS staging 적재 후 key overlap과 containment metric을 산출한다.
- `build_c13_detail_dong_report()`: 시도별 결과를 `AugmentReport`로 묶는다.
- `drop_c13_detail_dong_staging_tables()`: optional smoke와 실험 실행 후 staging table을 정리한다.

staging table:

| table | 내용 |
|-------|------|
| `_ktg_c13_detail_dong_polygon` | `TL_SGCO_RNADR_DONG` polygon |
| `_ktg_c13_detail_dong_entrc` | `TL_SPBD_ENTRC_DONG` point |
| `_ktg_c13_detail_address` | `adrdc_*.txt` parser 결과 |

## 측정 항목

### key overlap

| metric | left | right | 해석 |
|--------|------|-------|------|
| `building_management_no_to_bd_mgt_sn` | polygon `BD_MGT_SN` | TXT `building_management_no` | 상세주소 행이 도형의 건물관리번호와 얼마나 겹치는지 본다. |
| `road_address_key_to_shape_fields` | polygon `SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO` | TXT `sig_cd`, `road_name_no`, `road_underground_yn`, `building_main_no`, `building_sub_no` | 건물관리번호와 별개로 도로명주소 연계키가 도형 필드와 겹치는지 본다. |
| `detail_entrance_sig_bul_to_polygon_sig_bul` | entrance `SIG_CD`, `BUL_MAN_NO` | polygon `SIG_CD`, `BUL_MAN_NO` | 상세주소 동 출입구가 polygon building ref를 참조하는지 본다. |

### containment

| metric | SQL 의미 |
|--------|----------|
| `detail_entrance_point_in_detail_dong_polygon` | `ST_Covers(polygon.geom, entrance.geom)`를 `SIG_CD + BUL_MAN_NO` join으로 측정한다. |
| `detail_address_matched_detail_entrance_point_in_polygon` | 위 containment에 `TXT building_management_no = polygon BD_MGT_SN` 존재 여부를 붙여, 상세주소DB와 연결된 pair의 coverage를 따로 집계한다. |

두 containment 모두 `serving_promotion=False`다. 결과는 상세주소 기능 후보와 C13 consistency case seed로만 사용한다.

## 검증

단위 테스트:

- `tests/unit/test_c13_detail_dong.py`
  - 상세주소DB parser 16컬럼/encoding/key normalization
  - staging spec과 join key 계약
  - 시도별 member discovery
  - `ST_Covers` SQL 계약
  - metrics payload와 `serving_promotion=False`

선택형 실제 데이터 smoke:

- `tests/integration/test_optional_real_postgres_c13_detail_dong.py`
  - `KTG_SLOW_REAL_DATA=1`
  - `KTG_TEST_PG_DSN`
  - 실제 세종 상세주소 동 도형 ZIP과 상세주소DB ZIP이 있을 때만 실행

이번 구현은 측정 경로만 추가하므로 OpenAPI, DTO, serving table, UI type 생성물은 변경하지 않는다.
