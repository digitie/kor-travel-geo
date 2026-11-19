# Geo 앱 백엔드 선택 버전 정렬 (2026-11-20)

승인된 선택 버전 가운데 실제 사용하는 축만 root/API 선언과 CS image constraints에 반영한다. 이 표는 선택 시점의 기록이다. 앱·쿼리·DTO·Alembic migration·Docker GDAL 단계·UI 입력은 바꾸지 않는다. 실제 ARM 이미지/native 및 운영 수용은 후속 정상 API·CS 작업의 증거로 확인한다.

| 앱 축 | 선택 버전 | 사용 범위 |
|---|---|---|
| SQLAlchemy | 2.1.9 | API·CS; root asyncio extra 유지 |
| Pydantic / core | 2.14.4 / 2.50.5 | API·CS; 배포 metadata의 core 요구와 image constraint를 함께 검사 |
| pydantic-settings | 2.16.3 | API·CS |
| FastAPI | 0.165.0 | API extra만; CS에 강제 추가하지 않음 |
| Alembic | 1.20.1 | API·CS |
| httpx | 0.28.1 | API·CS |
| uvicorn | 0.54.0 | API standard extra; CS는 기존 dagster-webserver 의존성 |
| psycopg / binary | 3.3.9 / 3.3.9 | 기존 값 유지; 실제 구현 증거는 설치/native 단계에서 별도 확인 |

asyncpg는 사용하지 않아 추가하지 않는다. Dagster family 1.13.24·dagster-postgres 0.29.24·psycopg2-binary 2.9.13·psycopg-pool 3.3.3는 유지한다. gRPC와 전이 패키지의 후속 선택은 아래 공용 profile을 따른다. 공용 호스트의 daemon-pool SQLAlchemy 2.0.54는 별도 설치 profile이다. Constraints는 설치 요청이나 실제 설치본이 아니며, API·CS가 선택한 extras에 따라 패키지 존재 여부도 다르다.

Common Python은 API와 CS 모두 실제 병합 `67efe2e546ecef41e54a866bf4862d608ace343d`를 사용한다. Python package tree는 `87951f9c50bf99dfcba40a8b16a2a476f2e77118`이다. Geo가 쓰는 RecoveryPolicy·has_active_run·infrastructure_retry_sensor AST는 기존 344d와 같고, dagster_recovery/grpc_health/build_bytecode 파일도 동일하다. Deadline은 slots를 생략한 기존 4-slot 경로를 유지한다. 새 stall 기능은 opt-in이며 Geo는 daemon-pool extra를 선택하지 않는다. Frontend Common catalog·producer·tgz·SRI는 별개로 유지한다.

격리 CPython 3.13 환경에서 선택 버전과 Common Git 출처를 실제 설치 확인했다. GDAL은 기존 ABI가 맞는 테스트 binding을 읽기 전용으로 참조했으며 새 컴파일은 없다. Root unit 최초 실행은 2086 PASS와 이전 Common SHA 기대값 1 FAIL이었고, 기대값을 갱신한 뒤 최종 전체 2087 PASS(33.98초)를 확인했다. CS 전체도 157 PASS(7.05초)다. 기존 schedule 테스트 네 곳의 build_schedule_context를 명시적인 with 수명으로 닫아, 뒤 Definitions 조회에 종료된 instance의 weakref가 유출되지 않게 했다. 기존 assertion AST는 모두 보존했다. 최초 실패·단독 성공·상태 전이 진단은 작업 영수증에 남긴다.

Mypy 170파일·import-linter·Ruff·설치 의존성 정합 검사와 OpenAPI byte 동일성 검사가 통과했다. 새 source/image pin 계약은 이전 범위 선언과 잘못된 core 짝을 각각 거부하는 RED/GREEN으로 검증했다. 기존 psycopg-policy job은 Common76 immutable ref 694b814ce625778d31b6aa57b8ae2c8c4f22a752에 --strict-python-application --python-build-tools --python-version 3.12를 전달한다. Common Python 설치 ref 67efe와 frontend catalog d644는 별개로 유지한다. 소비자 병합 전 Common76이 실제 main ancestor인지 확인한다. CI 순서와 job 이름은 유지한다.

기존 로컬 PG에는 PostGIS가 없었다. 별도 own UUID Geo engine/JSON/rollback/deadline harness는 마지막 DB 정리가 timeout되어 완전한 성공 영수증으로 세지 않았다. 연결 0인 invalid own-test DB만 보존했고 추가 PG 작업은 중단했다. 실제 PostGIS/migration은 기존 CI integration에서 확인한다. 운영 DB DDL·HTTP·SDK·G·수집 제어는 실행하지 않았다. Runtime이 새 source라고 주장하지 않으며 최종 보고서 644는 소유자의 HOLD를 유지한다.


## 실제 사용 범위의 공용 profile과 앱 wheel cache 후속

후속 소스는 병합된 cache 변경 649(57fd9dd907e04010e0a0aa6775486823efcaecc0)를 상속하고, docker/constraints-shared-python.txt에 실제 API·CS 설치본과 선언된 개발·빌드 도구가 사용하는 선택 버전 97개를 고정한다. Constraints가 사용하지 않는 패키지를 새 의존성으로 설치하지는 않는다. API·CS의 실제 앱 설치, CS 자체 constraints의 포함, 기존 CI 설치가 같은 파일을 소비한다. 소스 빌드 도구는 setuptools 84.2.1 / wheel 0.48.0, 최종 이미지 pip은 26.3이다. AWS boto3/botocore는 1.44.7, grpcio는 1.85.3, grpcio-health-checking은 1.81.2를 선택한다. python-dateutil은 boto 계열과 호환되는 2.9.0.post0으로 정렬한다.

앱 wheel cache는 기존 정상 BuildKit mount 안에서 Python SOABI·GNU libc·gdal-config --version별 하위 경로로 분리한다. Fiona wheel 파일명에 libgdal soname이 없으므로 GDAL 버전이 다른 wheel을 공유하지 않는다. 원래 GDAL wheel 단계와 native import/version 검사는 보존한다. CS의 최종 pip 도구만 순수 Python 전용 cache를 사용한다. API·CS 앱 설치 뒤 pip check를 실행한다. 소스만 바뀌었을 때 GDAL/Fiona를 매번 재컴파일하는 문제의 수정이며, 임의 wheel 재포장·설치 overlay·cache prune은 없다.

로컬 판별 테스트는 이전 Dockerfile/설치 경로에서 실패한 후 수정본에서 통과했다. 실제 공개 pip의 --dry-run --no-index로 올바른 grpcio 후보와 이전 버전 후보를 두 constraints 경로에서 각각 구분했다. ARM CPython3.12용 선택 97개 union의 wheel metadata 해석은 105개 closure로 성공했다. 이는 설치·전체 GDAL closure·ARM 이미지/native 검증을 대신하지 않는다. 기존 설치 버전 parametrized 검사는 이전 로컬 환경에서 제외했으며 새 CI/native에서 확인해야 한다.

운영 31ad4의 정상 API·CS 이미지와 공식 SDK 적용은 이미 수용되었다. 일상 적용 후 전체 설치 맵은 API 62개, CS 103개였고 UI는 기존 5c159 이미지 3c7e를 그대로 유지했다. 이 후속 소스를 적용하기 전의 전체 맵을 Common76에 대조하면 API python-dateutil 한 항목과 CS boto3/botocore/grpcio/grpcio-health-checking/pip 다섯 항목이 다르다. 따라서 운영이 이 97개 profile과 모두 일치한다고 주장하지 않는다. 미래 정상 빌드에서 실제 API→CS Fiona cache 재사용과 전체 설치 버전 readback을 확인한다. cache만의 중간 이미지 빌드는 하지 않는다. 최종 보고서 644는 소유자의 HOLD를 유지한다.
