# Geo580 interval 독립 FULL6 검토

판정 SOURCE_PASS / 열린 P0·P1·P2 없음.

- 대상 2fc60bbec1869696a223458df525c2257ece7934 / 기준 ed8b2b116f29e36c8a1e6b09df467ca0489aa563
- 공개 immutable Git object 6파일 전체 diff·관련 API HEALTHCHECK/CLI와 배포 안내를 직접 확인했다.
- API Dockerfile은 interval10→30s 한 곳 외 byte동일. 기존 포트 fallback/exec/4초 내부예산,
  Docker5초/12회/시작30초가 보존된다.
- override는 정확 API/CS/UI 3서비스의 healthcheck.interval30/90/30s만 포함한다.
  fixture 전체 모델 병합에서 다른 모든 필드가 동일했고 임의 test·interval 변형6개를 거절했다.
- 새 실제 test 함수의 기본/사용자 포트2조건 PASS(각 종료0/1 전파). 같은 새 함수를 원Dockerfile에
  적용하면 interval assertion에서 실제 RED. 원소스와 테스트를 수정하지 않았다.
- docs3개는 감지 지연과 실제 적용/측정의 별도 gate를 명시한다. 업무 센서·grace·provider·DB·
  복구 정책·점검 timeout/retry를 바꾸지 않고 전체 CPU 개선을 입증했다고 주장하지 않는다.

실행범위: immutable object 추출/파싱/자체 메모리 병합/가짜 python 명령. SDK·실제 HTTP·PG·
Docker·SSH·운영·이미지빌드·타인의 파일 변경은 0이다. 저자의 full1915/실제Compose/CI 수치를
독립 실행 성과에 합산하지 않았다. 운영 정본 서비스와 병합 순서는 실제 적용 단계에서 재검증해야 한다.
공개 source-only SHA 목록과 자체 결과는 같은 prefix의 safe.json에 고정했다.
