# 로컬 공식 포트

이 문서는 PC/WSL 개발 환경에서 `python-kraddr-geo`가 기본으로 사용하는 로컬 포트를 고정한다. 여러 프로젝트가 같은 장비에서 동시에 떠 있으므로, PostgreSQL 기본 포트 `5432`와 Next.js 기본 포트 `3000`은 이 저장소의 외부 진입점으로 쓰지 않는다.

| 표면 | 공식 host 포트 | 내부 포트 | 비고 |
|------|----------------|-----------|------|
| PostgreSQL + PostGIS | `15434` | `5432` | Docker compose 기본 `KRADDR_GEO_DB_PORT`. DSN은 `postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo` |
| FastAPI 백엔드 | `9001` | `9001` | `uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 9001` |
| `kraddr-geo-ui` | `9002` | `9002` | 브라우저/e2e 기준 URL. Docker는 `-p 9002:9002`, 로컬 dev는 `npm run dev -- --port 9002` |
| RustFS S3 API | `9003` | `9003` | 업로드 object storage API. Docker network endpoint는 `http://kraddr-geo-rustfs:9003` |
| RustFS console | `9004` | `9004` | 운영자 웹 콘솔. 내부망 또는 로컬에서만 접근 |

`3000`은 Next.js의 일반 기본값일 뿐, 이 저장소의 브라우저 진입점이나 Docker 내부 포트로 문서화하지 않는다. Playwright 기본 `PLAYWRIGHT_BASE_URL`도 `http://127.0.0.1:9002`를 사용한다. API `9001`, UI `9002`, RustFS `9003`/`9004` 포트를 이미 점유한 프로세스나 컨테이너가 있으면 `scripts/docker_app.sh up`이 해당 점유자를 종료하고 새 컨테이너를 올린다.

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

Docker로 띄울 때는 `scripts/docker_app.sh`를 사용한다. 기본값은 Docker bridge network와 host port mapping이며, API 컨테이너는 host gateway를 통해 기존 PostgreSQL `15434`에 연결하고 UI 컨테이너는 Docker network alias `kraddr-geo-api`로 API를 호출한다. RustFS는 `kraddr-geo-rustfs` alias로 붙고 API endpoint는 `http://kraddr-geo-rustfs:9003`이다. 스크립트는 `.env` 또는 `kraddr-geo-ui/.env.local`에서 VWorld 키를 읽어 컨테이너 환경변수로 주입하되, 키 값은 출력하지 않는다. `KRADDR_GEO_API_PORT`/`KRADDR_GEO_UI_PORT`/`KRADDR_GEO_RUSTFS_PORT`/`KRADDR_GEO_RUSTFS_CONSOLE_PORT`를 명시하지 않는 한 host 포트는 항상 `9001`/`9002`/`9003`/`9004`다.

이미 `9003`을 publish하는 non-managed RustFS 컨테이너가 있으면 기본 `scripts/docker_app.sh up-rustfs`는 해당 컨테이너를 제거하고 `kraddr-geo-rustfs`를 올린다. 점유자가 Docker Compose 서비스이면 제거 전에 해당 service를 `stop`해서 같은 포트를 즉시 다시 잡지 못하게 한다. 기존 RustFS를 임시 재사용해야 하는 운영자는 `KRADDR_GEO_RUSTFS_REUSE_EXISTING=1`을 명시한다. 이 경우 script는 기존 컨테이너를 `kraddr-geo-net`에 연결하고 API 컨테이너에는 기존 RustFS 컨테이너의 `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`를 주입한다.

```bash
scripts/docker_app.sh build-ui
scripts/docker_app.sh up-ui
```
