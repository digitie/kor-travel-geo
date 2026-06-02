# 로컬 공식 포트

이 문서는 PC/WSL 개발 환경에서 `python-kraddr-geo`가 기본으로 사용하는 로컬 포트를 고정한다. 여러 프로젝트가 같은 장비에서 동시에 떠 있으므로, PostgreSQL 기본 포트 `5432`와 Next.js 기본 포트 `3000`은 이 저장소의 외부 진입점으로 쓰지 않는다.

| 표면 | 공식 host 포트 | 내부 포트 | 비고 |
|------|----------------|-----------|------|
| PostgreSQL + PostGIS | `15434` | `5432` | Docker compose 기본 `KRADDR_GEO_DB_PORT`. DSN은 `postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo` |
| FastAPI 백엔드 | `9001` | `9001` | `uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 9001` |
| `kraddr-geo-ui` | `9002` | `9002` | 브라우저/e2e 기준 URL. Docker는 `-p 9002:9002`, 로컬 dev는 `npm run dev -- --port 9002` |

`3000`은 Next.js의 일반 기본값일 뿐, 이 저장소의 브라우저 진입점이나 Docker 내부 포트로 문서화하지 않는다. Playwright 기본 `PLAYWRIGHT_BASE_URL`도 `http://127.0.0.1:9002`를 사용한다. API `9001`, UI `9002` 포트를 이미 점유한 프로세스나 컨테이너가 있으면 `scripts/docker_app.sh up`이 해당 점유자를 종료하고 새 컨테이너를 올린다.

## 실행 예시

```bash
# DB
KRADDR_GEO_DB_PORT=15434 docker compose up -d db

# 백엔드
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo \
  uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 9001

# API + UI Docker
scripts/docker_app.sh build
scripts/docker_app.sh up

# UI local dev
cd kraddr-geo-ui
KRADDR_GEO_API_INTERNAL_URL=http://localhost:9001 npm run dev -- --port 9002
```

Docker로 띄울 때는 `scripts/docker_app.sh`를 사용한다. 기본값은 Docker bridge network와 host port mapping이며, API 컨테이너는 host gateway를 통해 기존 PostgreSQL `15434`에 연결하고 UI 컨테이너는 Docker network alias `kraddr-geo-api`로 API를 호출한다. 스크립트는 `.env` 또는 `kraddr-geo-ui/.env.local`에서 VWorld 키를 읽어 컨테이너 환경변수로 주입하되, 키 값은 출력하지 않는다. `KRADDR_GEO_API_PORT`/`KRADDR_GEO_UI_PORT`를 명시하지 않는 한 host 포트는 항상 `9001`/`9002`다.

```bash
scripts/docker_app.sh build-ui
scripts/docker_app.sh up-ui
```
