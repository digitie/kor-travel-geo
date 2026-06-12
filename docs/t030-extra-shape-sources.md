# T-030: 별도 도형/출입구 자료 검토

## 상태

- 상태: 결정 완료
- 대상 브랜치: `codex/t030-extra-shape-sources`
- 대상 데이터:
  - `data/juso/건물군 내 상세주소 동 도형/*.zip`
  - `data/juso/구역의 도형/*.zip`
  - `data/juso/도로명주소 건물 도형/*.zip`
  - `data/juso/도로명주소 출입구 정보/*.zip`
- 관련 ADR: ADR-023

## 결론

네 자료를 현재 full-load 경로에 즉시 추가하지 않는다. 모두 가치가 있지만 현행 `mv_geocode_target`의 주소 단위 geocoding/reverse serving을 바로 바꾸기에는 기준월, cardinality, 레이어 의미가 다르다.

후속 구현은 다음처럼 분리한다.

| 자료 | 결정 | 후속 |
|------|------|------|
| `도로명주소 출입구 정보` | direct `bd_mgt_sn + EPSG:5179` 텍스트라 가장 유용한 보완 후보 | T-039 완료. `tl_roadaddr_entrc` 선택 적재 |
| `도로명주소 건물 도형` | 주소 단위 polygon/entrance/connection bundle. 전자지도 `TL_SPBD_BULD` 단순 중복이 아님 | T-040 완료. 분석 helper 유지, serving loader 보류 |
| `건물군 내 상세주소 동 도형` | 상세주소 동/동 출입구 레벨. 세종/경남 기준 전자지도 건물 polygon의 부분집합 | T-041 완료. overlay/상세주소 기능 후보 |
| `구역의 도형` | 기존 전자지도 행정구역/기초구역 5개는 key 기준 완전 중복, `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`만 추가 | T-041 완료. `TL_SCCO_GEMD`는 별도 overlay 후보, `TL_SPPN_MAKAREA`는 T-042에서 국가지점번호 보조 geocode/reverse 데이터로 구현 |

## 실제 파일 구조

세종특별자치시 ZIP을 기준으로 구조를 직접 확인했다.

### 건물군 내 상세주소 동 도형

파일: `건물군내동도형_전체분_세종특별자치시.zip`

| layer | geometry | rows | 주요 필드 |
|-------|----------|------|-----------|
| `TL_SGCO_RNADR_DONG` | Polygon | 40,478 | `ADR_MNG_NO`, `BD_MGT_SN`, `SIG_CD`, `BUL_MAN_NO`, `RN_CD`, `BULD_*`, `EQB_MAN_SN` |
| `TL_SPBD_ENTRC_DONG` | Point | 4,098 | `SIG_CD`, `ENT_MAN_NO`, `BUL_MAN_NO`, `ENTRC_SE`, `ENTRC_DC` |

이 자료는 건물군 안의 동 단위 상세주소를 표현한다. 현행 API의 대표 주소 좌표보다 세밀하고, 사용자 대상 검색 결과를 즉시 다중화할 경우 응답 cardinality가 바뀐다. 따라서 디버그 UI/품질 분석/상세주소 기능이 필요해질 때 별도 loader로 붙인다.

### 구역의 도형

파일: `구역의도형_전체분_세종특별자치시.zip`

| layer | geometry | rows | 현재 전자지도와 관계 |
|-------|----------|------|----------------------|
| `TL_SCCO_CTPRVN` | Polygon | 1 | 중복 |
| `TL_SCCO_SIG` | Polygon | 1 | 중복 |
| `TL_SCCO_EMD` | Polygon | 33 | 중복 |
| `TL_SCCO_LI` | Polygon | 117 | 중복 |
| `TL_KODIS_BAS` | Polygon | 155 | 중복 |
| `TL_SCCO_GEMD` | Polygon | 24 | 추가 |
| `TL_SPPN_MAKAREA` | Polygon | 146 | 추가 |

현재 전자지도 로더가 이미 행정구역과 기초구역을 적재하므로 중복 5개 레이어를 다시 추가할 필요는 낮다. `TL_SCCO_GEMD`는 기존 읍면동과 key가 겹치지 않는 별도 고시/행정 구역 overlay 후보로 둔다.

`TL_SPPN_MAKAREA`는 별도로 취급한다. 이 레이어는 지점번호표기 의무지역 polygon으로, 건물이 없어 도로명주소가 부여되지 않는 산악·해안·도서·하천 주변 등에서 국가지점번호를 표기해야 하는 구역을 나타낸다. 따라서 단순 관리 UI overlay뿐 아니라 다음 geocode/reverse geocode 보조 기능에 사용할 수 있다.

- reverse geocode: 입력 좌표가 어떤 `TL_SPPN_MAKAREA` polygon 안에 있는지 확인해 `x_extension.sppn_makarea`로 국가지점번호 표기 의무지역 문맥을 제공한다.
- geocode: `라마 1234 5678` 같은 국가지점번호 문자열 parser가 좌표를 계산한 뒤, 그 좌표가 표기 의무지역에 속하는지 검증하고 `MAKAREA_NM` 같은 구역 metadata를 붙인다. EPSG:5179 좌표에서 국가지점번호 문자열을 만드는 formatter도 제공한다.
- 검색/지도: 구역명(`MAKAREA_NM`) 기반 검색은 정확한 주소 geocode가 아니라 polygon centroid/bbox를 반환하는 낮은 confidence 구역 검색으로 분리한다.

주의할 점은 `TL_SPPN_MAKAREA`가 개별 국가지점번호판 point 목록이 아니라 의무지역 경계 polygon이라는 점이다. 실제 표지판 위치나 시설물 목록이 필요한 경우 별도 원천이 필요하다.

### 도로명주소 건물 도형

파일: `건물도형_전체분_세종특별자치시.zip`

| layer | geometry | rows | 주요 필드 |
|-------|----------|------|-----------|
| `TL_SGCO_RNADR_MST` | Polygon | 27,792 | `ADR_MNG_NO`, `SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `BUL_MAN_NO`, `EQB_MAN_SN` |
| `TL_SPBD_ENTRC` | Point | 28,111 | `SIG_CD`, `BUL_MAN_NO`, `ENTRC_SE`, `ENT_MAN_NO`, `EQB_MAN_SN` |
| `TL_SPOT_CNTC` | PolyLine | 27,776 | `ENT_MAN_NO`, `RDS_MAN_NO`, `RDS_SIG_CD`, `BSI_INT_SN` |

전자지도 `TL_SPBD_BULD` 세종 row count는 55,819이고, 이 ZIP의 `TL_SGCO_RNADR_MST`는 27,792다. T-040 natural key 비교 결과 세종 address polygon key 교집합은 15,339건, 경남은 345,290건으로 단순 중복이 아니다. direct address polygon/entrance/road connection으로 C2/C4/C8 후속 분석에 가치가 있지만, 기준월이 `202605`이고 현재 full-load 기준월(`202603/202604`)과 다르므로 즉시 serving path에 섞지 않는다.

### 도로명주소 출입구 정보

파일: `도로명주소출입구_전체분_세종특별자치시.zip`

ZIP 안에는 SHP가 아니라 `RNENTDATA_2605_36110.txt` 하나가 있다. 첫 행:

```text
36110101200000200181100000|3611010100|세종특별자치시||반곡동||361102000002|한누리대로|0|1811|0|30145|20181204||32169|RM|01|983296.172464|1833330.968984
```

주요 index:

| index | 의미 추정 | 비고 |
|-------|-----------|------|
| 0 | `bd_mgt_sn` | 26자리 direct key |
| 1 | `bjd_cd` | 법정동 |
| 6~10 | `rncode_full`, 도로명, 건물구분/본번/부번 | 도로명주소 키 |
| 11 | 우편번호 | |
| 12 | 고시/기준일 | |
| 14 | 출입구 관리번호 | `32169` |
| 15~16 | 출입구/좌표 구분 코드 | 예: `RM`, `01` |
| 17~18 | EPSG:5179 X/Y | meter 좌표 |

이 자료는 `tl_locsum_entrc`와 달리 `bd_mgt_sn`을 직접 제공한다. 따라서 위치정보요약DB의 natural key 후해소가 실패하는 건이나 C4 이상치 분석에 직접 보완 후보가 된다. T-039에서 별도 테이블 `tl_roadaddr_entrc`와 loader를 추가했다. T-027 최종 클린 적재 재검증 이후 MV 대표 좌표는 `tl_locsum_entrc`를 먼저 쓰고, `tl_roadaddr_entrc`는 `source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 기준월일 때만 fallback으로 사용한다. 현재 로컬 원천은 기준월이 `202605`라 기본 full-load 6종에는 자동 포함하지 않고 명시적 선택 적재/분석용으로 둔다.

## 결정

ADR-023:

1. 현재 full-load source child에는 네 자료를 추가하지 않는다.
2. `도로명주소 출입구 정보`는 T-039에서 구현했다. direct `bd_mgt_sn + 5179 point`라 현재 결측/이상치 분석에 바로 도움이 될 수 있지만, 기준월 차이 때문에 기본 full-load 자동 포함은 제외한다.
3. `도로명주소 건물 도형`은 T-040에서 전자지도 `TL_SPBD_BULD`와의 차이를 세종/경남 기준으로 비교했다. 단순 중복이 아니므로 loader가 필요하면 별도 분석 테이블로 둔다.
4. 상세주소 동 도형과 구역 추가 레이어는 T-041에서 검토했다. 상세주소 동과 `TL_SCCO_GEMD`는 serving API가 아니라 디버그 UI/품질 분석/상세주소 기능이 필요할 때 별도 overlay 테이블로 붙인다.
5. `TL_SPPN_MAKAREA`는 T-042에서 국가지점번호 표기 의무지역 데이터로 별도 적재한다. 단, 현행 `mv_geocode_target` 주소 MV에는 섞지 않고 reverse/geocode enrichment 경로로 연결한다.
6. 모든 후속 loader는 `source_yyyymm` 기준월을 명시하고, 현재 full-load 기준월과 섞을 때 C10 또는 별도 consistency note로 드러나야 한다.

## 검증

이번 PR에서 추가한 테스트:

- `tests/integration/test_real_extra_shape_sources.py`
  - 세종 `건물군 내 상세주소 동 도형` ZIP의 layer, geometry type, DBF row count/fields 검증.
  - 세종 `구역의 도형` ZIP이 현재 전자지도 중복 레이어와 추가 레이어를 함께 갖는지 검증.
  - 세종 `도로명주소 건물 도형` ZIP이 address polygon/entrance/connection bundle인지 검증.
  - 세종 `도로명주소 출입구 정보` ZIP의 19컬럼 text와 direct EPSG:5179 좌표를 검증.

실행 결과:

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q` → 128 passed, 3 skipped.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check .` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kortravelgeo` → 통과.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python scripts/export_openapi.py --check --output openapi.json` → drift 없음.
- `git diff --check` → 통과.

## 다음 작업

- T-039: 완료. `도로명주소 출입구 정보` direct entrance text loader와 `tl_roadaddr_entrc` 선택 적재 구현.
- T-040: 완료. `도로명주소 건물 도형` bundle과 전자지도 `TL_SPBD_BULD` 차이 분석.
- T-041: 완료. 상세주소 동 도형은 전자지도 건물 부분집합으로 확인했고, 구역 추가 레이어는 `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`만 별도 후보로 남겼다. 이후 ADR-027에서 `TL_SPPN_MAKAREA`는 국가지점번호 보조 geocode/reverse 데이터 후보로 승격했다.
- T-042: 완료. `TL_SPPN_MAKAREA` loader, `tl_sppn_makarea`, 국가지점번호 parser/formatter, geocode/reverse `x_extension.sppn_makarea` 보조 경로를 구현했고 세종 실제 ZIP 146행 적재를 검증했다.
