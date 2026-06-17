# ADR-010: PNU 토지구분 매핑은 infra 레이어에서 조립한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
법원 등기·토지대장 등 외부 기관 시스템과 조인하려면 19자리 표준 PNU(필지번호)가 필요하다. PNU 11번째 자리(토지구분)는 표준상 `1=일반, 2=산`이지만, 도로명주소 원천(`tl_spbd_buld.mntn_yn`)은 `0=대지, 1=산` 체계라 직접 결합하면 외부 조인 시 조용히 틀린다.

## 결정
- PNU 11번째 자리 매핑: **`mntn_yn='0' → '1'`, `mntn_yn='1' → '2'`**. helper 또는 generated stored column 어느 쪽이든 본 매핑을 그대로 따른다.
- 조립 위치: **`infra/`** (또는 generated column). `core/`는 의미론적 `mntn_yn`만 보관하고 PNU라는 외부 식별자 표준은 저장/조회 계층의 책임으로 분리.
- helper 함수 시그니처: `pnu_from_row(row: dict) -> str` (19자리). 컬럼명 표준은 `docs/architecture/data-model.md` "PNU 조립" 절.

## 근거
- 외부 시스템 조인 use-case가 사양에 진입했으므로 PNU 매핑을 별도 ADR로 박아두면 향후 hardcode 사고를 방지할 수 있다.
- `core/normalize.py`는 입력 문자열을 의미론적으로 해체하는 책임이지 외부 식별자 표준에 맞춰 재조립하는 책임이 아니다 — 계층 책임 분리(ADR-004).
- generated stored column이면 SQL one-liner로 자동 유지되어 적재 변경분이 와도 자연 갱신.

## 결과(긍정)
- 외부 시스템 조인 데이터의 무결성이 매핑 hardcode에 의존하지 않음.
- 라이브러리 사용자가 `bd_mgt_sn`이 아닌 PNU로 외부 조인할 때 안전한 단일 경로 제공.

## 결과(부정)
- generated column 추가 시 마이그레이션 비용(기존 행 백필). 첫 풀로드 단계라 부담은 낮다.
- helper 방식이면 라우터/리포가 호출을 잊을 가능성 — 따라서 generated column 권장.

## 후속
- (open) T-006(DDL) 또는 T-016(reverse/zipcode 코어) 진행 시 generated column 채택 여부 최종 결정. 기본 권장은 generated stored column.
- (open) 외부 시스템(등기·토지대장) 응답 구조와 PNU 자릿수 조합 실데이터 검증.
