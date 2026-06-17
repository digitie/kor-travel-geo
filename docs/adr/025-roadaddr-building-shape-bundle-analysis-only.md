# ADR-025: `도로명주소 건물 도형` bundle은 전자지도 테이블에 섞지 않고 별도 분석 후보로 둔다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-040 구현

## 컨텍스트

T-030에서 `도로명주소 건물 도형` ZIP이 `TL_SGCO_RNADR_MST` polygon, `TL_SPBD_ENTRC` point, `TL_SPOT_CNTC` polyline으로 구성된 address building bundle임을 확인했다. 이름은 기존 도로명주소 전자지도 `TL_SPBD_BULD`/`TL_SPBD_ENTRC`와 비슷하지만 row count가 달라 단순 중복인지, 보완 원천인지 확인이 필요했다.

T-040에서 세종특별자치시와 경상남도 실제 파일을 비교했다. address polygon key는 `SIG_CD + RN_CD + BULD_SE_CD + BULD_MNNM + BULD_SLNO + BUL_MAN_NO + EQB_MAN_SN`으로, 출입구 key는 `SIG_CD + BUL_MAN_NO + ENT_MAN_NO + EQB_MAN_SN`으로 비교했다.

주요 결과:

| 지역 | bundle `TL_SGCO_RNADR_MST` | 전자지도 `TL_SPBD_BULD` | 교집합 | bundle only | 전자지도 only |
|------|---------------------------:|-------------------------:|-------:|------------:|--------------:|
| 세종 | 27,792 | 55,819 | 15,339 | 12,453 | 40,480 |
| 경남 | 656,230 | 1,269,029 | 345,290 | 310,940 | 923,739 |

출입구 point는 대부분 겹치지만 완전히 같지 않았다. 세종은 bundle only 345건, 전자지도 only 21건이고, 경남은 bundle only 5,302건, 전자지도 only 19건이다.

## 결정

`도로명주소 건물 도형` bundle을 현행 `tl_spbd_buld_polygon` 또는 `tl_locsum_entrc`에 섞지 않는다. T-040에서는 비교 helper와 문서만 추가하고 serving loader는 만들지 않는다.

후속 loader가 필요하면 다음처럼 별도 테이블을 만든다.

| 후보 테이블 | 원천 layer | 역할 |
|-------------|------------|------|
| `tl_roadaddr_buld_polygon` | `TL_SGCO_RNADR_MST` | 주소 단위 polygon 품질 분석과 debug overlay |
| `tl_roadaddr_buld_entrc` | `TL_SPBD_ENTRC` | bundle 출입구와 T-039 direct 출입구/전자지도 출입구 차이 분석 |
| `tl_roadaddr_spot_cntc` | `TL_SPOT_CNTC` | C8 도로 인접성/connection line 분석 |

## 근거

- address bundle polygon과 전자지도 building polygon의 natural key 교집합이 낮아, 기존 테이블에 덮어쓰면 C1/C2 의미가 바뀐다.
- T-039 direct 출입구 텍스트가 이미 `bd_mgt_sn + 5179 point`를 제공하므로 대표 좌표 보강은 이 SHP bundle보다 단순한 경로가 있다.
- bundle 기준월이 `202605`라 기본 `202603~202604` full-load에 자동 포함하면 C10 경고가 의도적으로 발생한다.
- `TL_SPOT_CNTC` connection line은 C8 분석에 가치가 있지만, `mv_geocode_target`의 1주소 1행 serving 계약과는 별개다.

## 결과

- `src/kortravelgeo/loaders/building_shape_bundle.py`와 `scripts/compare_building_shape_bundle.py`를 추가해 실제 DBF key overlap을 재현 가능하게 했다.
- 빠른 세종 실제 파일 테스트는 기본 pytest에 포함하고, 경남 full key scan은 `KTG_SLOW_REAL_DATA=1` 선택 테스트로 둔다.
- T-041에서 상세주소 동/구역 추가 레이어도 검토 완료했다. 두 원천 모두 기본 full-load/MV에는 섞지 않고 별도 overlay/분석 후보로 둔다.
