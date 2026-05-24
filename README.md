# python-kraddr-geo

GitHub 저장소 이름은 `python-kraddr-geo`, Python 패키지는 `kraddr.geo`다. 도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS에 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**이며, vworld OpenAPI와 호환되는 응답 구조를 유지하면서 자체 확장(`x_extension`)을 더한다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 [`kraddr-geo-ui`](docs/frontend-package.md)로 운영한다.

> **현재 상태**: master 브랜치는 PostgreSQL + PostGIS 기반 재구현의 백엔드 핵심(T-005~T-020)을 포함한다. PR #12에서는 디버그/관리 UI(`kraddr-geo-ui`)와 운영 관측·CI 보강(T-021~T-026)을 추가한다. 이전 SpatiaLite 기반 구현(같은 `kraddr.geo` 패키지)은 `v1` 브랜치에 보존되어 있다(ADR-001).

## 문서 언어

이 저장소의 Markdown/RST 문서는 한국어로 작성한다. 공식 API 필드명, 코드 식별자, 명령어, URL, 패키지명처럼 그대로 보존해야 하는 값만 원문을 유지한다.

## 개발 환경 (PC, WSL)

PC 개발은 **WSL의 ext4 파일시스템** 위에서 진행한다. NTFS 마운트(`/mnt/<drive>/...`) 위에서 직접 `git`/`pip`/`uvicorn`을 실행하지 않는다 — 파일 권한·inotify·심볼릭 링크·대량 I/O 성능에서 모두 손해를 본다.

```
ext4 (개발):  ~/dev/python-kraddr-geo/                  ← 모든 코드/가상환경/테스트 (source of truth)
NTFS (카피본): /mnt/<drive>/projects/python-kraddr-geo/  ← 작업 완료 후 카피, Windows에서 접근
```

- 작업이 완료되면 ext4 → NTFS로 카피하여 Windows에서도 접근 가능하게 둔다.
- **데이터(`data/`)는 NTFS의 프로젝트 디렉토리 아래에 둔다**. 도로명주소 전자지도 ZIP/SHP, 사서함/다량배달처 TXT, 외부 API 캐시 dump 등 대용량 자료는 모두 `data/` 하위에 정리한다.
- 테스트(단위·통합·e2e) 실행 시 데이터 경로는 NTFS의 `data/`를 참조한다. WSL에서는 `/mnt/<drive>/projects/python-kraddr-geo/data/...` 경로로 접근한다.
- ext4 작업 디렉토리에는 `data/`를 **복사하지 않는다**. 필요하면 `data` → `/mnt/.../python-kraddr-geo/data` 심볼릭 링크를 둔다(`ln -s /mnt/d/projects/python-kraddr-geo/data data`).

## 빠른 시작 (구현 후 사용 예정)

```bash
# WSL ext4 작업 디렉토리에서
cd ~/dev/python-kraddr-geo

# 의존성
uv venv && uv pip install -e ".[api,loaders,dev]"
cp .env.example .env && $EDITOR .env       # KRADDR_GEO_PG_DSN 채우기

# 데이터는 NTFS 측 (예시) — 심볼릭 링크 또는 절대경로
ln -s /mnt/d/projects/python-kraddr-geo/data data

# PostgreSQL + PostGIS (Docker 권장)
docker compose up -d postgres              # postgis/postgis:16-3.4

# 스키마 적용
alembic upgrade head

# 전국 적재 (시도별 ZIP 또는 폴더가 섞여 있어도 OK)
kraddr-geo load all-sidos ./data/jusoMap/202605 --mode full \
    --pg-conn "host=localhost dbname=kraddr_geo user=addr password=..."

# 서비스 기동
uvicorn kraddr.geo.api.app:app --reload --port 8000
```

프론트엔드(별도 저장소 또는 디렉토리, Next.js 16):

```bash
cd kraddr-geo-ui
cp .env.local.example .env.local && $EDITOR .env.local   # KAKAO JS 키 등
npm ci
npm run gen:types        # 백엔드 openapi.json → TypeScript 타입 생성
npm run dev              # http://localhost:3000
```

운영 콘솔은 `/debug/geocode`로 바로 진입한다. `NEXT_PUBLIC_VWORLD_API_KEY`가 없으면 지도 영역은 좌표 프리뷰로 대체되며, 백엔드 API는 `KRADDR_GEO_API_INTERNAL_URL`을 통해 Next.js Route Handler가 서버 측에서 프록시한다.

## 진입점

- **Python 라이브러리**: `from kraddr.geo import AsyncAddressClient` — asyncio 컨텍스트 매니저
- **REST API**: `uvicorn kraddr.geo.api.app:app` — Swagger UI는 `http://localhost:8000/v1/docs`
- **CLI**: `kraddr-geo --help` — `load`, `refresh`, `validate`, `healthz`
- **디버그/관리 UI**: `kraddr-geo-ui` (별도 Node.js 패키지) — 내부망 전용 (ADR-013)

## 라이브러리 사용 예

```python
import asyncio
from kraddr.geo import AsyncAddressClient

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
| `src/kraddr/geo/dto/` | pydantic v2 입력/출력 (DB·FastAPI 의존성 없음) |
| `src/kraddr/geo/core/` | DB 무관 비즈니스 로직. Protocol에만 의존 |
| `src/kraddr/geo/infra/` | DB 어댑터 (SQLAlchemy 2 async + raw SQL) |
| `src/kraddr/geo/client.py` | `AsyncAddressClient` — 라이브러리 진입점 |
| `src/kraddr/geo/api/` | FastAPI 라우터 |
| `src/kraddr/geo/loaders/` | 시도 SHP, 사서함, 다량배달처, 증분 적재 |
| `src/kraddr/geo/cli/` | typer CLI |
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

`python-kraddr-geo`은 로컬 DB가 1차이고 외부 API는 폴백/보조 용도다. 발급 절차·환경변수·호출 정책은 [`docs/external-apis.md`](docs/external-apis.md) 참조.

| 서비스 | 환경변수 | 용도 |
|--------|---------|------|
| vworld | `KRADDR_GEO_VWORLD_API_KEY` | 지오코딩 폴백, 통합 검색 |
| vworld WMTS | `NEXT_PUBLIC_VWORLD_API_KEY` (frontend) | 디버그/관리 UI 지도 |
| juso 검색 | `KRADDR_GEO_JUSO_API_KEY` | 도로명/지번 검색 폴백 |
| juso 좌표 | `KRADDR_GEO_JUSO_COORD_API_KEY` (없으면 위 키 재사용) | 좌표 변환 폴백 |
| epost | `KRADDR_GEO_EPOST_API_KEY` | 사서함·다량배달처 ZIP 자동 다운로드 |

## 법적·데이터 사용 한계

이 저장소의 MIT 라이선스는 저장소에 포함된 소스 코드와 문서에만 적용된다. 도로명주소 전자지도, juso, epost, vworld 등 외부 원천 데이터와 API 응답은 각 제공 기관의 이용약관·저작권·재배포 조건을 따른다.

- 원천 ZIP/SHP/TXT, 외부 API 응답 캐시, 내려받은 우편번호 파일은 이 저장소에 커밋하지 않는다.
- 운영자는 도로명주소 안내시스템, 공공데이터포털, vworld의 최신 약관과 호출 한도를 직접 확인해야 한다.
- 본 패키지는 주소 정규화·지오코딩을 돕는 기술 도구이며, 토지·건축물·행정구역 경계의 법적 효력이나 공적 증명을 보장하지 않는다. 법적 판단이 필요한 업무는 해당 기관의 공식 공부와 고시를 기준으로 검증한다.

디버그 UI 지도는 MapLibre GL JS + VWorld WMTS를 사용한다. 공통 wrapper 또는 패키징 문제가 나오면 이 저장소에서만 우회하지 않고 [`digitie/maplibre-vworld-js`](https://github.com/digitie/maplibre-vworld-js)도 적극 수정 대상에 포함한다.

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
- [`docs/backend-package.md`](docs/backend-package.md) — `python-kraddr-geo` 백엔드 사양서 (`kraddr.geo` 패키지)
- [`docs/frontend-package.md`](docs/frontend-package.md) — `kraddr-geo-ui` 프론트엔드 사양서
- [`docs/agent-guide.md`](docs/agent-guide.md) — AI 에이전트 작업·문서화 가이드
- [`docs/external-apis.md`](docs/external-apis.md) — vworld/juso/epost 발급·호출
- [`docs/dev-environment.md`](docs/dev-environment.md), [`docs/dev-environment-recovery.md`](docs/dev-environment-recovery.md), [`docs/windows-reinstall-recovery.md`](docs/windows-reinstall-recovery.md) — WSL 개발 환경과 Windows 재설치 후 복구 절차
- [`docs/tasks.md`](docs/tasks.md), [`docs/resume.md`](docs/resume.md), [`docs/journal.md`](docs/journal.md) — 백로그·진척도·작업 일지
- [`docs/address-db-schema.md`](docs/address-db-schema.md), [`docs/geocoding-readiness.md`](docs/geocoding-readiness.md), [`docs/reverse-geocoding.md`](docs/reverse-geocoding.md), [`docs/spatialite-vworld-implementation.md`](docs/spatialite-vworld-implementation.md) — 주제별 요약
- [`docs/reflection-summary.md`](docs/reflection-summary.md) — 사양 첨부파일 반영 내용 요약

## 라이선스

MIT (구현 시작 시 `pyproject.toml`과 `LICENSE`에 반영 예정).
