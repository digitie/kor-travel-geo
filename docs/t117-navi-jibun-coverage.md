# T-117 C17 내비 지번 member coverage 검증

`match_jibun_*.txt`는 `navi_full` archive 안의 optional 검증 member다. 독립 source category로 만들지 않고, 내비게이션용DB의 지번 link 후보가 현재 정본 보조 테이블 `tl_juso_parcel_link`와 얼마나 겹치는지 측정한다.

## 범위

- 입력: materialized `navi_full` 디렉터리 또는 ZIP 안의 `match_jibun_*.txt`.
- 비교 대상: `tl_juso_parcel_link`.
- 산출: distinct key overlap, left/right-only sample.
- 제외: 좌표 적재, serving ranking 편입, `mv_geocode_target` 변경.

현재 운영 원천은 `.7z`일 수 있다. T-109 설계처럼 7z는 register/materialization 단계에서 풀어 로더에 디렉터리로 전달하는 계약을 유지한다. C17 모듈은 `.7z`를 직접 subprocess로 풀지 않는다.

## 컬럼 계약

실제 `match_jibun_*.txt`는 CP949 pipe text이며 C17은 다음 field만 사용한다.

| field index | 의미 | 사용처 |
|-------------|------|--------|
| 0 | `bjd_cd` | PNU 조립 |
| 5 | `mntn_yn` | PNU 조립 |
| 6 | `lnbr_mnnm` | PNU 조립 |
| 7 | `lnbr_slno` | PNU 조립 |
| 8 | `rncode_full` | `sig_cd`, `rn_cd`, road key |
| 9 | `buld_se_cd` | road key |
| 10 | `buld_mnnm` | road key |
| 11 | `buld_slno` | road key |
| 18 | `bd_mgt_sn` | `bd_mgt_sn + pnu` 비교 |
| 19 | `adm_cd` | context |

PNU는 기존 `infra.pnu.build_pnu()`를 사용해 `bjd_cd + mntn_yn + lnbr_mnnm + lnbr_slno`에서 만든다.

## Metric

새 모듈은 `src/kortravelgeo/loaders/c17_navi_jibun_coverage.py`다.

- `discover_navi_jibun_members()`: `match_jibun_*.txt` member를 찾는다.
- `iter_navi_jibun_rows()`: parser와 PNU 조립을 streaming으로 수행한다.
- `compare_c17_navi_jibun_coverage()`: `_ktg_c17_navi_jibun` staging table에 COPY한 뒤 두 key 계약을 측정한다.
- `build_c17_navi_jibun_coverage_report()`: `AugmentReport(task_id="T-117")`를 만든다. member가 없으면 실패가 아니라 `skipped`로 기록한다.

비교는 두 가지다.

| 비교명 | key contract |
|--------|--------------|
| `navi_jibun_to_tl_juso_parcel_link_bd_pnu` | `bd_mgt_sn + pnu` |
| `navi_jibun_to_tl_juso_parcel_link_pnu_road_key` | `pnu + rncode_full + buld_se_cd + buld_mnnm + buld_slno` |

payload에는 `coordinate_load=False`, `serving_promotion=False`를 고정한다.

left/right-only sample SQL은 양쪽 key를 `text`로 맞춘 뒤 `EXCEPT`로 뽑는다. 현재 C17 계약에서는 PNU·도로명코드·건물관리번호는 text이고 건물 본번/부번은 양쪽 모두 정수 계약이라 leading zero 의미 차이가 없다. 후속 registry에서 text key와 numeric key를 섞는 새 비교를 추가하면 sample SQL만 보지 말고 `key_contract`에 canonicalization 규칙을 먼저 명시해야 한다.

## 검증

- `tests/unit/test_c17_navi_jibun_coverage.py`: synthetic CP949 text/ZIP, parser, SQL, metric, skip 계약.
- `tests/integration/test_optional_real_postgres_c17_navi_jibun_coverage.py`: `KTG_SLOW_REAL_DATA=1` + `KTG_TEST_PG_DSN` 선택형 실제 PostGIS smoke. `.7z`만 있으면 테스트가 WSL `7z`로 `match_jibun_sejong.txt` 한 member만 임시 materialize한다.
