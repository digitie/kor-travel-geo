# SKILL — python-kraddr-geo 에이전트 매뉴얼

> 이 파일은 당신(AI 에이전트)이 작업을 시작하기 전 반드시 읽어야 한다.
> 1회만 읽으면 30분 이상의 디버깅을 줄일 수 있다.

## 1. 정체성

이 저장소(GitHub 이름 `python-kraddr-geo`, Python 패키지 `kraddr.geo`)는 도로명주소 전자지도(PDF 사양)를 PostGIS에 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**다. vworld API의 응답 형식을 호환하면서 자체 확장(`x_extension`)을 더한다. `kraddr-geo-ui`는 같은 저장소 안에서 관리하는 별도 Node.js 패키지이며, 디버그/관리 UI로 백엔드 REST API만 호출한다.

이전 SpatiaLite/SQLite 기반 구현은 같은 `kraddr.geo` 패키지였으나 `v1` 브랜치에 보존되어 있다. `main` 브랜치는 PostgreSQL + PostGIS 기반 새 사양으로 재시작한다.

### 식별자 매핑

| 항목 | 값 |
|------|----|
| GitHub 저장소 | `python-kraddr-geo` |
| Python import | `from kraddr.geo import ...` |
| CLI 명령 | `kraddr-geo` |
| 환경변수 prefix | `KRADDR_GEO_*` |
| PostgreSQL DB 이름 | `kraddr_geo` |
| 프론트엔드 패키지 | `kraddr-geo-ui` |

### 개발 환경 (PC, WSL)

- **Git source of truth는 NTFS** `/mnt/f/dev/python-kraddr-geo` 계열 checkout이다. 코드 편집, branch, commit, PR은 NTFS 에이전트 worktree에서 수행한다.
- **테스트와 장기 실행은 WSL ext4 테스트 미러**에서 수행한다. NTFS worktree를 `rsync --delete`로 `~/dev/python-kraddr-geo-<agent>-test/`에 복사한 뒤 `pip`/`npm`/`pytest`/`uvicorn`을 실행한다. ext4 미러에서는 commit/push하지 않는다.
- **Git 명령은 Windows Git 기준**이다. NTFS worktree의 `.git`/`gitdir`은 `F:/dev/...`를 가리키게 두고, WSL 미러에서 Git commit/branch를 수집하는 스크립트는 Windows `git.exe`와 `F:/dev/python-kraddr-geo-*` 경로를 사용한다. WSL `git` 편의를 위해 포인터를 `/mnt/f/...`로 바꾸지 않는다.
- **DB 검증은 T-027 최종 DB 재사용이 기본**이다. `kraddr-geo-t027-final` Docker project와 `/home/digitie/kraddr-geo-data/pgdata-final-20260529` pgdata를 host port `15434`로 다시 올려 사용한다. 클린 DB는 명시 요청 때만 새 pgdata로 만든다.
- **데이터(`data/`)는 NTFS main repo 아래** `/mnt/f/dev/python-kraddr-geo/data/`를 기준으로 둔다. ext4 테스트 미러에서는 절대경로 또는 심볼릭 링크로 참조한다.
- **로컬 secret/env 파일**(`.env`, `kraddr-geo-ui/.env.local`, `.claude/settings.local.json` 등)은 각 NTFS worktree에 복사하되 Git에 커밋하지 않는다. `.env*`, `.claude/`, `.codegraph/`는 ignore 대상이다.
- **Playwright e2e는 Windows Node/브라우저 전용**이다. WSL Playwright는 실행하지 않는다.

### 에이전트별 worktree / CodeGraph

- ChatGPT Codex는 `/mnt/f/dev/python-kraddr-geo-codex`, Claude Code는 `/mnt/f/dev/python-kraddr-geo-claude`, Google Antigravity 2.0은 `/mnt/f/dev/python-kraddr-geo-antigravity` worktree를 고정으로 사용한다.
- `geo-codex`, `geo-claude`, `geo-antigravity` 이름은 더 이상 새 작업에 쓰지 않는다.
- worktree는 에이전트별로 유지하고 작업마다 새 branch만 만든다. 새 작업 시작 예시는 `git fetch origin main && git switch -c agent/codex-next origin/main`이다.
- CodeGraph는 worktree마다 최초 1회 `codegraph init -i`로 초기화한다. `.codegraph/`가 이미 있으면 `codegraph init`을 반복하지 말고 `codegraph sync`로 증분 갱신한다. NTFS `/mnt`에서는 live watch가 비활성화될 수 있으므로 branch 전환·pull·merge 뒤 수동 `sync`가 필수다.
- 현재 인덱스 상태는 `codegraph status`로 확인한다.
- Codex MCP 설정은 프로젝트 루트 `.codex/config.toml`에 둔다. Codex Desktop을 재시작한 뒤 CodeGraph MCP 도구가 노출된다.
- `kraddr-geo-ui`의 React 컴포넌트, 지도 wrapper, 공용 UI primitive를 수정하기 전에는 CodeGraph MCP의 `codegraph_explore`로 영향도를 먼저 평가한다. 확인 대상은 호출자, import 경로, 관련 테스트, `maplibre-vworld-js` 경계다.
- `.codegraph/`는 로컬 SQLite 인덱스이므로 커밋하지 않는다.

## 2. 빠른 시작

```bash
cd /mnt/f/dev/python-kraddr-geo-codex              # NTFS Codex worktree
git fetch origin main && git switch -c agent/codex-next origin/main
rsync -a --delete --exclude .git --exclude .codegraph --exclude .venv --exclude node_modules --exclude kraddr-geo-ui/.next --exclude data ./ ~/dev/python-kraddr-geo-codex-test/
cd ~/dev/python-kraddr-geo-codex-test                 # WSL ext4 테스트 미러
sudo apt install -y libgdal-dev gdal-bin              # loaders extra용 (ADR-008)
uv venv && uv pip install -e ".[api,dev]"
uv pip install "gdal==$(gdal-config --version)"        # 시스템 GDAL과 버전 매치
uv pip install -e ".[loaders]"                         # 이제 안전하게 빌드
test -f .env || cp .env.example .env                  # KRADDR_GEO_PG_DSN 채우기
test -e data || ln -s /mnt/f/dev/python-kraddr-geo/data data # NTFS data를 참조
docker compose up -d db                         # postgis/postgis:16-3.4
alembic upgrade head
kraddr-geo load all-sidos \
  --juso "./data/juso/도로명주소 한글_전체분" \
  --jibun "./data/juso/도로명주소 한글_전체분" \
  --locsum "./data/juso/위치정보요약DB" \
  --navi "./data/juso/내비게이션용DB" \
  --shp-root "./data/jusoMap/202605" \
  --yyyymm 202605
uvicorn kraddr.geo.api.app:app --reload
```

자세한 환경 셋업과 conda/Docker 대안은 `docs/dev-environment.md`.

## 3. 디렉토리 지도

```
src/kraddr/geo/
  dto/       — pydantic v2 입력/출력 (DB·FastAPI 의존성 없음)
  core/      — 비즈니스 로직 (Protocol에만 의존)
  infra/     — DB 어댑터 (SQLAlchemy 2 async, raw SQL)
  loaders/   — 파일 적재 (일반 쿼리 경로와 완전 분리)
  client.py  — AsyncAddressClient (라이브러리 API 진입점)
  api/       — FastAPI 라우터 (client.py를 호출)
  cli/       — typer CLI
```

프론트엔드 작업은 `kraddr-geo-ui/`에서 수행한다. 이 패키지는 Next.js 기반 내부 디버그/관리 UI이며, DB 드라이버를 직접 갖지 않고 `/v1/*` REST API만 호출한다.

의존 방향은 **dto → core → infra → client → api/cli** 한 방향. `import-linter`가 CI에서 강제한다.

## 4. 절대 하지 말 것 (DO NOT)

1. **의존 방향 역행 금지**: 위 계층 순서를 거스르는 import 금지. 역방향 import 시 import-linter가 CI에서 실패시킴.
2. **동기 인터페이스 추가 금지**: `AsyncAddressClient`만 둔다. 동기가 필요하면 호출자가 `asyncio.run`으로 감싼다.
3. **`pg_trgm.similarity_threshold` 전역 변경 금지**: 항상 트랜잭션 내부에서 `SET LOCAL`.
4. **ORM에 비즈니스 로직 금지**: `infra/models.py`는 매핑만. 쿼리는 `infra/*_repo.py`의 raw SQL에.
5. **좌표 순서 혼동 금지**: 모든 외부 인터페이스는 `(lon, lat)`. 내부 PostGIS도 `ST_MakePoint(lon, lat)`.
6. **MVM_RES_CD 매핑 하드코드 금지**: settings 또는 DB `load_codes` 테이블에서 읽는다.
7. **응답에 `x_extension` 외 자체 필드 추가 금지**: vworld 호환성을 깬다.
8. **외부 API 키 평문 커밋 금지**: 모두 `SecretStr`. `.env`는 권한 600 또는 systemd `EnvironmentFile`/vault.
9. **`ogr2ogr` subprocess 호출 금지**: GDAL Python binding(`gdal.VectorTranslate`) 사용. CP949 디코딩은 `open_options=["ENCODING=CP949"]`로 명시.
10. **프론트엔드 패키지에 DB 드라이버 추가 금지**: `kraddr-geo-ui`는 백엔드 REST API만 호출. `pg`, `prisma` 같은 의존성 들어오면 ADR 위반.
11. **공간 쿼리 술어에서 좌표 형변환 금지**: 입력 좌표는 CTE/파라미터로 **한 번만** `ST_Transform`해서 상수로 굳히고, 술어는 `ST_DWithin(t.pt_5179, p.geom, :radius_m)`처럼 컬럼은 그대로 둔다. `ST_Transform(t.pt_5179, 4326)`이 술어에 들어가면 GiST 인덱스를 못 타고 매 행 변환이 돌아간다. **반경 검색은 `pt_5179`(meter)** 기준으로 한다 — `pt_4326`은 응답 직렬화 전용. MV의 `pt_source` 컬럼이 좌표 출처(entrance vs centroid)를 노출하므로 라우터는 centroid 결과의 `confidence`를 낮춰 반환(ADR-007, ADR-012, `docs/data-model.md` "공간 쿼리 가이드").
12. **SQLAlchemy bulk `insert().values(rows)` 파라미터 폭주 금지**: PostgreSQL 프로토콜은 한 쿼리당 최대 65,535개 파라미터. row × column이 ~30,000 이상이면 `psycopg.copy_*` 또는 `gdal.VectorTranslate(... PG_USE_COPY=YES)`로 전환한다(ADR-005). 안전 마진은 한도의 절반(30k) 권장.
13. **작업 큐 상태를 in-memory만 신뢰 금지**: 적재 작업은 `load_jobs` 테이블로 영속화한다(ADR-011). lifespan startup에서 `state IN ('queued','running')` 잔존 행을 `failed`로 마크하고, 실행 직렬성은 advisory lock 또는 `SELECT ... FOR UPDATE SKIP LOCKED`로 DB 수준에서 보강.

## 5. 자주 묻는 작업

| 작업 | 시작 파일 |
|------|-----------|
| 새 엔드포인트 추가 | `dto/<name>.py` → `core/<name>.py` → `infra/<name>_repo.py` → `api/routers/<name>.py` |
| 새 SQL 쿼리 튜닝 | `infra/*_repo.py`의 `_SQL` 상수. EXPLAIN은 `/debug/explain` UI |
| 새 적재 소스 추가 | `loaders/<name>_loader.py`, `manifest.py` 확장 |
| 응답 필드 추가 (자체 확장) | `dto/<name>.py`의 `*Extension` 클래스 |
| 새 에러 코드 추가 | `exceptions.py` + `api/responses.py` 매핑 |
| 외부 API 폴백 호출 | `httpx.AsyncClient` + `tenacity` 재시도. 키는 `Settings`에서 `SecretStr`로 |
| PR 리뷰 반영 | `docs/agent-guide.md` §B4.3. `gh pr view comments`만 보지 말고 `reviews[].body`, `review_threads[]`, 마지막 conversation comment를 모두 확인 |

## 6. 도메인 어휘

| 약어 | 의미 |
|------|------|
| BJD_CD | 법정동코드 10자리 (시도2 + 시군구3 + 읍면동3 + 리2) |
| RNCODE_FULL | 도로명코드 12자리 (SIG_CD 5 + RN_CD 7) |
| BD_MGT_SN | 건물관리번호 25자리, 전국 unique |
| BSI_ZON_NO | 건물의 기초구역번호 = 우편번호 5자리 |
| BAS_ID | `TL_KODIS_BAS`의 기초구역번호 = 우편번호 |
| MV | `mv_geocode_target` — 평면화된 머티리얼라이즈드 뷰 |
| MVM_RES_CD | 이동사유코드 (신규/수정/삭제) |
| MVMN_DE | 이동일자 YYYYMMDD |

## 7. 작업 후 체크리스트

- [ ] `pytest -q` 통과
- [ ] `ruff check .` / `mypy` / `lint-imports` 통과
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신
- [ ] DTO/스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
