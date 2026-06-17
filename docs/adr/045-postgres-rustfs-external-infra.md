# ADR-045: PostgreSQL과 RustFS는 외부 인프라로 두고 접속 설정만 저장한다

- 상태: accepted
- 날짜: 2026-06-10
- 결정자: 사용자 요청, codex

## 컨텍스트

이 저장소에는 PostgreSQL/PostGIS와 RustFS를 직접 띄우거나 정지·재시작하는 스크립트와 문서가 섞여 있었다. 이제 해당 인프라의 Docker 생명주기는 별도 인프라 관리 프로젝트가 맡고, `kor-travel-geo`는 라이브러리·REST API·관리 UI로서 이미 동작 중인 DB와 bucket에 접속해 사용해야 한다.

## 결정

이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동·정지·재시작하지 않는다. 필요한 것은 `KTG_PG_DSN`과 `KTG_RUSTFS_*` 접속 설정뿐이며, 이 값은 `.env`, 환경변수, 또는 admin UI 설정 파일에 저장해 사용한다.

## 근거

- 인프라 생명주기와 애플리케이션 코드를 분리하면 포트 경합과 중복 컨테이너 제거 위험이 줄어든다.
- 이 저장소의 책임은 주소 지오코딩 라이브러리·API·디버그/관리 UI이지, 공용 DB와 object storage의 운영자가 아니다.
- DB와 bucket 접속 설정만 유지하면 테스트, API, UI는 기존 기능을 유지하면서도 인프라 관리 책임은 외부로 위임할 수 있다.

## 결과(긍정)

- `docker-compose.yml`을 제거하고, `scripts/docker_app.sh`는 API/UI 컨테이너 실행과 접속 설정 주입만 담당한다.
- 문서의 현재 절차는 "이미 동작 중인 DB/bucket에 접속한다"는 원칙으로 단순해진다.

## 결과(부정)

- 단독 clone 환경에서는 PostgreSQL/PostGIS와 RustFS를 먼저 외부에서 준비해야 한다.

## 후속

- (open) 외부 인프라 관리 프로젝트의 구체 명령은 이 저장소에 복제하지 않고, 필요하면 링크 또는 저장소명 수준으로만 안내한다.
