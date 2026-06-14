# T-116 주소DB/건물DB row·key drift 검증

`주소DB_전체분`과 `건물DB_전체분`은 현재 serving 정본을 대체하지 않는다. C16은 두 원천을 검증 전용 staging으로 읽어 `tl_juso_text`, `tl_juso_parcel_link`, `tl_spbd_buld_polygon`과 row/key drift를 측정하는 prototype이다. 좌표 적재와 serving 후보 승격은 하지 않는다.

## 원천

실데이터 파일:

- `data/juso/202605_주소DB_전체분.zip`
- `data/juso/202605_건물DB_전체분.zip`

`주소DB_전체분.zip`의 member 이름은 CP949 원문이 ZIP filename flag 없이 들어 있어 Python `zipfile`에서 mojibake로 보일 수 있다. C16 loader는 member 이름을 `cp437` bytes로 되돌린 뒤 `cp949`로 복원해 `주소_*.txt`, `부가정보_*.txt`, `지번_*.txt`, `개선_도로명코드_전체분.txt`를 찾는다.

`건물DB_전체분.zip`은 `build_*.txt`, `jibun_*.txt`, `road_code_total.txt` member를 사용한다.

## 비교 범위

| 비교 | source | serving table | key |
|------|--------|---------------|-----|
| 주소 row | `주소_*.txt` | `tl_juso_text` | `bd_mgt_sn` |
| 주소 부가정보 | `부가정보_*.txt` | `tl_juso_text` | `bd_mgt_sn` |
| 주소 지번 | `지번_*.txt` | `tl_juso_parcel_link` | `bd_mgt_sn + pnu` |
| 건물 row | `build_*.txt` | `tl_spbd_buld_polygon` | `rncode_full + buld_se_cd + buld_mnnm + buld_slno + bjd_cd` |
| 건물 row | `build_*.txt` | `tl_juso_text` | `rncode_full + buld_se_cd + buld_mnnm + buld_slno + bjd_cd` |
| 건물 지번 | `jibun_*.txt` | `tl_juso_parcel_link` | `pnu + rncode_full + buld_se_cd + buld_mnnm + buld_slno` |

각 비교는 distinct key 기준으로 intersection, left-only, right-only를 계산하고, `EXCEPT` 기반 sample을 남긴다. staging row 수는 별도 metric으로 남겨 원천 행 수 drift와 key drift를 구분한다.

## 구현

새 모듈은 `src/kortravelgeo/loaders/c16_address_building_drift.py`이다.

- ZIP text member를 streaming으로 읽는다.
- PNU는 기존 `infra.pnu.build_pnu()`로 계산한다.
- 전용 staging table(`_ktg_c16_*`)에 필요한 key만 COPY한다.
- `measure_key_overlap()`과 C16 전용 `key_drift_sample_sql()`로 drift metric/sample을 만든다.
- `C16AddressBuildingDriftComparison.metrics()`는 `coordinate_load=False`, `serving_promotion=False`를 고정한다.

## 해석 주의

`build_*.txt`는 건물 단위가 1천만 행 이상이고, `tl_juso_text`는 도로명주소 정본 6백만 행 수준이다. 두 원천의 행 수가 다르다는 사실만으로 오류로 판정하지 않는다. C16의 목적은 기준월 차이, natural key 누락, 중복, 원천별 범위 차이를 후속 C1/C2/C10 분석에 연결하는 것이다.

## 금지선

- `주소DB`를 `tl_juso_text` 대체 정본으로 바로 적재하지 않는다.
- `건물DB` 속성으로 `tl_spbd_buld_polygon` 또는 `mv_geocode_target` 좌표를 변경하지 않는다.
- `road_code_total`/`개선_도로명코드`는 이번 prototype에서 row 존재 확인까지만 하고 serving 도로명 코드 정본으로 승격하지 않는다.
