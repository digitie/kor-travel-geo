# ADR-023: 별도 도형/출입구 자료는 full-load 기본 경로에 즉시 섞지 않고 후보별로 분리한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-030 실제 파일 검토

## 컨텍스트

`data/juso`에는 현재 로더가 쓰는 월간 텍스트 3종과 도로명주소 전자지도 외에도 다음 별도 묶음이 있다.

- `건물군 내 상세주소 동 도형`
- `구역의 도형`
- `도로명주소 건물 도형`
- `도로명주소 출입구 정보`

T-027 계획에서는 이들을 미지원 입력으로 표시했다. T-030에서 세종특별자치시 실제 ZIP을 열어 layer, geometry type, DBF row count/field, text row 구조를 확인했다.

## 결정

이 네 자료를 현재 full-load batch source child에 바로 추가하지 않는다. 대신 후보별 후속 작업으로 분리한다.

1. `도로명주소 출입구 정보`는 T-039 후보로 둔다. SHP가 아니라 direct `bd_mgt_sn + EPSG:5179 point` 텍스트라 현재 `tl_locsum_entrc` 후해소 실패와 C4 이상치 분석에 가장 직접적인 보완 후보다.
2. `도로명주소 건물 도형`은 T-040 후보로 둔다. `TL_SGCO_RNADR_MST`, `TL_SPBD_ENTRC`, `TL_SPOT_CNTC` bundle이며 전자지도 `TL_SPBD_BULD` 단순 중복이 아니다.
3. `건물군 내 상세주소 동 도형`은 T-041 후보로 둔다. 상세주소 동 polygon/point는 주소 대표 좌표보다 세밀하므로 serving path가 아니라 디버그 UI/상세주소 기능 요구가 있을 때 붙인다.
4. `구역의 도형`은 현재 전자지도 행정구역/기초구역과 중복되는 레이어가 많고, `TL_SCCO_GEMD`, `TL_SPPN_MAKAREA`만 추가 가치가 있다. 관리 UI 또는 품질 분석 필요가 생길 때 T-041 범위에서 검토한다.
5. 후속 loader는 모두 `source_yyyymm` 기준월을 명시하고, 현재 full-load 기준월과 섞는 경우 C10 또는 별도 consistency note로 드러내야 한다.

## 근거

- 기준월이 다르다. 세종 샘플의 별도 도형/출입구 자료는 `202605` 계열이고, 현재 full-load 기준은 도로명주소 한글 `202603`, 위치정보요약/내비 `202604`, 전자지도 `202604`다.
- `mv_geocode_target`은 `bd_mgt_sn` unique와 대표 좌표를 전제로 한다. 상세주소 동이나 다중 출입구를 즉시 펼치면 API cardinality와 MV unique index 계약이 깨질 수 있다.
- `도로명주소 출입구 정보`는 보완 가치가 크지만 기존 `locsum`, `navi`, `TL_SPBD_ENTRC`와 우선순위/중복 제거 규칙을 정해야 한다.
- `구역의 도형`은 이미 적재 중인 행정구역 계열과 많이 겹치므로, 지금 추가하면 load time과 스키마만 늘고 serving 개선은 불명확하다.

## 결과

- T-030은 문서와 실제 파일 구조 테스트만 남긴다.
- T-039/T-040/T-041을 새 backlog로 추가한다.
- T-027 최종 클린 적재 전까지 이 자료들은 "누락"이 아니라 "검토 후 분리된 후속 후보"로 취급한다.

## 남은 위험

- `도로명주소 출입구 정보`가 실제로 C4 이상치를 얼마나 줄이는지는 DB 적재 비교 전까지 모른다.
- `도로명주소 건물 도형`과 전자지도 `TL_SPBD_BULD`의 관계는 row count만으로 충분하지 않다. geometry overlap, `ADR_MNG_NO`/natural key 매칭률, 기준월 차이를 T-040에서 비교해야 한다.
