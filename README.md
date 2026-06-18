# kor-travel-geo

![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)
![GPL-3.0-only 라이선스](https://img.shields.io/badge/License-GPL--3.0-blue.svg)
![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)
![PostgreSQL + PostGIS](https://img.shields.io/badge/database-PostgreSQL%20%2B%20PostGIS-336791.svg)

`kor-travel-geo`는 대한민국 주소를 대상으로 하는 지오코딩·리버스 지오코딩 Python 라이브러리이자 FastAPI REST API입니다. 행정안전부 주소기반산업지원서비스가 제공하는 도로명주소 원천을 PostgreSQL + PostGIS에 적재하고, 로컬 DB를 우선 사용해 주소 검색과 좌표 변환을 제공합니다.

- `v1` REST API는 vworld.kr 지오코딩·리버스 지오코딩 API와 호환되는 응답 구조를 목표로 합니다.
- `v2` REST API와 Python 공개 API는 자체 후보 목록 모델을 사용합니다.
- `kor-travel-geo-ui`는 같은 저장소 안의 Next.js 기반 디버그·관리 UI이며, 사용자 대상 서비스 UI가 아니라 내부 운영 도구입니다.

이전 SpatiaLite/SQLite 기반 구현은 `v1` 브랜치에 보존되어 있고, `main`은 PostgreSQL + PostGIS 기반 재구현입니다.

## 현재 상태

`main`에는 백엔드 라이브러리, FastAPI REST API, `ktgctl` CLI, `kor-travel-geo-ui` 관리 UI가 함께 들어 있습니다. 실 데이터 적재, 성능 측정, 지도 UI, 백업/복원, 운영 메타데이터 같은 상세 진행 상황은 계속 바뀌므로 README에 복제하지 않고 [`docs/resume.md`](docs/resume.md)와 [`docs/journal.md`](docs/journal.md)를 정본으로 둡니다.

원천 ZIP/SHP/TXT와 외부 API 응답 캐시는 저장소에 포함하지 않습니다. 운영자는 도로명주소 안내시스템, 공공데이터포털, vworld의 이용약관과 재배포 조건을 별도로 확인해야 합니다.

## 제공 표면

| 표면 | 진입점 | 설명 |
|------|--------|------|
| Python 라이브러리 | `from kortravelgeo import AsyncAddressClient` | async-only 후보 목록 API |
| REST API v1 | `uvicorn kortravelgeo.api.app:app` | vworld 호환 지오코딩·리버스 지오코딩 |
| REST API v2 | 같은 FastAPI 앱 | 자체 후보 목록 기반 geocode/reverse/search |
| CLI | `ktgctl --help` | 적재, MV refresh, 검증, 백업/복원 등 |
| 관리 UI | `kor-travel-geo-ui` | 내부망 디버그·관리 콘솔 |

## 먼저 읽을 문서

README는 입구 역할만 합니다. 세부 절차와 결정은 아래 문서를 정본으로 봅니다.

| 필요 정보 | 문서 |
|-----------|------|
| 현재 진척도와 다음 작업 | [`docs/resume.md`](docs/resume.md) |
| 작업 일지 | [`docs/journal.md`](docs/journal.md) |
| 표준 에이전트 작업 흐름 | [`docs/runbooks/agent-workflow.md`](docs/runbooks/agent-workflow.md) |
| 반복 실패 패턴 | [`docs/runbooks/agent-failure-patterns.md`](docs/runbooks/agent-failure-patterns.md) |
| PC/WSL 개발 환경 | [`docs/dev-environment.md`](docs/dev-environment.md) |
| 전체 아키텍처와 의존 방향 | [`docs/architecture/architecture.md`](docs/architecture/architecture.md) |
| 백엔드 패키지 세부 사양 | [`docs/architecture/backend-package.md`](docs/architecture/backend-package.md) |
| 프론트엔드 패키지 세부 사양 | [`docs/architecture/frontend-package.md`](docs/architecture/frontend-package.md) |
| PostgreSQL/PostGIS 데이터 모델 | [`docs/architecture/data-model.md`](docs/architecture/data-model.md) |
| 외부 API 키와 호출 정책 | [`docs/architecture/external-apis.md`](docs/architecture/external-apis.md) |
| ADR 인덱스 | [`docs/adr/README.md`](docs/adr/README.md), [`docs/decisions.md`](docs/decisions.md) |

## 개발 환경 요약

이 저장소의 PC 개발 기준은 NTFS worktree에서 편집·Git 작업을 하고, WSL ext4 테스트 미러에서 설치·테스트·장기 실행을 수행하는 방식입니다. PostgreSQL/PostGIS와 RustFS는 이 저장소에서 직접 구동하지 않고, 이미 동작 중인 인프라에 `KTG_PG_DSN`, `KTG_RUSTFS_*` 설정으로 접속합니다.

```text
NTFS worktree:   /mnt/f/dev/kor-travel-geo-codex/
WSL test mirror: ~/dev/kor-travel-geo-codex-test/
Data root:       /mnt/f/dev/geodata/juso/
API port:        12501
UI port:         12505
```

테스트 전에 NTFS worktree를 WSL 미러로 복사합니다.

```bash
mkdir -p ~/dev/kor-travel-geo-codex-test
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude .venv \
  --exclude node_modules --exclude kor-travel-geo-ui/.next \
  --exclude data --exclude artifacts \
  /mnt/f/dev/kor-travel-geo-codex/ ~/dev/kor-travel-geo-codex-test/
cd ~/dev/kor-travel-geo-codex-test
test -e data || ln -s /mnt/f/dev/geodata data
source scripts/agent_env.sh
```

자세한 환경 구성, GDAL 핀, Windows Git/WSL 경계, Playwright 실행 방식은 [`docs/dev-environment.md`](docs/dev-environment.md)와 [`docs/runbooks/agent-workflow.md`](docs/runbooks/agent-workflow.md)를 따릅니다.

## 로컬 실행 요약

### 백엔드

```bash
cd ~/dev/kor-travel-geo-codex-test
uv venv
uv pip install -e ".[api,dev]"
test -f .env || cp .env.example .env

# .env의 KTG_PG_DSN이 이미 동작 중인 PostgreSQL/PostGIS를 가리켜야 합니다.
ktgctl init-db
uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12501 --reload
```

실제 원천 적재는 원천 경로와 기준월 확인이 필요합니다. 운영 절차는 [`docs/architecture/backend-package.md`](docs/architecture/backend-package.md)의 CLI 절과 [`docs/runbooks/agent-workflow.md`](docs/runbooks/agent-workflow.md)를 먼저 확인합니다.

```bash
ktgctl load full-set ./data/juso --discover
ktgctl refresh mv --swap
```

### 프론트엔드

```bash
cd ~/dev/kor-travel-geo-codex-test/kor-travel-geo-ui
cp .env.local.example .env.local
npm ci
npm run gen:types
npm run dev -- --port 12505
```

`kor-travel-geo-ui`는 DB에 직접 연결하지 않습니다. 브라우저 요청은 Next.js route handler를 거쳐 백엔드 REST API로 프록시됩니다.

## 라이브러리 예제

```python
import asyncio
from kortravelgeo import AsyncAddressClient


async def main() -> None:
    async with AsyncAddressClient() as client:
        geocode = await client.geocode(query="서울특별시 강남구 테헤란로 152")
        if geocode.status == "OK" and geocode.candidates:
            first = geocode.candidates[0]
            print(first.point)
            print(first.address.full if first.address else None)

        reverse = await client.reverse(127.028601, 37.500344, include_zipcode=True)
        for item in reverse.candidates:
            print(item.match_kind, item.address.full if item.address else None)


asyncio.run(main())
```

공개 라이브러리 API는 async-only입니다. 동기 API나 장기 호환 alias는 추가하지 않습니다.

## 검증

백엔드 검증은 WSL ext4 테스트 미러에서 실행합니다.

```bash
pytest -q
ruff check .
mypy src/kortravelgeo scripts/export_openapi.py
lint-imports
python scripts/export_openapi.py --check --output openapi.json
```

프론트엔드 변경이 있으면 WSL 미러에서 Linux Node/npm으로 실행합니다.

```bash
scripts/frontend_check.sh
cd kor-travel-geo-ui
npx react-doctor@latest . --offline --verbose --json
```

Playwright e2e와 실제 브라우저는 Windows Node/브라우저에서만 실행합니다. WSL에서는 Playwright를 실행하지 않습니다.

## 데이터와 외부 API

| 항목 | 기준 |
|------|------|
| 원천 데이터 | 행정안전부 주소기반산업지원서비스 원천을 로컬 `data/` 또는 공용 geodata 경로에서 읽음 |
| vworld | 지오코딩 폴백, 통합 검색, VWorld WMTS 지도 렌더링 |
| juso | 도로명/지번 검색과 좌표 변환 폴백 |
| epost | 사서함·다량배달처 우편번호 ZIP 다운로드 |
| RustFS | 선택적 upload set 저장소. 이 저장소는 bucket을 직접 구동하지 않음 |

키 발급, 환경변수, 쿼터, 재시도 정책은 [`docs/architecture/external-apis.md`](docs/architecture/external-apis.md)에 모아 둡니다. 모든 키는 `.env`나 운영 secret으로만 관리하고 Git에 커밋하지 않습니다.

## 디렉터리 개요

| 경로 | 역할 |
|------|------|
| `src/kortravelgeo/dto/` | pydantic v2 입력·출력 모델 |
| `src/kortravelgeo/core/` | DB 무관 비즈니스 로직 |
| `src/kortravelgeo/infra/` | SQLAlchemy 2 async 기반 DB 어댑터와 raw SQL repository |
| `src/kortravelgeo/loaders/` | Juso 텍스트, SHP, daily delta 적재 |
| `src/kortravelgeo/api/` | FastAPI 앱과 라우터 |
| `src/kortravelgeo/cli/` | Typer 기반 `ktgctl` 명령 |
| `sql/`, `alembic/` | DDL과 마이그레이션 |
| `tests/` | 단위·통합·e2e 테스트 |
| `kor-travel-geo-ui/` | Next.js 디버그·관리 UI |
| `docs/` | ADR, 사양서, runbook, 작업 기록 |

계층 의존 방향은 `dto -> core -> infra -> client -> api/cli` 한 방향이며, `import-linter`가 강제합니다.

## 문서와 기여 규칙

- Markdown/RST 문서는 한국어로 작성합니다. 공식 API 필드명, 코드 식별자, 명령어, URL, 제공자 원문처럼 보존해야 하는 값만 영어를 유지합니다.
- 작업 전 [`AGENTS.md`](AGENTS.md), [`SKILL.md`](SKILL.md), [`docs/runbooks/agent-workflow.md`](docs/runbooks/agent-workflow.md), [`docs/runbooks/agent-failure-patterns.md`](docs/runbooks/agent-failure-patterns.md)를 확인합니다.
- 작업 완료 후 [`docs/journal.md`](docs/journal.md)를 갱신하고, 현재 상태가 바뀌면 [`docs/resume.md`](docs/resume.md)도 갱신합니다.
- 주요 구조 결정은 ADR로 남기고, 사용자 가시 변경은 `CHANGELOG.md`에 기록합니다.
- `main` 직접 push 대신 작업 브랜치와 PR을 사용합니다.

## 법적 고지

GPL-3.0-only 라이선스는 저장소에 포함된 소스 코드와 문서에 적용됩니다. 자세한 조건은 [`LICENSE`](LICENSE)를 확인하십시오. 도로명주소 전자지도, juso, epost, vworld 등 외부 원천 데이터와 API 응답은 각 제공 기관의 이용약관, 저작권, 재배포 조건을 따릅니다. 본 패키지는 주소 정규화와 지오코딩을 돕는 기술 도구이며, 토지·건축물·행정구역 경계의 법적 효력이나 공적 증명을 보장하지 않습니다.
