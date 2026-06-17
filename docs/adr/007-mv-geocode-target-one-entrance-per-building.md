# ADR-007: `mv_geocode_target`은 건물당 대표 출입구 1건만 보유한다

- 상태: accepted (위치정보요약DB 기반으로 갱신, ADR-012 후속)
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
출입구 데이터(`tl_locsum_entrc`, 위치정보요약DB 기반)는 한 건물(`BD_MGT_SN`)에 출입구가 여러 개일 수 있다. 평면화 MV가 단순 join으로 다대다를 펼치면 `UNIQUE (bd_mgt_sn)` 인덱스가 깨지고 `REFRESH MATERIALIZED VIEW CONCURRENTLY`가 불가능하며, 도로명/지번 lookup 결과도 출입구 수만큼 부풀어 라우터가 추가 dedup 로직을 떠안는다.

## 결정
`mv_geocode_target`은 건물당 **대표 출입구 한 건**만 보유한다. 선택 순서(SQL `DISTINCT ON (bd_mgt_sn)` 기반):

1. `ent_se_cd = '0'` (대표 출입구 코드) 우선
2. `buld_se_cd`(지상/지하)와 일치하는 출입구
3. 모호하면 `ent_man_no` 오름차순 첫 한 건

비대표 출입구가 필요한 use-case(내비 진입점, 차량 진입 등)는 `tl_locsum_entrc` 또는 `tl_navi_entrc`를 직접 조회한다. 출입구가 0개인 건물은 ADR-012 후속으로 `tl_navi_buld_centroid`의 centroid를 fallback 좌표로 사용한다.

## 근거
- 지오코딩 라우터가 `bd_mgt_sn` 단위 단일 row를 가정하므로 `UNIQUE` 인덱스 + CONCURRENTLY refresh 사용 가능.
- 위치정보요약DB의 `ent_se_cd`는 SHP보다 명확해 대표 선택 규칙이 안정적.
- 역지오코딩은 처음부터 `tl_locsum_entrc` 전체에서 GiST 최근접을 찾기 때문에 MV 단순화의 부담이 없다.

## 결과(긍정)
- 도로명/지번 lookup 결과가 항상 0 또는 1건. 라우터 로직 단순.
- ADR-011 (load_jobs)과 결합해 적재→swap→이전 MV drop 흐름이 깔끔.

## 결과(부정)
- 비대표 출입구·내비 진입점 응답이 필요해지면 별도 조회 경로 필요(ADR-012가 텍스트 보조 테이블로 흡수).

## 후속
- (open) `ent_se_cd` 값 분포가 시도별로 다른지 실데이터 검증 — ADR-012의 정합성 검증 리포트에 포함.
