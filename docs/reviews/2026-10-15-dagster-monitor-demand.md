# Dagster 관리 화면의 조회 부하 개선

## 변경 범위

기존 Common `DagsterOperations`의 controlled selection과 상세 renderer를 그대로 사용한다.
첫 실행을 자동 선택하지 않으므로 첫 화면의 run 상세 요청은 1회에서 0회가 된다.
사용자가 실행을 선택하면 해당 상세를 조회하고 선택 변경·이탈은 기존 TanStack Query
signal을 취소한다. 내장 콘솔은 명시적으로 열 때만 iframe을 만들고 닫을 때 제거한다.

상세 응답의 run 상태가 `SUCCESS`, `FAILURE`, `CANCELED`이면 자동 polling을 멈춘다.
활성·미확인 상세는 기존 15초 주기를 유지하며 수동 갱신은 종료 상태에서도 가능하다.
요약·실패 목록은 기존 30초 주기를 유지한다. 세 조회 모두 즉시 자동 retry를 하지 않고
다음 주기 또는 사용자 갱신으로 복구한다. 상태 조회 장애를 성공으로 바꾸지 않는다.
기존 클라이언트·서버 deadline, 상세/이력 건수, 인증·실패 확인 write 경계는 변경하지 않는다.

## 검증

- 기존 소스에 새 회귀: 7 FAIL/7 PASS. 종료 상태 3종의 반복 요청, 종료 전환 후 반복,
  오류 직후 retry, iframe 자동 생성을 재현했다.
- 첫 run 선택 검증에 effect 대기를 추가한 독립 OLD 재현: 1 FAIL/3 PASS.
- 변경 후 관련 14 PASS. 명시 선택, terminal polling 중단·수동 갱신, 활성→종료 전환,
  오류→다음 주기 복구, 선택 변경 signal 취소, 콘솔 열기/닫기·sandbox를 포함한다.
- 이 atom만 반영한 frontend 전체 261 PASS, type/lint PASS. 별도 지오코딩 UI와 통합한
  최종 전체 검증과 실제 배포 후 live E2E는 이 기록의 PASS에 포함하지 않는다.
- React hook test helper 이름 lint 오류는 helper를 컴포넌트 이름으로 고쳤다. 제품 오류가 아니다.

## 실제 상태 조회 분석과 미채택 대안

변경 전 실제 UI 상태 조회에서 HTTP 200이나 `status=unavailable`인 응답을 약 10.9초에
관찰했다. 상태가 없는 응답을 정상으로 처리하거나 live assertion을 완화하지 않았다.
전체 query는 repository·최근/활성 실행과 schedule/sensor의 최근 tick 및 예정 시각을 포함한다.

동일 서버·scope·이력 3건·최근 실행 10건으로 status 필터 유무를 교차 순서로 3쌍 비교했다.

| query | 각 요청 경과 ms | 중앙값 ms |
| --- | --- | --- |
| 기존 exhaustive status 필터 | 7,487.77 / 5,285.62 / 3,235.69 | 5,285.62 |
| 필터 생략 bulk 경로 | 3,818.41 / 4,365.33 / 2,626.54 | 3,818.41 |

6회 모두 동일 5 instigator·6 tick의 전체 이력 내용 hash가 같았고 HTTP 200·GraphQL 오류 0이었다.
그러나 배경 부하가 변하는 소표본이며 p95·CPU 개선 실측이 아니다. Dagster의 bulk 구현은
전체 selector 이력에 `rank()`를 적용하며 timestamp 동률이면 요청 limit보다 많은 행을
반환할 수도 있다. 오래 쌓이는 이력의 CPU·메모리 비용을 악화시킬 수 있어 이 변경은
채택하지 않았다. 기존 제한 조회 및 그 회귀는 그대로 유지했다.

## 남은 확인

브라우저 요청 감소를 서버 CPU 감소율로 환산하지 않는다. 이미 시작된 서버 GraphQL 계산의
강제 중단도 보장하지 않는다. 최종 통합 소스의 두 독립 리뷰, 실제 UI와 관리자 예제의
배포 후 비교, Dagster 부하·실행 복구 확인은 별도 수행한다.
