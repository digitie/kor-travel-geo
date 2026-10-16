# Common gRPC 상태 조회 채택

## 범위와 상태

현재 Geo Dagster 구성요소는 Common344d91c0eec4b605e007e61ce248693a729d692d의
기존 dagster/grpc-health extra를 설치한다. API extra는 같은 pin의 core-only Common을
추가하며 Geo 본체만 설치할 때는 Common·gRPC·Dagster를 강제하지 않는다.
원 ad988 상태 조회 채택과 d1aa 복구 센서 채택의 검증 기록은 아래 역사 절에 보존한다.
현재 source의 이미지 빌드·배포·운영 효과는 [bytecode 채택 안내](runbooks/image-health-bytecode.md)의 별도 gate다.

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

초기 상태 조회 채택 단계의 Common73e3ff8b9398e533806d2d1a8435292570169de3 →
ad988a5 비교에서 기존 __init__.py, dagster.py, deadline.py는 byte 동일했다.
현재344까지 dagster.py가 byte 동일하다는 뜻은 아니다. Common35 multi-job retry와
Common36 PID1 leader clock·Common37 빌드 CLI가 후속에 포함됐다. Geo는 새 multi-job
retry를 등록하지 않으며 기존 backup_verify만의 재시도 범위와 native 기본 STOPPED를 유지한다.
http.py, scheduling.py와 상태 조회 모듈은 이후 추가된 API다.
기존 pin에는 http/scheduling이 없었으므로 기존 다섯 파일이 모두 있었다고 기술하지 않는다.
코어 필수 의존성은 추가되지 않고 새 gRPC 의존성은 선택 extra로만 노출된다.

Dagster 및 gRPC 버전의 정본은 기존 constraints-dagster.txt이며 수치를 바꾸지 않는다.
DB 스키마·풀·timeout·기존 job/sensor·주기·GDAL 직렬 빌드·Next worker2와
frontend/NPM pin은 유지한다. 추가 복구 센서의 선택적 등록은 아래 별도 절을 따른다.

정확한 실행 분은 필수가 아니더라도 수집 횟수·발표 계약·coalescing·동시성 경계는 유지해야 한다.
상태 조회 간격 분산이나 주기 변경은 동일 부하의 CPU/wall/RSS와 수집 신선도를 측정한 뒤
별도로 판단한다. 재시작 때 누락 시각을 한꺼번에 실행하는 catch-up 폭주를 만들지 않는다.
현재 변경만으로 CPU나 지연이 개선되었다고 주장하지 않는다.

## 이전 상태 조회 채택 단계(ad988a5)의 검증 결과

- 이전 pin/extra 및 설치본에 신규 회귀를 실행해 2 FAIL을 확인했다.
- 새 Common을 실제 VCS pin으로 격리 venv에 설치한 뒤 새 회귀 8 PASS를 확인했다.
  합성 loopback gRPC의 표준 DagsterApi SERVING/NOT_SERVING, 닫힌 포트,
  선택 grpc 부재, quiet stdout/stderr, Dagster/SQLAlchemy/Geo의 불필요한 import 차단,
  Geo 본체의 Dagster/gRPC 미수입을 검증했다. 실제 운영 서버 호출은 없다.
- 전체 Python 1,907 PASS/141 SKIP, Dagster 구성요소 129 PASS.
  실제 DB를 제공하지 않았으므로 실제 PostgreSQL 회귀의 통과를 주장하지 않는다.
- 전체 Ruff, mypy, 실제 lint-imports entrypoint 통과(계층 계약 1 KEPT).
- frontend 타입 생성·lint·type-check·269 tests·production build 통과.
  빌드 로그에서 기존 worker2를 확인했다. frontend 소스와 NPM pin은 수정하지 않았다.
- 기존 이미지 constraints의 실제 설치 버전 회귀를 유지했다. Dagster 1.13.24와
  선택 gRPC 의존성의 버전 pin을 변경하지 않았다.

새 회귀의 최초 Ruff 길이 오류와 도구 PATH 오류는 보존 후 수정했다.
lint-imports의 초기 python -m 호출은 검사 결과를 내지 않아 통과 근거로 제외하고,
실제 CLI entrypoint를 다시 실행했다. 위 결과는 작성자 로컬 검증이며 독립 적대 리뷰,
실제 DB·운영 UI·ARM64 빌드·배포·성능 비교의 대체 증거가 아니다.


## 선택적 native incarnation 복구 센서

Dagster 패키지는 Common의 복구 센서도 제공한다. 운영에서 실제 Geo
RepositoryOrigin의 ID를 조회해 KTG_DAGSTER_NATIVE_RECOVERY_REPOSITORY_ORIGIN_ID로
명시한 경우에만 geo_native_incarnation_recovery를 등록하며, 기본 상태는 STOPPED다.
값은 정확히 소문자 16진수 40자여야 한다. 값이 없거나 공백뿐이면 등록하지 않는다.
잘못된 명시값은 값을 노출하지 않는 경고만 남기고 센서를 등록하지 않아 기존
job·schedule·sensor 로딩을 보존한다. ID를 호스트명으로 재구성하거나 추측하지 않는다.
배포자가 실제 location 이름도 KTG_DAGSTER_REPOSITORY_LOCATION_NAME과 일치시켜야 한다.

센서를 켜기 전 해당 이미지에 Common의 모듈이 설치되었는지와 실제 컨테이너의
private PID namespace·PID1 시작 anchor·NTP 신뢰 조건을 확인한다. 이 조건은 로컬
소스 회귀만으로 운영에서 충족되었다고 볼 수 없다. 센서는 정확한 DefaultRunLauncher와
저장된 origin·전송 태그가 확인되는 이전 incarnation의 STARTED 실행만 대상으로 한다.
현재 incarnation 실행, 외부 launcher, origin/태그/시계가 불확실한 실행은 보류한다.


활성화 전제의 정본은 [고정 Common344d91c 가이드 §15](https://github.com/digitie/kor-travel-common/blob/344d91c0eec4b605e007e61ce248693a729d692d/docs/runbooks/dagster-adoption.md#15-컨테이너-재시작-뒤-native-실행-정산)다.
해당 exact gRPC origin은 단일 code-server가 독점 소유해야 하며 구/신 동시 생존,
rolling/blue-green overlap·proxy/LB의 다중 서버 분기는 지원하지 않는다.
private PID namespace와 origin 일치만으로 구 worker 사망을 증명하지 않는다.
실제 serial 교체에서 구 init/worker의 PID·start ticks 및 구 cgroup 비어 있음/소멸을
대조하고 PID/cgroup 경로 재사용과 구분한 물리 소멸 증거가 필요하다.
이 전제/물리 소멸이 UNKNOWN이면 기본 STOPPED를 유지하고 활성화하지 않는다.
센서 자체가 구 namespace worker나 routing의 부재를 증명하지 않는다.

이 센서는 native 실행을 실패로 정산하며 자동 재실행을 만들지 않는다. 기존
geo_infrastructure_retry_backup_verify만 멱등 backup_verify의 인프라 실패를 한 번
재시도한다. 다른 job의 재시도 범위·예산·동시성·예약·기본 상태는 바꾸지 않는다.
공식 실패 보고 API의 마지막 상태 재조회와 기록 사이에는 원자 CAS가 없으므로 외부
수동 조작 경쟁을 완전히 막지 못한다. 태그가 없는 옛 실행은 수동 정산이 필요할 수 있다.
code location 자체가 로드되지 않거나 같은 incarnation의 worker가 멈춘 경우까지
복구하지 않으며, 순수 live 상태 조회로 전환할 모든 선행 조건이 완료되었다는 뜻도 아니다.

이번 변경은 소스 채택이다. 실제 origin 환경 설정·센서 활성화·이미지 설치·운영 orphan
복구·live E2E와 성능 검증은 별도이며 이 문서의 로컬 시험 결과로 대체하지 않는다.

후속 d1aa4bb 채택은 별도 실제 VCS 설치 환경에서 Dagster 전체 148 PASS로 검증했다.
처음 core 미설치 환경의 설치 경계 시험 1 FAIL/147 PASS와, 빌드 산출물을 포함한
Ruff 실행 오류는 보존하고 환경을 교정했다. DB 또는 운영 시험으로 집계하지 않는다.
