# 로컬 접속 설정

이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동·정지·재시작하지 않는다. 애플리케이션은 어딘가에서 이미 잘 동작하는 DB와 bucket에 접속해 사용하며, 이 프로젝트에는 그 접속 설정만 저장한다.

| 설정 | 예시 | 비고 |
|------|------|------|
| `KTG_PG_DSN` | `postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo` | 이미 동작 중인 PostgreSQL/PostGIS |
| `KTG_RUSTFS_ENABLED` | `true` | RustFS bucket을 사용할 때만 활성화 |
| `KTG_RUSTFS_ENDPOINT_URL` | `http://127.0.0.1:12101` | 이미 동작 중인 S3 호환 endpoint |
| `KTG_RUSTFS_BUCKET` | `kor-travel-geo` | 이 프로젝트가 사용할 bucket |
| `KTG_RUSTFS_PREFIX` | `kor-travel-geo` | bucket 내부 project prefix |
| `KTG_RUSTFS_ACCESS_KEY` / `KTG_RUSTFS_SECRET_KEY` | `.env`에 저장 | Git에 커밋하지 않음 |

로컬 FastAPI와 UI는 이 저장소의 애플리케이션 프로세스이므로 다음 포트를 고정값으로 사용한다.

| 표면 | host 포트 | 비고 |
|------|-----------|------|
| FastAPI 백엔드 | `12201` | `uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12201` |
| `kor-travel-geo-ui` | `12205` | `npm run dev -- --port 12205`, Playwright 기본 `PLAYWRIGHT_BASE_URL` |

```bash
KTG_PG_DSN=postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo \
KTG_RUSTFS_ENABLED=true \
KTG_RUSTFS_ENDPOINT_URL=http://127.0.0.1:12101 \
  uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12201

# API + UI Docker. DB/RustFS는 이미 동작 중인 접속 대상이어야 한다.
scripts/docker_app.sh build
scripts/docker_app.sh up

# UI local dev
cd kor-travel-geo-ui
KTG_API_INTERNAL_URL=http://localhost:12201 npm run dev -- --port 12205
```
