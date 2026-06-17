# ADR-026: 상세주소 동 도형과 구역 추가 레이어는 serving MV가 아니라 별도 overlay/분석 후보로 둔다

- 상태: accepted, partially amended by ADR-027
- 날짜: 2026-05-26
- 결정자: codex, T-041 구현

## 컨텍스트

T-030에서 `건물군 내 상세주소 동 도형`과 `구역의 도형` ZIP이 현재 full-load 기본 경로에 들어가지 않는 별도 원천으로 식별됐다. T-039/T-040에서 direct 출입구와 도로명주소 건물 도형 bundle을 먼저 처리한 뒤, T-041에서 남은 두 원천을 세종특별자치시와 경상남도 실제 파일로 다시 비교했다.

`건물군 내 상세주소 동 도형`은 다음 두 레이어를 갖는다.

- `TL_SGCO_RNADR_DONG`: 상세주소 동 polygon
- `TL_SPBD_ENTRC_DONG`: 상세주소 동 출입구 point

`구역의 도형`은 전자지도와 이름이 같은 5개 레이어와 추가 2개 레이어를 갖는다.

- 기존 전자지도 중복 후보: `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`
- 추가 후보: `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`

## 실제 비교 결과

상세주소 동 polygon은 전자지도 `TL_SPBD_BULD`의 부분집합이었다. 비교 key는 `BD_MGT_SN + EQB_MAN_SN`이다.

| 지역 | 상세주소 동 polygon | 전자지도 `TL_SPBD_BULD` | 교집합 | 상세주소 동 only | 전자지도 only |
|------|--------------------:|-------------------------:|-------:|-----------------:|--------------:|
| 세종 | 40,478 | 55,819 | 40,478 | 0 | 15,341 |
| 경남 | 923,702 | 1,269,029 | 923,702 | 0 | 345,327 |

상세주소 동 출입구는 모든 상세주소 동 polygon에 제공되지 않았다. `SIG_CD + BUL_MAN_NO` 기준으로 세종은 4,098행이 2,182개 building ref를, 경남은 35,649행이 16,260개 building ref를 가리켰다.

`구역의 도형`의 중복 후보 5개 레이어는 세종/경남에서 전자지도와 key 기준 완전히 같았다.

| 지역 | 중복 레이어 | 결과 |
|------|-------------|------|
| 세종 | `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS` | 모든 key 교집합 100%, 좌우 only 0 |
| 경남 | `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS` | 모든 key 교집합 100%, 좌우 only 0 |

추가 레이어는 별도 의미를 갖는다.

- `TL_SCCO_GEMD.EMD_CD`는 같은 ZIP의 `TL_SCCO_EMD.EMD_CD`와 교집합이 0건이었다. 기존 읍면동 테이블에 union하면 코드 의미가 섞일 수 있다.
- `TL_SPPN_MAKAREA`는 `SIG_CD + MAKAREA_ID`가 distinct key다. 세종 146행, 경남 3,486행 모두 distinct였다.

## 결정

두 원천 모두 현행 `mv_geocode_target`과 기본 `full_load_batch`에 자동 포함하지 않는다.

1. `건물군 내 상세주소 동 도형`은 기존 `tl_spbd_buld_polygon`에 섞지 않는다. 필요하면 `tl_detail_dong_polygon`, `tl_detail_dong_entrc` 같은 별도 overlay 테이블을 둔다.
2. `구역의 도형`의 중복 5개 레이어는 다시 적재하지 않는다.
3. `TL_SCCO_GEMD`와 `TL_SPPN_MAKAREA`는 필요하면 각각 `tl_scco_gemd`, `tl_sppn_makarea` 같은 별도 테이블로 적재한다.
4. 이 레이어들은 serving 대표 좌표를 바꾸는 원천이 아니라 디버그 UI overlay, 상세주소 기능, 품질 분석용 원천으로 취급한다.
5. 기준월이 `202605` 계열이므로 기존 `202603~202604` full-load와 섞을 때는 C10 경고 또는 별도 consistency note로 드러낸다.

ADR-027은 이 결정 중 `TL_SPPN_MAKAREA`의 용도를 보강한다. `TL_SPPN_MAKAREA`는 여전히 `mv_geocode_target`에는 union하지 않지만, 단순 overlay보다 높은 가치가 있는 국가지점번호 표기 의무지역 polygon이므로 별도 테이블로 적재해 geocode/reverse geocode 보조 데이터로 활용한다.

## 근거

- `mv_geocode_target`은 1주소 1행과 대표 좌표를 전제로 한다. 상세주소 동 polygon/출입구를 즉시 펼치면 결과 cardinality와 응답 계약이 바뀐다.
- 상세주소 동 polygon은 전자지도 building polygon의 부분집합이므로, 기본 건물 polygon 검증을 대체하면 전체 건물이 아니라 상세주소 동 대상 건물만 검증하게 된다.
- 구역 중복 레이어 5개는 전자지도에 이미 있으므로 다시 적재해도 serving 개선이 없다.
- `TL_SCCO_GEMD`는 기존 `TL_SCCO_EMD`와 key가 겹치지 않아 같은 테이블에 합치면 침묵하는 의미 충돌이 생길 수 있다.

## 결과

- `src/kortravelgeo/loaders/shape_dbf.py`를 추가해 DBF/SHP key-set 분석 helper를 공용화했다.
- T-040의 `building_shape_bundle.py`는 이 공용 helper를 사용하도록 정리했다.
- `src/kortravelgeo/loaders/extra_shape_layers.py`와 `scripts/compare_extra_shape_layers.py`를 추가했다.
- 빠른 세종 실제 파일 테스트는 기본 pytest에 포함하고, 경남 full key scan은 `KTG_SLOW_REAL_DATA=1` 선택 테스트로 둔다.

## 남은 위험

- `TL_SCCO_GEMD`의 정확한 업무 의미는 제공자 PDF/레이아웃 문서 해석이 더 필요하다. 이번 결정은 key overlap과 현행 serving 계약 기준의 보류 결정이다.
- `TL_SPPN_MAKAREA`는 ADR-027에서 국가지점번호 보조 데이터로 용도를 확정했지만, 개별 국가지점번호판 point 목록이 아니라 표기 의무지역 polygon이라는 한계를 갖는다. 국가지점번호 문자열 parser/generator는 별도 설계가 필요하다.
- 상세주소 동 도형을 사용자 기능으로 노출하려면 주소 검색 결과에서 동/호/출입구를 어떻게 랭킹하고 응답할지 별도 DTO/API 설계가 필요하다.
