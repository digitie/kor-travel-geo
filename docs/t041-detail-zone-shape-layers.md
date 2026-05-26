# T-041: 상세주소 동 도형과 구역 추가 레이어 검토

## 상태

- 상태: 구현/결정 완료
- 대상 브랜치: `codex/t041-extra-shape-layer-review`
- 대상 원천:
  - `data/juso/건물군 내 상세주소 동 도형/건물군내동도형_전체분_세종특별자치시.zip`
  - `data/juso/건물군 내 상세주소 동 도형/건물군내동도형_전체분_경상남도.zip`
  - `data/juso/구역의 도형/구역의도형_전체분_세종특별자치시.zip`
  - `data/juso/구역의 도형/구역의도형_전체분_경상남도.zip`
  - 비교 기준: `data/juso/도로명주소 전자지도/{세종특별자치시,경상남도}`
- 관련 ADR: ADR-023, ADR-026

## 결론

T-041에서도 기본 `full_load_batch`와 `mv_geocode_target`에는 새 레이어를 섞지 않는다.

`건물군 내 상세주소 동 도형`은 상세주소 동 polygon과 동 출입구 point를 제공한다. 하지만 세종/경남 실제 파일 기준으로 polygon의 `BD_MGT_SN + EQB_MAN_SN` key는 기존 전자지도 `TL_SPBD_BULD`의 부분집합이었다. 즉, 주소 대표 좌표를 보강하는 새 원천이라기보다 상세주소 동/건물군 내부 표시를 위한 분석 원천에 가깝다.

`구역의 도형`은 기존 전자지도와 이름이 같은 5개 레이어(`TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`)가 세종/경남에서 key 기준 완전히 일치했다. 새 가치가 있는 레이어는 `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA` 두 개뿐이다. 이 둘도 지오코딩 대표 좌표에는 직접 필요하지 않으므로 관리 UI overlay나 품질 분석 요구가 생길 때 별도 테이블로 적재한다.

이번 PR의 산출물은 다음으로 제한한다.

- 공용 DBF/SHP 분석 helper: `src/kraddr/geo/loaders/shape_dbf.py`
- T-041 비교 helper: `src/kraddr/geo/loaders/extra_shape_layers.py`
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
| `TL_SPPN_MAKAREA` | `SIG_CD`, `MAKAREA_ID` | 시군구별 고시/표시 구역으로 보인다. `MAKAREA_NM`은 중복될 수 있으므로 key로 쓰지 않는다. |

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

## 후속 설계 원칙

후속 loader가 필요하면 전자지도 테이블에 섞지 않고 별도 테이블로 둔다.

| 후보 테이블 | 원천 layer | 용도 |
|-------------|------------|------|
| `tl_detail_dong_polygon` | `TL_SGCO_RNADR_DONG` | 상세주소 동/건물군 내부 polygon overlay, 상세주소 기능 |
| `tl_detail_dong_entrc` | `TL_SPBD_ENTRC_DONG` | 상세주소 동 출입구 overlay, 건물군 내부 진입점 검토 |
| `tl_scco_gemd` | `TL_SCCO_GEMD` | 고시 읍면동 또는 별도 구역 overlay |
| `tl_sppn_makarea` | `TL_SPPN_MAKAREA` | 고시/표시 구역 overlay |

기본 `full_load_batch`에 자동 포함하는 조건:

1. 이 레이어들을 조회하는 명확한 API 또는 관리 UI 화면이 먼저 정의되어야 한다.
2. `mv_geocode_target`의 1주소 1행 계약과 대표 좌표 계약을 바꾸지 않아야 한다.
3. 현재 전자지도 중복 레이어는 다시 적재하지 않고, 추가 가치가 있는 레이어만 적재해야 한다.
4. 기준월이 `202605` 계열이므로 기존 `202603~202604` full-load와 섞을 때 C10 경고 또는 별도 consistency note가 남아야 한다.
5. `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key가 겹치지 않으므로 같은 테이블에 union하지 않아야 한다.

## 재현 명령

세종 빠른 비교:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/compare_extra_shape_layers.py \
  --detail-dong-zip "/mnt/f/dev/python-kraddr-geo/data/juso/건물군 내 상세주소 동 도형/건물군내동도형_전체분_세종특별자치시.zip" \
  --zone-zip "/mnt/f/dev/python-kraddr-geo/data/juso/구역의 도형/구역의도형_전체분_세종특별자치시.zip" \
  --electronic-map-sido "/mnt/f/dev/python-kraddr-geo/data/juso/도로명주소 전자지도/세종특별자치시"
```

경남 선택형 비교:

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp KRADDR_GEO_SLOW_REAL_DATA=1 \
  .venv/bin/python -m pytest \
  tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q
```

## 검증

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_building_shape_bundle.py tests/unit/test_extra_shape_layers.py tests/integration/test_real_extra_shape_sources.py -q` → 11 passed, 2 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp KRADDR_GEO_SLOW_REAL_DATA=1 .venv/bin/python -m pytest tests/integration/test_real_extra_shape_sources.py::test_actual_detail_and_zone_gyeongnam_key_overlap_slow -q` → 1 passed in 16.74s.
- `scripts/compare_extra_shape_layers.py`로 세종 실제 파일 JSON 출력을 확인했다.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 148 passed, 5 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo scripts/compare_extra_shape_layers.py scripts/compare_building_shape_bundle.py` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `git diff --check` → 통과.
