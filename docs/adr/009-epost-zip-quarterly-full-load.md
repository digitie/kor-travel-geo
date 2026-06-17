# ADR-009: 우편번호는 epost OpenAPI(15000302) ZIP을 분기 1회 전량 적재해 로컬 매칭한다

- 상태: accepted
- 날짜: 2026-05-23
- 결정자: human

## 컨텍스트
우편번호 매칭은 본 프로젝트의 핵심 lookup 흐름 중 하나(`docs/architecture/data-model.md`의 4단계 우선순위, `docs/reverse-geocoding.md`의 `zip_at` 분기). 외부에서 활용할 수 있는 OpenAPI는 크게 두 종류다.

- 데이터셋 **`15000302`**: 우정사업본부 우편번호 **다운로드** 서비스. 호출 응답은 ZIP 파일 URL(`fileLocplc`)로, 매칭 결과를 직접 주지 않는다. `downloadKnd ∈ {1=전체, 2=변경분, 3=범위주소, 4=사서함주소}`.
- 데이터셋 **`15056971`**: 우정사업본부 우편번호 **정보조회** 서비스. 키워드/주소로 우편번호를 실시간 lookup.

또한 `15000302`의 `downloadKnd=2`(변경분)를 누적 적용해 점진 갱신할지, `downloadKnd=1`(전체)을 정기적으로 받아 전량 교체할지의 선택지가 있다.

## 결정
우편번호 매칭은 **데이터셋 `15000302`의 `downloadKnd=1`(전체) ZIP을 분기당 1회 받아 로컬 PostgreSQL(`postal_pobox`, `postal_bulk_delivery`)에 TRUNCATE 후 INSERT 하는 방식**으로 운영한다. `downloadKnd=2`(변경분) 누적은 운영하지 않는다. 데이터셋 `15056971`(실시간 lookup)은 본 시점에서 **도입하지 않는다**.

## 근거
- 우편번호 데이터셋은 분기 단위로도 충분히 안정적 — 일/주 단위로 변경분을 추적할 운영 부담이 비용 대비 이득 없음.
- 전량 TRUNCATE→INSERT는 변경분 머지(`MVM_RES_CD` 흐름과 별개)보다 적재 로직이 단순하고 idempotent. T-017(`pobox_loader.py`, `bulk_loader.py`) 구현 비용 절감.
- 매칭은 로컬 DB가 1차이고 외부 API 호출은 폴백/보조(`fallback="api"`, ADR-003 후속). 실시간 lookup API(`15056971`)를 도입하면 라우터에 외부 호출 경로가 또 늘어나며, 응답 형식이 vworld 호환 응답(`x_extension`)과 결합되지 않아 어댑터 비용이 추가된다.
- ADR-005, ADR-006의 적재 운영 모델(GDAL 적재 + 직렬 작업 큐)과 같은 패턴으로 cron 또는 관리 UI(T-015) 트리거 한 줄에 통합 가능.

## 결과(긍정)
- 적재 코드가 단순. `postal_*` 테이블은 분기당 일관성이 보장.
- 외부 API 의존도가 분기당 4회(전체 1 + 보조 3종 중 필요 시) 정도라 쿼터에 여유.
- vworld 호환 응답 구조가 외부 lookup API로 오염되지 않음(ADR-003 유지).

## 결과(부정)
- 분기 내 신규 우편번호(예: 신축 건물의 새 우편번호)는 다음 갱신까지 누락 가능. 운영상 큰 영향은 없지만, 사용자 신고가 들어오면 수동 변경분 적재(`downloadKnd=2`)로 임시 보강하는 절차가 필요할 수 있다.
- 실시간 외부 lookup이 필요한 신규 use-case가 생기면 본 ADR을 뒤집어야 함 — 그때 새 ADR로 재검토.

## 후속
- (open) 적재 cron 스케줄(분기 첫째 주 일요일 02:00 KST 등)을 운영 단계에서 확정. `ktgctl load pobox/bulk` CLI를 systemd timer로 묶는 안이 자연스러움(T-018).
- (open) 사용자 신고 기반 hot-fix(특정 우편번호만 변경분 적재) UI는 `/admin/postal`(T-023)에 가벼운 보조 액션으로 추가 가능.
