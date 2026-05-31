# 처음 보는 사람을 위한 코드 안내

`kraddr-geo` 백엔드와 `kraddr-geo-ui` 프론트엔드는 별도 패키지지만 한 시스템을 구성한다. 아래 순서대로 읽으면 큰 그림에서 세부로 자연스럽게 내려간다.

> 이전 SpatiaLite 기반 `kraddr.geo` 구현은 `v1` 브랜치에 보존되어 있다. `main`은 PostgreSQL + PostGIS 기반 새 사양으로 처음부터 다시 짓는다(ADR-001).

## 1. 큰 그림

1. `README.md` — 5분 안에 프로젝트가 무엇인지, 어떻게 띄우는지.
2. `SKILL.md` — DO NOT 룰, 도메인 어휘, 자주 묻는 작업.
3. `docs/architecture.md` — 두 패키지의 관계, 백엔드 계층, 데이터 흐름.

## 2. 백엔드 (`kraddr-geo`)

의존 방향은 **dto → core → infra → client → api/cli** 한 방향(ADR-004).

```
src/kraddr/geo/
  dto/         pydantic v2 입력/출력 (DB·FastAPI 의존성 없음)
  core/        DB 무관 비즈니스 로직. Protocol에만 의존.
  infra/       SQLAlchemy 2 async + raw SQL repository
  loaders/     파일 적재 (GDAL Python binding, ogr2ogr 미사용)
  client.py    AsyncAddressClient — 라이브러리 진입점
  api/         FastAPI 라우터
  cli/         typer CLI
```

이해를 빠르게 하려면:

1. **dto**부터 본다. `dto/common.py`, `dto/geocode.py` — 입출력의 모양이 곧 시스템의 모양이다.
2. **core/geocoder.py**를 본다. `parse_address` → `repo.lookup_by_road` → `RefinedAddress` 빌드 흐름.
3. **infra/geocode_repo.py**의 raw SQL 상수 (`_LOOKUP_ROAD`, `_FUZZY_ROADS`).
4. **client.py**의 `AsyncAddressClient` — 위 셋을 묶는 진입점.
5. **api/routers/geocode.py** — REST v1 라우터는 client의 내부 v1 adapter를 호출한다.

세부 사양은 `docs/backend-package.md`에 있다.

## 3. 프론트엔드 (`kraddr-geo-ui`)

별도 Node.js 패키지(Next.js 16 + Tailwind + MapLibre GL JS + VWorld WMTS + TanStack Query). 사용자 대상이 아니라 개발자·운영자용 디버깅/관리 UI.

```
kraddr-geo-ui/
  app/                 Next.js App Router. /debug/* + /admin/* + /api/proxy/[...]
  components/          layout/, ui/, vworld/, debug/, admin/
  lib/                 api.ts, schemas.ts(zod), consistency.ts, format.ts, load-workflow.ts, sido.ts
  scripts/gen-types.mjs 백엔드 openapi.json → TypeScript 타입 생성
```

이해 순서:

1. `lib/api.ts` — Next.js 프록시(`/api/proxy`)를 호출하는 fetch helper.
2. `app/debug/geocode/page.tsx` — 폼 + 지도 + JsonViewer가 한 화면에서 어떻게 묶이는지.
3. `app/admin/load/page.tsx` — 업로드 단계 → 처리 단계 상태 머신.
4. `components/admin/LoadConsole.tsx` — full-load batch payload, raw upload, MV refresh enqueue가 한 화면에 묶이는 방식.

세부 사양은 `docs/frontend-package.md`에 있다.

## 4. 데이터·로더

- `docs/data-model.md` — PostgreSQL + PostGIS 스키마 reference.
- `docs/backend-package.md` §9 — GDAL Python binding 시도 로더, MVM_RES_CD 증분 로더, 작업 큐, 업로드+일괄 처리.

## 5. 외부 API

`docs/external-apis.md`에 vworld / juso / epost의 발급 절차, 환경변수, 호출 예시, 재시도·회로차단 정책이 모여 있다. 프론트엔드 지도는 VWorld WMTS + MapLibre를 쓰며, 공통 VWorld/MapLibre wrapper 문제가 나오면 `digitie/maplibre-vworld-js`도 함께 수정한다. 주소 디버그/관리 UI에만 의미가 있는 기능은 `kraddr-geo-ui` wrapper에 둔다.

## 6. 검증

```bash
# 백엔드
pip install -e ".[api,loaders,dev]"
pytest -q
ruff check .
mypy src/kraddr/geo
lint-imports

# 프론트엔드
cd kraddr-geo-ui
npm ci
npm run lint
npm run type-check
npm run test
npm run build
npm run test:e2e   # Windows Node/브라우저에서만 실행
```

스키마 변경이 있다면 `python scripts/export_openapi.py` → `cd kraddr-geo-ui && npm run gen:types`로 frontend Zod/types를 재생성한다.

## 7. 작업 흐름

작업 1건은 다음 사이클을 돈다 (`docs/agent-guide.md` §B4.2):

```
[읽기] resume → architecture 관련 절 → 관련 ADR
  ↓
[코드] 변경 (한 PR / 한 commit 단위)
  ↓
[검증] pytest / ruff / mypy / lint-imports / (UI) Windows Playwright
  ↓
[기록] docs/journal.md 엔트리 추가
  ↓
[갱신] docs/resume.md 진척도 토글, docs/tasks.md 상태 변경
  ↓
[선택] ADR 추가, CHANGELOG 갱신
  ↓
[커밋] <scope> <verb>: <object> (#T-NNN)
```
