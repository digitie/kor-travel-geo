# addr-kr

`addr-kr`은 도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS에 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**다. vworld OpenAPI와 호환되는 응답 구조를 유지하면서 자체 확장(`x_extension`)을 더한다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 [`addr-kr-ui`](docs/frontend-package.md)로 운영한다.

> **현재 상태**: master 브랜치는 신규 사양 문서만 포함하며 코드 구현은 아직 시작 전이다. 이전 SpatiaLite 기반 구현(`kraddr.geo`)은 `v1` 브랜치에 보존되어 있다(ADR-001).

## 문서 언어

이 저장소의 Markdown/RST 문서는 한국어로 작성한다. 공식 API 필드명, 코드 식별자, 명령어, URL, 패키지명처럼 그대로 보존해야 하는 값만 원문을 유지한다.

## 빠른 시작 (구현 후 사용 예정)

```bash
# 의존성
uv venv && uv pip install -e ".[api,loaders,dev]"
cp .env.example .env && $EDITOR .env       # ADDR_KR_PG_DSN 채우기

# PostgreSQL + PostGIS (Docker 권장)
docker compose up -d postgres              # postgis/postgis:16-3.4

# 스키마 적용
alembic upgrade head

# 전국 적재 (시도별 ZIP 또는 폴더가 섞여 있어도 OK)
addr-kr load all-sidos /data/jusoMap/202605 --mode full \
    --pg-conn "host=localhost dbname=addr_kr user=addr password=..."

# 서비스 기동
uvicorn addr_kr.api.app:app --reload --port 8000
```

프론트엔드(별도 저장소 또는 디렉토리):

```bash
cd addr-kr-ui
cp .env.local.example .env.local && $EDITOR .env.local   # KAKAO JS 키 등
npm ci
npm run gen:types        # 백엔드 openapi.json → 타입·Zod 자동 생성
npm run dev              # http://localhost:3000
```

## 진입점

- **Python 라이브러리**: `from addr_kr import AsyncAddressClient` — asyncio 컨텍스트 매니저
- **REST API**: `uvicorn addr_kr.api.app:app` — Swagger UI는 `http://localhost:8000/v1/docs`
- **CLI**: `addr-kr --help` — `load`, `refresh`, `validate`, `healthz`
- **디버그/관리 UI**: `addr-kr-ui` (별도 Node.js 패키지) — 내부망 전용 (ADR-013)

## 라이브러리 사용 예

```python
import asyncio
from addr_kr import AsyncAddressClient

async def main() -> None:
    async with AsyncAddressClient() as client:    # .env에서 DSN 자동 로드
        r = await client.geocode("서울특별시 강남구 테헤란로 152")
        if r.status == "OK":
            print(r.result.point)            # Point(x=127.028..., y=37.500...)
            print(r.refined.text)            # '서울특별시 강남구 테헤란로 152'
            print(r.x_extension.bd_mgt_sn)   # '11680101...'

        rr = await client.reverse_geocode(127.028601, 37.500344, type="both")
        for item in rr.result:
            print(item.type, item.text, item.zipcode)

asyncio.run(main())
```

동기 컨텍스트에서 호출하려면 호출자가 `asyncio.run`으로 감싼다(ADR-002).

## 디렉토리 한 줄 설명

| 경로 | 역할 |
|------|------|
| `src/addr_kr/dto/` | pydantic v2 입력/출력 (DB·FastAPI 의존성 없음) |
| `src/addr_kr/core/` | DB 무관 비즈니스 로직. Protocol에만 의존 |
| `src/addr_kr/infra/` | DB 어댑터 (SQLAlchemy 2 async + raw SQL) |
| `src/addr_kr/client.py` | `AsyncAddressClient` — 라이브러리 진입점 |
| `src/addr_kr/api/` | FastAPI 라우터 |
| `src/addr_kr/loaders/` | 시도 SHP, 사서함, 다량배달처, 증분 적재 |
| `src/addr_kr/cli/` | typer CLI |
| `alembic/`, `sql/` | 스키마 마이그레이션과 DDL |
| `tests/` | unit (Fake repo) / integration (testcontainers) / e2e |
| `docs/` | 사양·결정·작업 기록 |

## 핵심 결정

| ADR | 결정 |
|-----|------|
| ADR-001 | PostgreSQL + PostGIS를 1차 저장소로 채택 (SpatiaLite/SQLite 폐기) |
| ADR-002 | 라이브러리 API는 async-only |
| ADR-003 | 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 |
| ADR-004 | ORM 위에 raw SQL Repository |
| ADR-005 | 로더는 GDAL Python binding (ogr2ogr subprocess 폐기) |
| ADR-006 | 적재 작업은 단일 인스턴스의 in-process 큐로 직렬 처리 |
| ADR-013 | 프론트엔드 UI는 내부망 전용, 애플리케이션 인증 없음 |

전체 ADR 본문은 [`docs/decisions.md`](docs/decisions.md).

## 외부 REST API

`addr-kr`은 로컬 DB가 1차이고 외부 API는 폴백/보조 용도다. 발급 절차·환경변수·호출 정책은 [`docs/external-apis.md`](docs/external-apis.md) 참조.

| 서비스 | 환경변수 | 용도 |
|--------|---------|------|
| vworld | `ADDR_KR_VWORLD_API_KEY` | 지오코딩 폴백, 통합 검색 |
| juso 검색 | `ADDR_KR_JUSO_API_KEY` | 도로명/지번 검색 폴백 |
| juso 좌표 | `ADDR_KR_JUSO_COORD_API_KEY` (없으면 위 키 재사용) | 좌표 변환 폴백 |
| epost | `ADDR_KR_EPOST_API_KEY` | 사서함·다량배달처 ZIP 자동 다운로드 |
| Kakao Maps JS | `NEXT_PUBLIC_KAKAO_JS_KEY` (frontend) | 디버그/관리 UI 지도 |

## 기여

1. **반드시** [`SKILL.md`](SKILL.md) 먼저 읽기
2. [`docs/tasks.md`](docs/tasks.md)에서 항목 선택, [`docs/resume.md`](docs/resume.md)로 현재 상태 확인
3. 작업 후 [`docs/journal.md`](docs/journal.md) 엔트리 추가 + `docs/resume.md` 진척도 갱신
4. 결정이 있다면 [`docs/decisions.md`](docs/decisions.md)에 ADR 추가
5. 사용자 가시 변경이면 [`CHANGELOG.md`](CHANGELOG.md) 갱신

## 문서 지도

- [`SKILL.md`](SKILL.md) — 에이전트 작업 매뉴얼 (DO NOT, 디렉토리 지도, 자주 묻는 작업)
- [`docs/architecture.md`](docs/architecture.md) — 두 패키지의 관계, 계층, 데이터 흐름
- [`docs/decisions.md`](docs/decisions.md) — ADR 누적
- [`docs/data-model.md`](docs/data-model.md) — PostgreSQL + PostGIS 스키마 reference
- [`docs/backend-package.md`](docs/backend-package.md) — `addr-kr` 백엔드 사양서
- [`docs/frontend-package.md`](docs/frontend-package.md) — `addr-kr-ui` 프론트엔드 사양서
- [`docs/agent-guide.md`](docs/agent-guide.md) — AI 에이전트 작업·문서화 가이드
- [`docs/external-apis.md`](docs/external-apis.md) — vworld/juso/epost/kakao 발급·호출
- [`docs/tasks.md`](docs/tasks.md), [`docs/resume.md`](docs/resume.md), [`docs/journal.md`](docs/journal.md) — 백로그·진척도·작업 일지
- [`docs/address-db-schema.md`](docs/address-db-schema.md), [`docs/geocoding-readiness.md`](docs/geocoding-readiness.md), [`docs/reverse-geocoding.md`](docs/reverse-geocoding.md), [`docs/spatialite-vworld-implementation.md`](docs/spatialite-vworld-implementation.md) — 주제별 요약
- [`docs/reflection-summary.md`](docs/reflection-summary.md) — 사양 첨부파일 반영 내용 요약

## 라이선스

MIT (구현 시작 시 `pyproject.toml`과 `LICENSE`에 반영 예정).
