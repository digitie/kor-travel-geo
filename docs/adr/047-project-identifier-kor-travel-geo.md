# ADR-047: 프로젝트 식별자는 `kor-travel-geo` 계열로 통일한다

- 상태: accepted
- 날짜: 2026-06-13
- 결정자: 사용자 요청, codex

## 컨텍스트

초기 구현은 여러 공개 표면에서 오래된 주소 라이브러리 이름을 사용했다. 사용자와 에이전트가 동시에 작업하는 상황에서 저장소명, Python import, CLI, 환경변수, DB 이름, RustFS prefix가 서로 다르면 어떤 서비스나 데이터를 가리키는지 즉시 판단하기 어렵다. 사용자는 검색성과 직관성을 위해 배포명 `kor-travel-geo`, Python import `kortravelgeo`, 권장 alias `import kortravelgeo as ktg`, CLI `ktgctl`을 확정했고, PostgreSQL DB 이름과 RustFS에 쓰이는 이름도 함께 바꾸라고 지시했다.

## 결정

1. GitHub 저장소와 Python 배포명은 `kor-travel-geo`로 통일한다.
2. Python import root는 `kortravelgeo`로 통일하고, 문서의 권장 사용 예시는 `import kortravelgeo as ktg`로 쓴다.
3. CLI 명령은 `ktgctl`만 제공한다.
4. 환경변수 prefix는 `KTG_*`만 사용한다.
5. PostgreSQL 기본 DB 이름은 `kor_travel_geo`다.
6. RustFS bucket/prefix 기본값과 Docker image/container/network 이름은 `kor-travel-geo` 계열을 사용한다.
7. API title, UI package, OpenAPI, 문서 URL, GitHub URL 참조도 `kor-travel-geo` 기준으로 맞춘다.
8. Prometheus metric namespace는 `kor_travel_geo_*`, callback/header prefix는 `x-kor-travel-geo-*`를 사용한다.
9. 이전 이름 계열의 package, CLI alias, 환경변수 alias, 단순 전달 facade는 만들지 않는다.

## 근거

- 식별자를 하나의 계열로 맞추면 배포 산출물, 운영 설정, DB, object storage, 문서가 같은 프로젝트를 가리킨다는 점을 이름만으로 확인할 수 있다.
- `ktgctl`은 짧고 shell에서 반복 입력하기 쉬우며, Python alias `ktg`와 의미가 이어진다.
- 이전 환경변수 alias를 남기면 비밀값과 운영 설정이 두 체계로 갈라져 장애 원인 추적이 어려워진다.
- 공개 릴리스 전 breaking rename으로 처리하면 장기 호환 layer 없이 코드 구조를 단순하게 유지할 수 있다.

## 결과

- 패키지 경로, import-linter root, Docker/uvicorn entrypoint, OpenAPI export, benchmark/운영 스크립트가 `kortravelgeo`를 기준으로 동작한다.
- `.env.example`, `Settings`, Docker 실행 스크립트, UI proxy/runtime config가 `KTG_*`를 기준으로 동작한다.
- 기본 DSN은 `postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo`를 사용한다.
- RustFS 기본 bucket/prefix는 `kor-travel-geo`다.
- API 요청 성능 측정은 `kor_travel_geo_api_request_duration_seconds` metric과 `KTG_API_PERFORMANCE_LOGGING_ENABLED` opt-in 로그로 제공한다.

## 남은 위험

- 실제 GitHub repository slug 변경은 코드 PR만으로 완료되지 않는다. merge 직후 repository 관리 작업으로 slug를 바꾸고, 원격 URL과 에이전트 worktree 안내를 확인해야 한다.
- 운영 DB 이름을 실제로 바꾸는 시점에는 기존 연결 문자열, 백업/복원 runbook, 외부 에이전트 `.env`를 같은 배포 창에서 갱신해야 한다.
