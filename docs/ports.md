# 로컬 접속 설정

이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동·정지·재시작하지 않는다. 애플리케이션은 어딘가에서 이미 잘 동작하는 DB와 bucket에 접속해 사용하며, 이 프로젝트에는 그 접속 설정만 저장한다.

| 설정 | 예시 | 비고 |
|------|------|------|
| `KTG_PG_DSN` | `postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo` | 이미 동작 중인 PostgreSQL/PostGIS |
| `KTG_RUSTFS_ENABLED` | `true` | RustFS bucket을 사용할 때만 활성화 |
| `KTG_RUSTFS_ENDPOINT_URL` | `http://127.0.0.1:12101` | 이미 동작 중인 S3 호환 endpoint. RustFS console은 manager 기준 `12105` |
| `KTG_RUSTFS_BUCKET` | `kor-travel-geo` | 이 프로젝트가 사용할 bucket |
| `KTG_RUSTFS_PREFIX` | `kor-travel-geo` | bucket 내부 project prefix |
| `KTG_RUSTFS_ACCESS_KEY` / `KTG_RUSTFS_SECRET_KEY` | `.env`에 저장 | Git에 커밋하지 않음 |

로컬 FastAPI와 UI는 이 저장소의 애플리케이션 프로세스이므로 다음 포트를 고정값으로 사용한다.

| 표면 | host 포트 | 비고 |
|------|-----------|------|
| FastAPI 백엔드 | `12501` | `uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12501` |
| `kor-travel-geo-ui` | `12505` | `npm run dev -- --port 12505`, Playwright 기본 `PLAYWRIGHT_BASE_URL` |

로컬 단독 실행과 Docker 실행 모두 API/UI를 `12501`/`12505`로 맞춘다. `kor-travel-docker-manager`의 Grafana는 host `12205`를 사용하므로 같은 PC에서 동시에 띄워도 UI 포트와 충돌하지 않는다.

`kor-travel-docker-manager`가 띄우는 공용 인프라와 관측 스택은 별도 애플리케이션이므로 이 저장소에서 직접 구동하지 않는다. 현재 포트 기준은 `kor-travel-docker-manager`의 `docs/ports.md`, `AGENTS.md`, `docker-compose.yml`을 source of truth로 삼는다. 이 저장소에서 해당 서비스를 참조할 때는 다음 host 포트를 사용한다.

| 표면 | host 포트 | compose 내부 대상 | 비고 |
|------|-----------|-------------------|------|
| PostgreSQL/PostGIS | `5432` | `kor-travel-geo-postgres:5432` | 통합 DB. `kor_travel_geo`, `tripmate`, `kor_travel_concierge`, `krtour_map` 등 |
| RustFS S3 API | `12101` | `rustfs:9000` | `KTG_RUSTFS_ENDPOINT_URL`의 host 기준값 |
| RustFS console | `12105` | `rustfs:9001` | object 확인·수동 삭제 등 운영 콘솔 |
| Grafana | `12205` | `grafana:3000` | Prometheus datasource 자동 등록 |
| cAdvisor | `12301` | `cadvisor:8080` | Docker 컨테이너 리소스 exporter |
| Prometheus | `12401` | `prometheus:9090` | `http://127.0.0.1:12401` |
| `kor-travel-geo` API | `12501` | `kor-travel-geo-api:12501` | 로컬 단독 실행과 Docker 실행 동일 |
| `kor-travel-geo-ui` | `12505` | `kor-travel-geo-ui:12505` | 로컬 단독 실행과 Docker 실행 동일 |
| `kor-travel-concierge` API | `12601` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| `kor-travel-concierge` worker/보조 API | `12602` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| `kor-travel-concierge` Web UI | `12605` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| `kor-travel-map` API | `12701` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| `kor-travel-map` worker/보조 API | `12702` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| `kor-travel-map` Web UI | `12705` | manager compose 기준 | 다른 서비스 연동 시 참조 |
| Pinvi API | `12801` | manager compose 기준 | Pinvi 연동 시 참조 |
| Pinvi Web UI | `12805` | manager compose 기준 | Pinvi 연동 시 참조 |
| `kor-travel-docker-manager` API | `12901` | manager backend | 관리 대시보드 backend |
| `kor-travel-docker-manager` Web UI | `12905` | manager frontend | 관리 대시보드 |

Prometheus scrape 대상은 이 저장소의 API `/metrics`와 `kor-travel-geo-ui`의 `/api/metrics`다.

| 표면 | host 포트 | compose 내부 대상 | 비고 |
|------|-----------|-------------------|------|
| `kor-travel-geo` API metrics | `12501` | `kor-travel-geo-api:12501/metrics` | Docker manager compose 기준 scrape target |
| `kor-travel-geo-ui` metrics | `12505` | `kor-travel-geo-ui:12505/api/metrics` | Docker manager compose 기준 scrape target |

```bash
KTG_PG_DSN=postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo \
KTG_RUSTFS_ENABLED=true \
KTG_RUSTFS_ENDPOINT_URL=http://127.0.0.1:12101 \
  uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12501

# API + UI Docker. DB/RustFS는 이미 동작 중인 접속 대상이어야 한다.
scripts/docker_app.sh build
scripts/docker_app.sh up

# UI local dev
cd kor-travel-geo-ui
KTG_API_INTERNAL_URL=http://localhost:12501 npm run dev -- --port 12505
```
