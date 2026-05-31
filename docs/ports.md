# 로컬 공식 포트

이 문서는 PC/WSL 개발 환경에서 `python-kraddr-geo`가 기본으로 사용하는 로컬 포트를 고정한다. 여러 프로젝트가 같은 장비에서 동시에 떠 있으므로, PostgreSQL 기본 포트 `5432`와 Next.js 기본 포트 `3000`은 이 저장소의 외부 진입점으로 쓰지 않는다.

| 표면 | 공식 host 포트 | 내부 포트 | 비고 |
|------|----------------|-----------|------|
| PostgreSQL + PostGIS | `15434` | `5432` | Docker compose 기본 `KRADDR_GEO_DB_PORT`. DSN은 `postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo` |
| FastAPI 백엔드 | `8000` | `8000` | `uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 8000` |
| `kraddr-geo-ui` | `13088` | `3000` | 브라우저/e2e 기준 URL. Docker는 `-p 13088:3000`, 로컬 dev는 `npm run dev -- --port 13088` |

`3000`은 Next.js 프로세스의 내부 기본값일 뿐, 이 저장소의 브라우저 진입점으로 문서화하지 않는다. Playwright 기본 `PLAYWRIGHT_BASE_URL`도 `http://127.0.0.1:13088`을 사용한다.

## 실행 예시

```bash
# DB
KRADDR_GEO_DB_PORT=15434 docker compose up -d db

# 백엔드
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo \
  uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 8000

# UI
cd kraddr-geo-ui
KRADDR_GEO_API_INTERNAL_URL=http://localhost:8000 npm run dev -- --port 13088
```

Docker UI로 띄울 때는 백엔드를 host gateway로 연결한다.

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e KRADDR_GEO_API_INTERNAL_URL=http://host.docker.internal:8000 \
  -e NEXT_PUBLIC_API_BASE_URL=/api/proxy \
  -p 13088:3000 \
  kraddr-geo-ui:debug-v2
```
