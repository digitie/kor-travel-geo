# SKILL — kor-travel-geo 에이전트 매뉴얼

> 이 파일은 당신(AI 에이전트)이 작업을 시작하기 전 반드시 읽어야 한다.
> 1회만 읽으면 30분 이상의 디버깅을 줄일 수 있다.

## 1. 정체성

이 저장소(GitHub 이름 `kor-travel-geo`, Python 패키지 `kortravelgeo`)는 도로명주소 전자지도(PDF 사양)를 PostGIS에 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**다. vworld API의 응답 형식을 호환하면서 자체 확장(`x_extension`)을 더한다. `kor-travel-geo-ui`는 같은 저장소 안에서 관리하는 별도 Node.js 패키지이며, 디버그/관리 UI로 백엔드 REST API만 호출한다.

이전 SpatiaLite/SQLite 기반 구현은 같은 `kortravelgeo` 패키지였으나 `v1` 브랜치에 보존되어 있다. `main` 브랜치는 PostgreSQL + PostGIS 기반 새 사양으로 재시작한다.

### 식별자 매핑

| 항목 | 값 |
|------|----|
| GitHub 저장소 | `kor-travel-geo` |
| Python import | `from kortravelgeo import ...` |
| CLI 명령 | `ktgctl` |
| 환경변수 prefix | `KTG_*` |
| PostgreSQL DB 이름 | `kor_travel_geo` |
| 프론트엔드 패키지 | `kor-travel-geo-ui` |

### 개발 환경 (Linux-only, WSL 포함)

- **모든 개발 명령은 Linux 환경에서만 실행**한다. WSL은 허용되는 Linux 환경이며, Windows native `git.exe`/Node/npm/Python/CodeGraph는 표준 개발 경로가 아니다.
- **Git source of truth는 Linux `git`이 읽는 checkout/worktree**다. `/mnt/f/dev/kor-travel-geo` 계열 NTFS mount를 쓸 수는 있지만 `.git`/`gitdir`은 `/mnt/f/...` 같은 Linux 경로를 가리켜야 한다. `F:/...` 포인터가 남아 있으면 작업 전 Linux에서 `git worktree repair <worktree>`를 실행하거나 worktree를 재생성한다.
- **테스트와 장기 실행은 WSL ext4 테스트 미러**에서 수행한다. 고정 worktree를 `rsync --delete`로 `~/dev/kor-travel-geo-<agent>-test/`에 복사한 뒤 `pip`/`npm`/`pytest`/`uvicorn`을 실행한다. ext4 미러에서는 commit/push하지 않는다.
- **Git/CodeGraph 명령은 Linux 기준**이다. branch, commit, push, PR 준비, `codegraph sync/status`는 Linux shell에서 실행한다. 과거 Windows Git/Windows CodeGraph 포인터 정책은 ADR-065로 대체됐다.
- **DB/RustFS 검증은 접속 설정 기준**이다. 이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동하지 않는다. 이미 동작 중인 DB와 bucket에 `KTG_PG_DSN`, `KTG_RUSTFS_*` 설정으로 접속해 사용한다.
- **대용량 Juso 원천은 NTFS 공용 루트** `/mnt/f/dev/geodata/juso`(`F:\dev\geodata\juso`)를 기준으로 둔다. ext4 테스트 미러에서는 `data -> /mnt/f/dev/geodata` 심볼릭 링크로 참조해 기존 `data/juso` 상대경로를 유지한다. 현재 쓰지 않는 원천은 `F:\dev\geodata\juso\unused\`에 보존한다.
- **로컬 secret/env 파일**(`.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json` 등)은 각 worktree에 복사하되 Git에 커밋하지 않는다. `.env*`, `.claude/`, `.codegraph/`는 ignore 대상이다.
- **프론트엔드 실행은 WSL ext4 테스트 미러의 Linux Node/npm 기준**이다. `kor-travel-geo-ui` 의존성 설치, `next dev`/`next start`, lint, type-check, unit test, build, React Doctor는 WSL에서 실행한다.
- **Playwright e2e는 n150 Linux 환경 우선**이다. n150에서 실행할 수 없는 경우에만 Windows Playwright를 fallback으로 사용하고, fallback 사유와 실행 명령을 작업 기록에 남긴다.
- **반복되는 작업 실패 패턴은 먼저 `docs/runbooks/agent-failure-patterns.md`를 본다.** 특히 `.git`/`gitdir`이 `F:/...`를 가리키는 경우 Linux 경로로 repair한 뒤 진행하고, `exec_command`의 `CreateProcess ... os error 2`는 저장소 버그가 아니라 런처/quoting 문제로 먼저 분류한다.

### 에이전트별 worktree / CodeGraph

- ChatGPT Codex는 `/mnt/f/dev/kor-travel-geo-codex`, Claude Code는 `/mnt/f/dev/kor-travel-geo-claude`, Google Antigravity 2.0은 `/mnt/f/dev/kor-travel-geo-antigravity` worktree를 고정으로 사용한다.
- `geo-codex`, `geo-claude`, `geo-antigravity` 이름은 더 이상 새 작업에 쓰지 않는다.
- worktree는 에이전트별로 유지하고 작업마다 새 branch만 만든다. 새 작업 시작 예시는 `git fetch origin main && git switch -c agent/codex-next origin/main`이다.
- CodeGraph는 worktree마다 최초 1회 Linux `codegraph init -i`로 초기화한다. `.codegraph/`가 이미 있으면 `codegraph init`을 반복하지 말고 `codegraph sync`로 증분 갱신한다. NTFS `/mnt`에서는 live watch가 비활성화될 수 있으므로 branch 전환·pull·merge 뒤 수동 `sync`가 필수다.
- 현재 인덱스 상태는 `codegraph status`로 확인한다.
- Codex MCP 설정은 프로젝트 루트 `.codex/config.toml`에 둔다. Codex Desktop을 재시작한 뒤 CodeGraph MCP 도구가 노출된다.
- `kor-travel-geo-ui`의 React 컴포넌트, 지도 wrapper, 공용 UI primitive를 수정하기 전에는 CodeGraph MCP의 `codegraph_explore`로 영향도를 먼저 평가한다. 확인 대상은 호출자, import 경로, 관련 테스트, `maplibre-vworld-js` 경계다.
- `.codegraph/`는 로컬 SQLite 인덱스이므로 커밋하지 않는다.

## 2. 빠른 시작

```bash
cd /mnt/f/dev/kor-travel-geo-codex              # Linux에서 읽히는 Codex worktree
git fetch origin main && git switch -c agent/codex-next origin/main
rsync -a --delete --exclude .git --exclude .codegraph --exclude .venv --exclude node_modules --exclude kor-travel-geo-ui/.next --exclude data --exclude artifacts ./ ~/dev/kor-travel-geo-codex-test/
cd ~/dev/kor-travel-geo-codex-test                 # WSL ext4 테스트 미러
sudo apt install -y libgdal-dev gdal-bin              # loaders extra용 (ADR-008)
uv venv && uv pip install -e ".[api,dev]"
uv pip install "gdal==$(gdal-config --version)"        # 시스템 GDAL과 버전 매치
uv pip install -e ".[loaders]"                         # 이제 안전하게 빌드
test -f .env || cp .env.example .env                  # KTG_PG_DSN, KTG_RUSTFS_* 채우기
test -e data || ln -s /mnt/f/dev/geodata data # NTFS 공용 geodata를 참조
# PostgreSQL/PostGIS와 RustFS는 이미 동작 중인 외부 인프라에 접속한다.
alembic upgrade head
ktgctl load all-sidos \
  --juso "./data/juso/도로명주소 한글_전체분" \
  --jibun "./data/juso/도로명주소 한글_전체분" \
  --locsum "./data/juso/위치정보요약DB" \
  --navi "./data/juso/내비게이션용DB" \
  --shp-root "./data/jusoMap/202605" \
  --yyyymm 202605
uvicorn kortravelgeo.api.app:app --reload
```

자세한 환경 셋업과 conda/Docker 대안은 `docs/dev-environment.md`.

## 3. 디렉토리 지도

```
src/kortravelgeo/
  dto/       — pydantic v2 입력/출력 (DB·FastAPI 의존성 없음)
  core/      — 비즈니스 로직 (Protocol에만 의존)
  infra/     — DB 어댑터 (SQLAlchemy 2 async, raw SQL)
  loaders/   — 파일 적재 (일반 쿼리 경로와 완전 분리)
  client.py  — AsyncAddressClient (라이브러리 API 진입점)
  api/       — FastAPI 라우터 (client.py를 호출)
  cli/       — typer CLI
```

프론트엔드 작업은 `kor-travel-geo-ui/`에서 수행한다. 이 패키지는 Next.js 기반 내부 디버그/관리 UI이며, DB 드라이버를 직접 갖지 않고 `/v1/*` REST API만 호출한다.

의존 방향은 **dto → core → infra → client → api/cli** 한 방향. `import-linter`가 CI에서 강제한다.

## 4. 절대 하지 말 것 (DO NOT)

1. **의존 방향 역행 금지**: 위 계층 순서를 거스르는 import 금지. 역방향 import 시 import-linter가 CI에서 실패시킴.
2. **동기 인터페이스 추가 금지**: `AsyncAddressClient`만 둔다. 동기가 필요하면 호출자가 `asyncio.run`으로 감싼다 (구 ADR-002 → 본 §4 룰로 통합).
3. **`pg_trgm.similarity_threshold` 전역 변경 금지**: 항상 트랜잭션 내부에서 `SET LOCAL`.
4. **ORM에 비즈니스 로직 금지**: `infra/models.py`는 매핑만. 쿼리는 `infra/*_repo.py`의 raw SQL에.
5. **좌표 순서 혼동 금지**: 모든 외부 인터페이스는 `(lon, lat)`. 내부 PostGIS도 `ST_MakePoint(lon, lat)`.
6. **MVM_RES_CD 매핑 하드코드 금지**: settings 또는 DB `load_codes` 테이블에서 읽는다.
7. **응답에 `x_extension` 외 자체 필드 추가 금지**: vworld 호환성을 깬다.
8. **외부 API 키 평문 커밋 금지**: 모두 `SecretStr`. `.env`는 권한 600 또는 systemd `EnvironmentFile`/vault.
9. **`ogr2ogr` subprocess 호출 금지**: GDAL Python binding(`gdal.VectorTranslate`) 사용. CP949 디코딩은 `open_options=["ENCODING=CP949"]`로 명시.
10. **프론트엔드 패키지에 DB 드라이버 추가 금지**: `kor-travel-geo-ui`는 백엔드 REST API만 호출. `pg`, `prisma` 같은 의존성 들어오면 ADR 위반.
11. **공간 쿼리 술어에서 좌표 형변환 금지**: 입력 좌표는 CTE/파라미터로 **한 번만** `ST_Transform`해서 상수로 굳히고, 술어는 `ST_DWithin(t.pt_5179, p.geom, :radius_m)`처럼 컬럼은 그대로 둔다. `ST_Transform(t.pt_5179, 4326)`이 술어에 들어가면 GiST 인덱스를 못 타고 매 행 변환이 돌아간다. **반경 검색은 `pt_5179`(meter)** 기준으로 한다 — `pt_4326`은 응답 직렬화 전용. MV의 `pt_source` 컬럼이 좌표 출처(entrance vs centroid)를 노출하므로 라우터는 centroid 결과의 `confidence`를 낮춰 반환(ADR-007, ADR-012, `docs/architecture/data-model.md` "공간 쿼리 가이드").
12. **SQLAlchemy bulk `insert().values(rows)` 파라미터 폭주 금지**: PostgreSQL 프로토콜은 한 쿼리당 최대 65,535개 파라미터. row × column이 ~30,000 이상이면 `psycopg.copy_*` 또는 `gdal.VectorTranslate(... PG_USE_COPY=YES)`로 전환한다(ADR-005). 안전 마진은 한도의 절반(30k) 권장.
13. **작업 큐 상태를 in-memory만 신뢰 금지**: 적재 작업은 `load_jobs` 테이블로 영속화한다(ADR-011). lifespan startup에서 `state IN ('queued','running')` 잔존 행을 `failed`로 마크하고, 실행 직렬성은 advisory lock 또는 `SELECT ... FOR UPDATE SKIP LOCKED`로 DB 수준에서 보강.
14. **PostgreSQL/RustFS Docker 생명주기 직접 관리 금지**: 이 저장소는 이미 동작 중인 DB와 bucket에 접속만 한다. 구동·정지·재시작 절차는 이 저장소의 문서나 스크립트에 두지 않는다.
15. **`gdal` 바인딩을 시스템 GDAL과 다른 버전으로 설치 금지**: Python `gdal`은 C++ 확장 wheel이라 시스템 `libgdal-dev`와 ABI가 일치해야 한다. 항상 `pip install "gdal==$(gdal-config --version)"`로 시스템 버전에 핀하고, 운영·CI는 `osgeo/gdal:ubuntu-small-*` 베이스 이미지로 시스템 GDAL과 바인딩을 한 번에 묶는다. `pip install gdal>=...`로 임의 버전을 가져오면 `ImportError: undefined symbol` 또는 segfault가 난다 (구 ADR-008 → 본 §4 룰로 통합).
16. **base 예외명을 `KorTravelGeoError` 외 다른 이름으로 두지 말 것**: 패키지 식별자(`kortravelgeo`)와 일관되게 base 예외는 `KorTravelGeoError`로 고정한다. `AddrKrError` 같은 옛 이름이나 장기 호환 alias를 만들지 않는다 (구 ADR-014 → 본 §4 룰로 통합).
17. **`src/kortravel/__init__.py` 생성 금지**: `kortravel`는 PEP 420 implicit namespace package로 둔다. parent `kortravel` 패키지에 `__init__.py`를 두면 namespace 병합을 막아 향후 `kortravel.*` 다른 배포 패키지와 충돌한다. setuptools는 namespace discovery(`namespaces = true`)로 `kortravelgeo`를 패키징한다 (구 ADR-015 → 본 §4 룰로 통합).

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
- [ ] 프론트엔드 작업이면 `kor-travel-geo-ui`에서 `npx react-doctor@latest . --offline --verbose --json` 실행 후 경고를 수정하고 재실행
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신
- [ ] DTO/스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
