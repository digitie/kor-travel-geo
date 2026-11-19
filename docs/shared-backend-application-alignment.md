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

asyncpg는 사용하지 않아 추가하지 않는다. Dagster family 1.13.24·dagster-postgres 0.29.24·psycopg2-binary 2.9.13·psycopg-pool 3.3.3과 grpc/protobuf constraints는 유지한다. 공용 호스트의 daemon-pool SQLAlchemy 2.0.54는 별도 설치 profile이다. Constraints는 설치 요청이나 실제 설치본이 아니며, API·CS가 선택한 extras에 따라 패키지 존재 여부도 다르다.

Common Python은 API와 CS 모두 실제 병합 `67efe2e546ecef41e54a866bf4862d608ace343d`를 사용한다. Python package tree는 `87951f9c50bf99dfcba40a8b16a2a476f2e77118`이다. Geo가 쓰는 RecoveryPolicy·has_active_run·infrastructure_retry_sensor AST는 기존 344d와 같고, dagster_recovery/grpc_health/build_bytecode 파일도 동일하다. Deadline은 slots를 생략한 기존 4-slot 경로를 유지한다. 새 stall 기능은 opt-in이며 Geo는 daemon-pool extra를 선택하지 않는다. Frontend Common catalog·producer·tgz·SRI는 별개로 유지한다.

격리 CPython 3.13 환경에서 선택 버전과 Common Git 출처를 실제 설치 확인했다. GDAL은 기존 ABI가 맞는 테스트 binding을 읽기 전용으로 참조했으며 새 컴파일은 없다. Root unit 최초 실행은 2086 PASS와 이전 Common SHA 기대값 1 FAIL이었고, 기대값을 갱신한 뒤 최종 전체 2087 PASS(33.98초)를 확인했다. CS 전체도 157 PASS(7.05초)다. 기존 schedule 테스트 네 곳의 build_schedule_context를 명시적인 with 수명으로 닫아, 뒤 Definitions 조회에 종료된 instance의 weakref가 유출되지 않게 했다. 기존 assertion AST는 모두 보존했다. 최초 실패·단독 성공·상태 전이 진단은 작업 영수증에 남긴다.

Mypy 170파일·import-linter·Ruff·설치 의존성 정합 검사와 OpenAPI byte 동일성 검사가 통과했다. 새 source/image pin 계약은 이전 범위 선언과 잘못된 core 짝을 각각 거부하는 RED/GREEN으로 검증했다. 기존 psycopg-policy job은 frozen Common guard `b566840cb111fa8b1184498aa892b0fd5ce7e5c6`의 `--strict-python-application`과 실제 CS constraints를 사용한다. 이 guard ref는 작성 시점 미병합 후보이며, 소비자 병합 전 producer 실제 병합·main ancestor 확인이 필요하다. Common Python 설치 ref 67efe와 구분한다. CI 순서와 job 이름은 유지한다.

기존 로컬 PG에는 PostGIS가 없었다. 별도 own UUID Geo engine/JSON/rollback/deadline harness는 마지막 DB 정리가 timeout되어 완전한 성공 영수증으로 세지 않았다. 연결 0인 invalid own-test DB만 보존했고 추가 PG 작업은 중단했다. 실제 PostGIS/migration은 기존 CI integration에서 확인한다. 운영 DB DDL·HTTP·SDK·G·수집 제어는 실행하지 않았다. Runtime이 새 source라고 주장하지 않으며 최종 보고서 644는 소유자의 HOLD를 유지한다.
