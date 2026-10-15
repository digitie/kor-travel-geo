# Common gRPC 상태 조회 채택

## 범위와 상태

Geo Dagster 구성요소가 Common ad988a5dac252d710d41f9937b6d567c5d3398ae의
선택 의존성 grpc-health를 설치하도록 준비한다. Geo 본체/API에는 gRPC나 Dagster
의존성을 새로 강제하지 않는다. 배포와 운영 효과 검증은 아직 수행하지 않았다.

Geo 저장소에는 code-server healthcheck 선언이 없다. 실제 선언의 소유자는
Manager Compose이며, Manager #486에서 준비한 exec 명령은 다음과 같다.

~~~text
python -m kortravelcommon.grpc_health 12503 --check live
~~~

소비 이미지에 모듈과 선택 의존성이 설치된 것을 확인한 후 Manager 선언을 적용한다.
이 문서는 컨테이너 교체나 수집 실행을 수행하지 않는다. 기존 이미지의 모듈 설치 여부를
새 소스의 선언만으로 통과 판정하지 않는다.

## 상태 조회와 실행 복구의 경계

live는 loopback의 표준 DagsterApi Health Check가 SERVING인지 확인한다.
정의 로딩, 저장소 준비, DB, 활성 worker, sensor의 실행 상태까지 보장하지 않는다.
정의 readiness가 필요한 별도 호출은 ready --repository <이름>을 사용하되
Docker healthcheck에 run 상태 변경이나 복구 부작용을 넣지 않는다.

Common CLI는 quiet 종료 코드 0(성공)/1(조회 실패)/2(인수 오류)를 사용한다.
기본 4초는 Python 시작 시간을 별도로 제한하는 실시간 보장이 아니라 내부 호출의 단일
논리 예산이다. HTTP proxy와 자동 gRPC retry는 비활성화된다.
이 조회는 Dagster/SQLAlchemy/애플리케이션 import, DB 쓰기, subprocess,
PID 종료 또는 orphan reaper를 수행하지 않는다.

기존 run monitoring, 원점·incarnation을 확인하는 실패 재시도 정책은 별도 책임으로 유지한다.
live 성공을 실행 정지 복구 성공으로 확대하지 않는다. unhealthy 자체가 Docker의
자동 재시작을 의미하지 않는다.

## 기존 계약과 설정 보존

기존 Common pin 73e3ff8b9398e533806d2d1a8435292570169de3에서 새 pin으로
비교한 기존 __init__.py, dagster.py, deadline.py는 byte 동일하다.
http.py, scheduling.py, 두 health 모듈은 이후 추가된 API다.
기존 pin에는 http/scheduling이 없었으므로 기존 다섯 파일이 모두 있었다고 기술하지 않는다.
코어 필수 의존성은 추가되지 않고 새 gRPC 의존성은 선택 extra로만 노출된다.

Dagster 및 gRPC 버전의 정본은 기존 constraints-dagster.txt이며 수치를 바꾸지 않는다.
DB 스키마·풀·timeout·job/sensor·주기·복구 구성·GDAL 직렬 빌드·Next worker2와
frontend/NPM pin은 이번 작업의 변경 대상이 아니다.

정확한 실행 분은 필수가 아니더라도 수집 횟수·발표 계약·coalescing·동시성 경계는 유지해야 한다.
상태 조회 간격 분산이나 주기 변경은 동일 부하의 CPU/wall/RSS와 수집 신선도를 측정한 뒤
별도로 판단한다. 재시작 때 누락 시각을 한꺼번에 실행하는 catch-up 폭주를 만들지 않는다.
현재 변경만으로 CPU나 지연이 개선되었다고 주장하지 않는다.

## 검증 계획

선언의 정확 pin/extra 및 API 본체의 선택 의존성 경계를 회귀로 고정한다.
실제 설치된 Common을 사용한 격리 subprocess에서 무거운 import 금지,
합성 loopback SERVING/비정상 응답·닫힌 포트·quiet CLI를 확인한다.
회귀가 이전 선언을 거절하는 RED와 새 선언을 허용하는 GREEN을 모두 보존한다.
전체 Python 정적/회귀와 frontend gate 결과는 실행 후 이 문서에 기록한다.
실제 DB·운영 UI·ARM64 빌드·배포·성능 비교는 후속이다.
