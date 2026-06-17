# ADR-024: `도로명주소 출입구 정보`는 별도 테이블에 저장하고 same-month direct fallback으로 사용한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-039 구현

## 컨텍스트

T-030에서 `도로명주소 출입구 정보` ZIP이 SHP가 아니라 `RNENTDATA_2605_<시군구코드>.txt` 텍스트이며, 각 row가 direct `bd_mgt_sn`과 EPSG:5179 좌표를 제공함을 확인했다.

기존 `tl_locsum_entrc`는 위치정보요약DB 기반 출입구 좌표 정본이지만 실제 `entrc_*.txt`에 `bd_mgt_sn`이 없어 후처리 해소가 필요하다. 전국 full-load 기준으로 이 해소 실패가 C3 WARN의 큰 원인이었고, C4 일부 이상치는 locsum 좌표와 polygon 사이의 거리 문제를 드러냈다.

T-039에서 실제 17개 ZIP을 읽어 계측한 결과:

- 총 원천 행 수는 6,418,169행이다.
- 모든 row는 19컬럼이며 `ent_source_cd='RM'`, `ent_detail_cd='01'`이다.
- 세종과 경남 샘플에서 `bd_mgt_sn`은 행마다 유일했다.
- 반면 `ent_man_no`는 일부 row에서 비어 있었다. 세종 9건, 경남 100건이 빈 값이었다.
- 세종 원천 27,868행 중 유효 좌표 적재 대상은 27,779행이었다.

## 결정

`도로명주소 출입구 정보`를 기존 `tl_locsum_entrc`에 섞어 넣지 않고, 별도 테이블 `tl_roadaddr_entrc`에 적재한다.

핵심 규칙:

1. `tl_roadaddr_entrc`의 PK는 `bd_mgt_sn` 단독으로 둔다.
2. `ent_man_no`는 nullable 원천 보존 필드로 둔다.
3. 좌표가 비어 있거나 `0/0` sentinel인 row는 `geom NOT NULL` 테이블에 적재하지 않는다.
4. `mv_geocode_target` 대표 좌표는 `tl_locsum_entrc` → same-month `tl_roadaddr_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. same-month는 `tl_roadaddr_entrc.source_yyyymm`이 현재 `tl_juso_text.source_yyyymm` 집합에 포함되는 경우다.
5. direct entrance와 locsum entrance 모두 API 응답의 기존 `pt_source='entrance'` 계약을 유지한다.
6. `roadaddr_entrance_load`는 API/CLI job으로 제공하지만 기본 `full_load_batch` child에는 넣지 않는다.
7. C3/C4/C6/C7/C8은 `tl_locsum_entrc`와 same-month `tl_roadaddr_entrc`를 합친 대표 출입구 CTE를 사용한다.
8. C10은 `tl_roadaddr_entrc.source_yyyymm`을 기준월 비교 대상에 포함한다. T-027 최종 클린 적재 보강 이후 C10은 row-level `source_yyyymm` 집계를 우선하고 `load_manifest`를 fallback으로 사용한다.

## 근거

- direct `bd_mgt_sn`은 후해소 실패를 피하므로 serving 대표 좌표 후보로 가치가 높다.
- 기존 `tl_locsum_entrc`에 임의 삽입하면 원천 의미가 섞인다. locsum은 `sig_cd + ent_man_no` PK와 `ent_se_cd` 대표/부속 구분을 갖지만, RNENTDATA는 건물당 대표 출입구 1건 형태에 가깝고 `ent_man_no`도 nullable이다.
- 새 `pt_source` 값을 추가하면 vworld 호환 응답과 기존 클라이언트 처리에 영향을 준다. 지금은 `entrance`라는 큰 분류를 유지하고, 세부 원천은 운영 테이블과 정합성 sample에서 본다.
- 기준월이 202605 계열이라 기본 full-load에 자동 포함하면 C10 경고가 상시 발생할 수 있다. T-027 실제 재검증에서는 기준월이 다른 direct 출입구를 serving 좌표로 우선 사용했을 때 C4/C6/C7 오류도 증가했다. 따라서 운영자가 명시적으로 적재하더라도 같은 기준월 세트일 때만 MV serving 후보로 반영한다.

## 결과

- T-039에서 DDL/Alembic `0005_t039_roadaddr_entrance_table`, loader, CLI `load roadaddr-entrances`, API job kind `roadaddr_entrance_load`를 추가했다.
- `mv_geocode_target`은 `tl_roadaddr_entrc`가 비어 있거나 기준월이 다르면 기존 locsum/navi 동작과 동일하다.
- 같은 기준월의 `tl_roadaddr_entrc`를 적재한 뒤 `refresh mv --swap`을 실행하면 direct entrance가 locsum 결측 건의 fallback 대표 좌표가 될 수 있다.

## 남은 위험

- T-027 최종 클린 적재에서는 `RNENTDATA_2605_*`를 함께 적재하되 same-month gate를 적용해 serving 승격을 보류했다. 남은 위험은 같은 기준월 세트에서 direct fallback이 실제로 C3를 줄이면서 C4/C6/C7을 악화시키지 않는지 재측정하는 것이다.
- `RNENTDATA_2605_*`와 다른 기준월의 `rnaddrkor_*`, `locsum`, SHP를 섞는 운영 모드에서는 C10 WARN을 정상적인 운영 경고로 해석하되, direct 출입구는 분석용으로만 둔다.
- direct entrance와 locsum entrance의 좌표 차이가 큰 건에 대해 어느 원천을 신뢰할지, 데이터 품질 대시보드에서 비교 sample을 추가할 필요가 있다.
