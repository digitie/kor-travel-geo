# Geo580 interval 전용 변경 독립 검토 D

판정 SOURCE_PASS / 열린 P0/P1/P2/P3=0.

- HEAD 2fc60bbec1869696a223458df525c2257ece7934 / base ed8b2b116f29e36c8a1e6b09df467ca0489aa563
- 전체6파일 diff SHA256 0f6aa66064069e7fbdc7f6940c13cb4d6c2cf94dabf9fd00962558ec02d76159
- D는 이전 Geo579 저자이므로 그 기존 제품을 새 독립 리뷰로 합산하지 않는다. root가 작성한580 전체 변경6파일의 실제 수정범위와 기존 호출계약을 읽고 판단했다. peer raw NOT_READ.

API Dockerfile의 유일한 실행 변경은 HEALTHCHECK interval10→30이다. 원 Test/PORT/4초/timeout5/retries12/start30/USER/컴파일 및 모든 나머지 byte는 동일하다. 새 YAML은 정확한 API/CS/UI 세 서비스에 healthcheck.interval30/90/30만 선언한다. image·Test·Env·다른 leaf를 허용하지 않는다. 다른 운영 역할이나 source/pin/수집·recovery clock 변경은 없다.

독립 noDB Python 모형으로 실제 Gitblob의 세 서비스/leaf집합, 원 interval3배, 전체 service merge의 다른 field 불변, API Dockerfile 전체 치환비교, 앱·pin 경로 Gitdiff 공백을 확인했다. 모두 PASS. 테스트 기대값의10→30도 실제 제품변경과 일치한다.

새 YAML은 기존 정본 뒤에 병합해야 하며 원 컨테이너가 저절로 갱신되지는 않는다. 잘못된 service 이름/override 적용 순서는 배포자의 최종 Compose 검증 대상이다. 문서는 실제 적용·상태 점검·실측을 후속으로 구분하고 지연 증가를 명시한다. root의 전체1915P141S/CI 결과는 본인 재실행으로 합산하지 않았다. 본인 Docker/SSH/DB/SDK/운영0, 원본수정0.
