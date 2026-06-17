# ADR-022: 보조 지번 원천은 `tl_juso_text`가 아니라 1:N 링크 테이블로 모델링한다

- 상태: accepted
- 날짜: 2026-05-26
- 결정자: codex, T-029 실제 파일 검토

## 컨텍스트

도로명주소 한글 전체분에는 `rnaddrkor_*.txt`와 함께 `jibun_rnaddrkor_*.txt`가 배포된다. T-028 daily ZIP에는 같은 성격의 `TH_SGCO_RNADR_LNBR.TXT` member가 있다. 두 파일은 모두 건물관리번호와 지번을 연결하지만, 현재 `tl_juso_text`는 한 건물 행에 대표 지번 1개만 보관한다.

실제 파일 계측 결과 이 원천들은 대표 지번 보정용이 아니라 보조 지번 1:N 관계다.

- 전국 `jibun_rnaddrkor_*`: 1,769,370행, distinct `bd_mgt_sn` 986,309, 2개 이상 보조 지번을 가진 건물 334,789건, 한 건물 최대 545행.
- 서울 `jibun_rnaddrkor_seoul.txt`: 89,290행, distinct `bd_mgt_sn` 52,280, 2개 이상 보조 지번을 가진 건물 13,318건.
- 서울 `jibun_rnaddrkor` PNU와 `rnaddrkor` 대표 PNU 비교: 89,290행 중 89,289행이 대표 PNU와 다르다.
- daily `20260401` LNBR: 204행, distinct `bd_mgt_sn` 72, 2개 이상 변경 지번을 가진 건물 31건, 코드 분포 `31=74`, `63=130`.

## 결정

`jibun_rnaddrkor_*`와 daily `LNBR`는 `tl_juso_text.pnu`에 덮어쓰지 않는다. T-038에서 별도 테이블 `tl_juso_parcel_link`를 만든다.

구현된 테이블의 핵심:

- PK: `(bd_mgt_sn, pnu)`
- 주요 컬럼: `bd_mgt_sn`, `pnu`, `bjd_cd`, `mntn_yn`, `lnbr_mnnm`, `lnbr_slno`, `sig_cd`, `rn_cd`, `buld_se_cd`, `buld_mnnm`, `buld_slno`, `source_kind`, `source_file`, `source_yyyymm`, `last_mvmn_de`
- 인덱스: `pnu`, 도로명 건물번호 키(`sig_cd`, `rn_cd`, `buld_se_cd`, `buld_mnnm`, `buld_slno`)
- `bd_mgt_sn`은 `tl_juso_text`를 참조하고 `ON DELETE CASCADE`를 사용한다.

`rnaddrkor_*.txt`에서 온 `tl_juso_text.pnu`는 계속 대표 PNU로 유지한다. `mv_geocode_target`도 지금처럼 `bd_mgt_sn` unique를 유지한다.

## 근거

- 한 건물에 보조 지번이 수백 개까지 붙을 수 있으므로 `tl_juso_text` 1행 구조에 넣으면 데이터가 손실된다.
- 대표 PNU와 보조 PNU의 의미가 다르다. 대표 PNU를 바꾸면 기존 지번 geocode와 외부 조인의 의미가 조용히 바뀐다.
- daily `LNBR`는 insert/delete movement code를 포함하므로 full snapshot과 같은 테이블에 delta를 적용할 수 있다.
- 별도 테이블을 두면 지번 검색 확장, 디버그 표시, 정합성 검증을 단계적으로 붙일 수 있고, 현행 `mv_geocode_target`의 unique 제약을 깨지 않는다.

## 결과

- T-029는 DDL/loader를 바로 만들지 않고 결정과 실제 파일 테스트만 남긴다.
- T-038에서 `tl_juso_parcel_link` DDL/Alembic, full snapshot loader, daily LNBR delta loader를 구현했다.
- T-028 `daily_juso_delta`는 MST 전용으로 남기고, 같은 ZIP의 LNBR은 T-038 `juso_parcel_link_delta`로 별도 적용한다. 이 분리는 MST와 보조 지번 delta의 실패/재시도 단위를 분리하기 위한 것이다.

## 남은 위험

- `tl_juso_parcel_link`를 지번 검색에 바로 연결하면 한 건물에 여러 지번이 매칭되며 랭킹/중복 제거 정책이 필요하다.
- `bd_mgt_sn` 길이가 원천별로 25/26자리 혼재할 가능성은 T-027 SHP에서 이미 확인했다. `jibun_rnaddrkor_*`와 `rnaddrkor_*` 사이에서는 서울 샘플 기준 모두 매칭됐지만, 전국 loader 구현 전 다시 전수 확인한다.
