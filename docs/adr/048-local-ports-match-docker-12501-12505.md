# ADR-048: 로컬 API/UI 포트는 Docker 실행과 같은 12501/12505를 사용한다

- 상태: accepted
- 날짜: 2026-06-13
- 결정자: 사용자 요청, codex

## 컨텍스트

ADR-046은 로컬 단독 실행 포트를 API `12201`, UI `12205`로 정했지만, `kor-travel-docker-manager`와 Docker 실행 관측 기준은 이미 `kor-travel-geo-api:12501`, `kor-travel-geo-ui:12505`를 scrape target으로 사용하고 있었다. 같은 PC에서 Grafana가 host `12205`를 사용하면 로컬 UI `12205`와도 충돌한다. 사용자는 로컬 단독 실행 포트도 Docker와 동일하게 맞추라고 지시했다.

## 결정

1. FastAPI 백엔드의 로컬 단독 실행, Docker host port, Docker container port 기본값은 모두 `12501`이다.
2. `kor-travel-geo-ui`의 로컬 단독 실행, Docker host port, Docker container port 기본값은 모두 `12505`이다.
3. UI proxy 기본 `KTG_API_INTERNAL_URL`은 `http://localhost:12501`이다.
4. Playwright 기본 `PLAYWRIGHT_BASE_URL`은 `http://127.0.0.1:12505`이다.
5. `kor-travel-docker-manager`의 Grafana host `12205`는 그대로 두고, 이 저장소의 UI는 `12505`로 띄워 포트 충돌을 피한다.
6. 이 저장소가 참조하는 주변 서비스 포트도 `kor-travel-docker-manager`를 source of truth로 삼는다. PostgreSQL은 `5432`, RustFS API/console은 `12101`/`12105`, Grafana/cAdvisor/Prometheus는 `12205`/`12301`/`12401`, concierge는 `12601`/`12602`/`12605`, map은 `12701`/`12702`/`12705`, Pinvi는 `12801`/`12805`, manager 자체는 `12901`/`12905`다.
7. 과거 작업 로그와 성능 측정 문서의 `12201`/`12205` 및 이전 RustFS `9003`/`9004`는 당시 재현 정보로 남길 수 있지만, 현재 실행 절차 문서와 기본값은 manager 기준 포트만 사용한다.

## 근거

- 단독 실행과 Docker 실행 포트가 같으면 API smoke, UI e2e, Prometheus scrape target을 같은 주소 체계로 검증할 수 있다.
- Grafana `12205`와 UI `12505`를 분리하면 운영 관측 스택과 디버그 UI를 같은 PC에서 동시에 띄울 수 있다.
- API/UI가 같은 `1250x` 대역을 쓰면 이 저장소의 애플리케이션 표면을 다른 프로젝트 포트와 구분하기 쉽다.

## 결과

- `scripts/docker_app.sh`, `scripts/deploy_app.py`, API/UI Dockerfile, UI proxy, Playwright 설정, benchmark 기본 URL, README와 현재 운영 문서가 `12501`/`12505`를 따른다.
- `.env.example`의 Prometheus 예시는 로컬 단독 실행과 manager compose 모두 `12501`/`12505` 기준이다.
- `docs/ports.md`는 주변 서비스 포트 matrix를 `kor-travel-docker-manager` 기준으로 정리한다.
- ADR-046은 superseded 상태로 남기고, 현재 포트 정책은 이 ADR을 따른다.

## 남은 위험

- VWorld 개발 키의 referrer/domain 제한에 예전 `12205`만 등록돼 있으면 지도 타일 호출이 실패할 수 있다. 로컬 개발용 키에는 `localhost:12505`, `127.0.0.1:12505`, WSL e2e IP와 포트 조합을 등록한다.
