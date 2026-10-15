# ADR-071: 보조 geometry timeout은 좌표와 분리하고 요청 수명을 따른다

- 상태: accepted
- 날짜: 2026-10-15
- 결정자: 사용자(실패 격리·CPU/메모리 개선·실측 기반 튜닝), Codex

## 컨텍스트

좌표를 먼저 확보한 뒤 선택적 polygon 조회가 timeout되면 전체 v2 응답이 실패했다.
동일 건물의 road/parcel 후보는 같은 변환 SQL을 반복할 수 있었다. 보조 road 후보는 반대로
일반 Exception을 잡아 programming 오류도 성공 응답으로 감췄다.

## 결정

- geometry repository에서 SQLSTATE57014와 driver primary message의 statement timeout을
  함께 확인한 경우만 GeometryTimeoutError로 구별한다. 같은 SQLSTATE의 사용자 취소,
  lock/connect 오류·programming 오류는 그대로 전파한다.
  구조화된 diag.message_primary가 없거나 문자열이 아니면 원 오류를 전파한다.
  DETAIL/CONTEXT가 섞이는 str(orig)는 statement timeout 확인 근거로 사용하지 않는다.
- 이미 유효한 point를 확보한 v2 후보에만 보조 실패를 격리하고
  `geometry_error: {code: "statement_timeout", retryable: true}`를 명시한다. point·주소·confidence는
  보존한다. point가 없거나 primary 조회 자체가 실패하면 기존 오류다. v1 호환 DTO는 바꾸지 않는다.
- building 조회의 모든 실제 인자가 같은 결과/miss/확인된 timeout만 요청 안에서 공유한다.
  다음 요청에서 다시 조회하므로 사용자 재시도가 복구할 수 있고 장기 geometry cache는 없다.
- API의 기존 disconnect cancellation과 BFF signal 전달을 재사용한다. 관리 UI는 취소·unmount·
  새 요청에 이전 결과가 현재 상태를 덮지 않도록 한다. 부분 실패를 경고로 표시하고 자동 재시도하지 않는다.
- checkout+SQL geometry 경계 시간을 유한 kind/outcome histogram으로 관측한다. 주소·ID·원문 오류는
  label에 넣지 않는다. 기존 SQL timer와 구분하며 CPU/lock/I/O 원인으로 해석하지 않는다.

## 근거와 결과

동일 SQL 호출과 보관 객체 수를 줄이고, 보조 timeout이 이미 성공한 좌표를 버리지 않게 한다.
SQLSTATE만으로 statement timeout과 사용자 취소를 구분할 수 없어 message 확인도 필요하다.
서버 메시지가 다른 언어로 제공되는 등 원인이 불명확하면 부분 성공으로 바꾸지 않는다.
HTTP200이어도 geometry가 불완전할 수 있으므로 소비자는 optional geometry_error를 확인한다.

이번 결정은 pool/엔진 수명이나 DB schema/인덱스/timeout 값을 변경하지 않는다. 기존 indexed plan과
성공·실패 실측만으로 CPU/lock/I/O 원인을 단정할 수 없으므로 추가 튜닝은 같은 workload의 비교 측정 뒤에 한다.

## 후속

- 같은 Admin 예제의 배포 전후 비교, 오류/취소/재시도 live UI 확인과 독립 리뷰 두 건을 진행한다.

## 구현 기록

관리 UI는 같은 주소 요약 컴포넌트에서 typed 도형 timeout 경고를 표시한다. geocode 화면은
실행 중 입력을 잠그되 취소 버튼을 제공하며 다음 제출 시 이전 요청을 취소한다. 화면 이탈도
취소하고 요청 버전과 signal을 함께 검사해 늦은 결과·오류·finally를 버린다. 공개 JSON helper의
선택적 signal 인자를 기존 BFF/API 취소 경계에 전달하며 인증·프록시 scope는 바꾸지 않았다.
서버가 disconnect를 처리하기 전 이미 끝낸 작업까지 되돌린다는 의미는 아니다.
