# T-040: `도로명주소 건물 도형` bundle 비교

## 상태

- 상태: 구현/결정 완료
- 대상 브랜치: `codex/t040-building-shape-bundle`
- 대상 원천:
  - `data/juso/도로명주소 건물 도형/건물도형_전체분_세종특별자치시.zip`
  - `data/juso/도로명주소 건물 도형/건물도형_전체분_경상남도.zip`
  - 비교 기준: `data/juso/도로명주소 전자지도/{세종특별자치시,경상남도}/.../TL_SPBD_BULD.*`, `TL_SPBD_ENTRC.*`
- 관련 ADR: ADR-023, ADR-025

## 결론

`도로명주소 건물 도형`은 전자지도 `TL_SPBD_BULD`의 단순 중복이 아니다. `TL_SGCO_RNADR_MST`는 주소 단위 polygon, `TL_SPBD_ENTRC`는 출입구 point, `TL_SPOT_CNTC`는 출입구와 도로 관리/구간을 잇는 connection line으로 묶인 별도 bundle이다.

하지만 T-040에서는 serving loader를 바로 추가하지 않는다. 이유는 세 가지다.

1. 기준월이 `202605`라 현재 검증 기준월(`juso=202603`, `locsum/navi/shp=202604`)과 다르다.
2. T-039 `tl_roadaddr_entrc`가 이미 direct `bd_mgt_sn + 5179 point`를 제공하므로, 출입구 대표 좌표 보강은 텍스트 경로가 더 단순하고 안전하다.
3. 건물 polygon과 connection line은 C2/C4/C8 데이터 품질 분석에는 가치가 크지만, 현행 `mv_geocode_target`의 `bd_mgt_sn` 1행 계약에 바로 넣으면 주소 단위와 건물 단위 geometry 의미가 섞인다.

따라서 T-040의 산출물은 다음으로 제한한다.

- 순수 Python 비교 helper: `src/kortravelgeo/loaders/building_shape_bundle.py`
- 재현 스크립트: `scripts/compare_building_shape_bundle.py`
- 실제 세종 빠른 overlap 테스트와 경남 선택형 slow 테스트
- ADR-025와 본 문서의 후속 loader 설계 원칙

## 실제 레이어 구조

### 세종특별자치시

| 원천 | layer | geometry | rows | 주요 필드 |
|------|-------|----------|-----:|-----------|
| 도로명주소 건물 도형 | `TL_SGCO_RNADR_MST` | Polygon | 27,792 | `ADR_MNG_NO`, `SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `BUL_MAN_NO`, `EQB_MAN_SN`, `EFFECT_DE` |
| 도로명주소 건물 도형 | `TL_SPBD_ENTRC` | Point | 28,111 | `BUL_MAN_NO`, `ENTRC_SE`, `ENT_MAN_NO`, `EQB_MAN_SN`, `OPERT_DE`, `SIG_CD` |
| 도로명주소 건물 도형 | `TL_SPOT_CNTC` | PolyLine | 27,776 | `BSI_INT_SN`, `CNT_DRC_LN`, `CNT_DST_LN`, `ENT_MAN_NO`, `OPERT_DE`, `RDS_MAN_NO`, `RDS_SIG_CD`, `SIG_CD` |
| 도로명주소 전자지도 | `TL_SPBD_BULD` | Polygon | 55,819 | 건물 polygon + 도로명/지번/관리 속성 |
| 도로명주소 전자지도 | `TL_SPBD_ENTRC` | Point | 27,787 | 출입구 point |

### 경상남도

| 원천 | layer | geometry | rows |
|------|-------|----------|-----:|
| 도로명주소 건물 도형 | `TL_SGCO_RNADR_MST` | Polygon | 656,230 |
| 도로명주소 건물 도형 | `TL_SPBD_ENTRC` | Point | 661,416 |
| 도로명주소 건물 도형 | `TL_SPOT_CNTC` | PolyLine | 652,660 |
| 도로명주소 전자지도 | `TL_SPBD_BULD` | Polygon | 1,269,029 |
| 도로명주소 전자지도 | `TL_SPBD_ENTRC` | Point | 656,133 |

## Natural Key 비교

주소 polygon 비교 key:

```text
SIG_CD, RN_CD, BULD_SE_CD, BULD_MNNM, BULD_SLNO, BUL_MAN_NO, EQB_MAN_SN
```

출입구 point 비교 key:

```text
SIG_CD, BUL_MAN_NO, ENT_MAN_NO, EQB_MAN_SN
```

connection line은 출입구 참조만 비교한다.

```text
SIG_CD, ENT_MAN_NO
```

### 세종특별자치시 결과

| 비교 | left rows/distinct | right rows/distinct | 교집합 | left only | right only |
|------|-------------------:|--------------------:|-------:|----------:|-----------:|
| bundle `TL_SGCO_RNADR_MST` ↔ 전자지도 `TL_SPBD_BULD` | 27,792 / 27,792 | 55,819 / 55,819 | 15,339 | 12,453 | 40,480 |
| bundle `TL_SPBD_ENTRC` ↔ 전자지도 `TL_SPBD_ENTRC` | 28,111 / 28,111 | 27,787 / 27,787 | 27,766 | 345 | 21 |
| bundle `TL_SPOT_CNTC` 출입구 참조 ↔ bundle 출입구 참조 | 27,776 / 27,776 | 28,111 / 28,111 | 27,774 | 2 | 337 |

### 경상남도 결과

| 비교 | left rows/distinct | right rows/distinct | 교집합 | left only | right only |
|------|-------------------:|--------------------:|-------:|----------:|-----------:|
| bundle `TL_SGCO_RNADR_MST` ↔ 전자지도 `TL_SPBD_BULD` | 656,230 / 656,230 | 1,269,029 / 1,269,029 | 345,290 | 310,940 | 923,739 |
| bundle `TL_SPBD_ENTRC` ↔ 전자지도 `TL_SPBD_ENTRC` | 661,416 / 661,416 | 656,133 / 656,133 | 656,114 | 5,302 | 19 |
| bundle `TL_SPOT_CNTC` 출입구 참조 ↔ bundle 출입구 참조 | 652,660 / 652,660 | 661,416 / 661,416 | 652,660 | 0 | 8,756 |

해석:

- address polygon은 두 지역 모두 전자지도 `TL_SPBD_BULD`와 교집합이 절반 수준이거나 그보다 낮다. 이 레이어를 전자지도 `tl_spbd_buld_polygon`에 덮어쓰면 기존 C1/C2 기준이 바뀐다.
- 출입구 point는 전자지도 `TL_SPBD_ENTRC`와 대부분 겹치지만 완전히 같지는 않다. 특히 경남은 bundle only 5,302건이 있어 별도 품질 분석 가치가 있다.
- connection line은 대부분 bundle 출입구를 참조한다. 세종은 connection 2건이 bundle 출입구 key에 없고, 경남은 connection 쪽 누락은 없었다. 반대로 connection이 없는 출입구는 세종 337건, 경남 8,756건이다.

## 재현 명령

세종 빠른 비교:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/compare_building_shape_bundle.py \
  --bundle-zip "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 건물 도형/건물도형_전체분_세종특별자치시.zip" \
  --electronic-map-sido "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 전자지도/세종특별자치시"
```

경남 full key 비교는 NTFS의 `TL_SPBD_BULD.dbf` 126만 행을 스캔하므로 일반 테스트에서는 제외한다. 캐시 상태에 따라 수십 초에서 2분 안팎이 걸릴 수 있으며, 이번 PR의 선택형 pytest 재실행은 18.48초였다.

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/compare_building_shape_bundle.py \
  --bundle-zip "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 건물 도형/건물도형_전체분_경상남도.zip" \
  --electronic-map-sido "/mnt/f/dev/kor-travel-geo/data/juso/도로명주소 전자지도/경상남도"
```

선택형 pytest:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp KTG_SLOW_REAL_DATA=1 \
  .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_building_shape_bundle_gyeongnam_key_overlap_slow -q
```

## 후속 설계 원칙

후속에서 loader를 붙인다면 전자지도 테이블에 섞지 않고 별도 테이블로 둔다.

| 후보 테이블 | 원천 layer | 용도 |
|-------------|------------|------|
| `tl_roadaddr_buld_polygon` | `TL_SGCO_RNADR_MST` | 주소 단위 polygon 품질 분석, 상세 debug overlay |
| `tl_roadaddr_buld_entrc` | `TL_SPBD_ENTRC` | bundle 출입구와 T-039 direct 출입구/전자지도 출입구 차이 분석 |
| `tl_roadaddr_spot_cntc` | `TL_SPOT_CNTC` | C8 도로 인접성/connection line 분석 |

기본 `full_load_batch`에 자동 포함하는 조건:

1. 도로명주소 한글, direct 출입구, 건물 도형 bundle, 전자지도 기준월을 맞춘다.
2. C10 기준월 경고를 해결하거나 운영자가 명시적으로 허용한다.
3. C2/C4/C8 분석에서 기존 전자지도 기반 검증보다 더 설명력이 높다는 재측정 결과를 남긴다.
4. `mv_geocode_target`의 1주소 1행 계약을 바꾸지 않는다. geometry overlay는 별도 API 또는 debug/admin API로 노출한다.

## T-040 검증

- `python -m pytest tests/unit/test_building_shape_bundle.py tests/integration/test_real_extra_shape_sources.py -q` → 7 passed, 1 skipped.
- `KTG_SLOW_REAL_DATA=1 python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_building_shape_bundle_gyeongnam_key_overlap_slow -q` → 1 passed in 18.48s.
- `scripts/compare_building_shape_bundle.py`로 세종/경남 실제 파일을 직접 비교했다.
