# AGENTS.md

## 문서 언어 정책

이 저장소의 모든 Markdown/RST 문서는 한글로 작성한다. 공식 API 필드명, 코드 식별자, 명령어, URL, 제공자 원문처럼 그대로 보존해야 하는 값만 영어를 유지한다. 새 문서나 기존 문서를 수정할 때도 이 규칙을 우선한다.

## 역할

이 저장소(GitHub 이름 `python-kraddr-geo`, Python 패키지 `kraddr.geo`)는 도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS로 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 `kraddr-geo-ui`(Next.js 16 + Tailwind + MapLibre GL JS + VWorld WMTS)로 운영한다.

이전(v1) SpatiaLite + SQLite 기반 구현은 동일한 `kraddr.geo` 패키지였지만 `v1` 브랜치에 보존되어 있다. `main`은 PostgreSQL + PostGIS 기반 새 사양으로 처음부터 다시 구현한다(ADR-001).

## 식별자 (혼동 방지)

| 항목 | 값 |
|------|----|
| GitHub 저장소 이름 | `python-kraddr-geo` |
| Python import | `from kraddr.geo import ...` |
| CLI 명령 | `kraddr-geo ...` |
| 환경변수 prefix | `KRADDR_GEO_*` |
| PostgreSQL DB 이름 | `kraddr_geo` (dot 불가) |
| 프론트엔드 패키지 | `kraddr-geo-ui` (Node.js) |

## 개발 환경 정책 (PC, WSL)

PC 개발의 Git source of truth는 NTFS의 `F:\dev\python-kraddr-geo` 계열 checkout이다(ADR-041). 단, Python/Node 의존성 설치, 테스트, 장기 실행 검증은 NTFS worktree를 WSL ext4 테스트 미러로 복사한 뒤 수행한다.

- **메인 repo**: NTFS `/mnt/f/dev/python-kraddr-geo/` (`F:\dev\python-kraddr-geo`)
- **에이전트 worktree**: NTFS `/mnt/f/dev/python-kraddr-geo-codex`, `/mnt/f/dev/python-kraddr-geo-claude`, `/mnt/f/dev/python-kraddr-geo-antigravity`
- **테스트 미러**: WSL ext4 `~/dev/python-kraddr-geo-<agent>-test/` 같은 임시 복사본. `rsync --delete`로 갱신하고 여기서는 commit/push하지 않는다.
- **데이터(`data/`)**: NTFS main repo의 `data/`를 기준으로 두고, ext4 테스트 미러에서는 절대경로 또는 필요한 경우 심볼릭 링크로 참조한다.
- **카피 정책**: 작업 시작/검증 전 NTFS worktree → ext4 테스트 미러로 복사한다. 작업 완료 후 별도 ext4 → NTFS 역카피를 source-of-truth 절차로 쓰지 않는다.
- **Git 실행 기준**: NTFS worktree의 Git metadata는 Windows Git 기준(`F:\...`)을 유지한다. WSL 테스트 미러에서 실행하는 벤치마크·운영 스크립트가 Git commit/branch를 기록해야 하면 Windows `git.exe`와 `F:/dev/python-kraddr-geo-*` 경로를 사용한다. WSL `git`이 읽히도록 `.git`/`gitdir` 포인터를 `/mnt/f/...`로 바꾸지 않는다.
- **PostgreSQL 검증 DB**: 별도 요청이 없으면 지난 T-027 최종 적재 Docker DB(`kraddr-geo-t027-final`, `KRADDR_PGDATA=/home/digitie/kraddr-geo-data/pgdata-final-20260529`, host port `15434`)를 재사용한다. 빈 DB 클린 적재/클린 스키마 검증은 사용자가 명시적으로 요구할 때만 새 pgdata로 수행한다.
- **로컬 키**: `.env`, `kraddr-geo-ui/.env.local`, `.claude/settings.local.json` 등은 각 NTFS worktree에 복사하되 Git에 커밋하지 않는다.
- **Playwright**: Windows Node/브라우저에서만 실행한다. WSL Playwright는 사용하지 않는다.

## 에이전트별 고정 worktree와 CodeGraph

AI 에이전트는 같은 checkout을 번갈아 쓰지 않고, NTFS의 `/mnt/f/dev` 아래 고정 worktree를 유지한다(ADR-041). `geo-*` 접두사는 더 이상 쓰지 않고 `python-kraddr-geo-*` 접두사로 통일한다.

| 에이전트 | 고정 worktree | idle branch |
|----------|---------------|-------------|
| ChatGPT Codex | `/mnt/f/dev/python-kraddr-geo-codex` | `agent/codex-idle` |
| Claude Code | `/mnt/f/dev/python-kraddr-geo-claude` | `agent/claude-idle` |
| Google Antigravity 2.0 | `/mnt/f/dev/python-kraddr-geo-antigravity` | `agent/antigravity-idle` |

- worktree는 에이전트별로 1회만 생성하고, 작업마다 해당 worktree 안에서 새 branch만 만든다.
- 예: `git fetch origin main && git switch -c agent/codex-next origin/main`
- 같은 branch를 여러 worktree에서 checkout하지 않는다. branch 이름에는 `agent/<agent>-<task>`처럼 소유자를 넣는다.
- CodeGraph는 worktree마다 1회 `codegraph init -i`로 초기화하고, 이후 branch 전환·pull·merge 뒤에는 재초기화하지 않고 `codegraph sync`로 유지한다. NTFS `/mnt` worktree에서는 live watch가 비활성화될 수 있으므로 수동 `sync`를 더 엄격히 지킨다.
- 동기화 상태는 `codegraph status`로 확인한다. `codegraph init -i`는 최초 1회 인덱싱용이고, 평상시 상태 확인용 명령은 아니다.
- 프로젝트 루트의 `.codex/config.toml`은 CodeGraph MCP stdio 서버를 등록한다. Codex Desktop 재시작 전에는 현재 세션 도구로 노출되지 않을 수 있으나, 설정 파일은 유지한다.
- `kraddr-geo-ui` 컴포넌트 또는 공용 UI primitive를 수정하기 전에는 CodeGraph MCP의 `codegraph_explore` 도구로 영향 범위(호출자, 참조 파일, 테스트 표면)를 먼저 확인한다. MCP가 아직 노출되지 않은 과도기 세션에서는 그 사실을 작업 로그에 남기고 `codegraph sync`, `codegraph status`, `codegraph context`/`codegraph impact` CLI로 임시 확인한다.
- `.codegraph/`와 `.claude/`는 로컬 상태/secret이므로 Git에 커밋하지 않는다. `.gitignore`에 포함되어 있어야 한다.

작업 전에 반드시 다음을 읽는다:

1. `README.md` — 프로젝트 개요와 빠른 시작
2. `SKILL.md` — DO NOT 룰, 자주 묻는 작업, 도메인 어휘
3. `docs/architecture.md` — 두 패키지의 관계, 의존 방향
4. `docs/resume.md` — 현재 진척도와 "다음 한 작업"
5. `docs/decisions.md` — 관련 ADR

Windows 재설치, WSL 초기화, 새 세션에서 이어받는 상황이면 `docs/windows-reinstall-recovery.md`도 함께 읽는다. T-027 실 데이터 전체 적재는 이미 완료됐으므로 별도 금지선이 없다. 빈 DB가 필요하면 백업 복원(ADR-030/ADR-036) 또는 `scripts/fullload_test.sh` 재실행으로 처리하고, 기준월 분리와 산출물 경로는 `docs/t027-fullload-plan.md`를 참고한다.

## 지시 우선순위

1. 사용자 요청
2. 이 `AGENTS.md`
3. `SKILL.md`
4. `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/backend-package.md`, `docs/frontend-package.md`, `docs/agent-guide.md`, `docs/external-apis.md`
5. `README.md` 및 나머지 `docs/`
6. 기존 코드와 테스트
7. 최소한의, 되돌릴 수 있는 가정

## 절대 하지 말 것 (DO NOT)

`SKILL.md` §4와 동일하지만 핵심만 다시 적는다:

1. **의존 방향 역행 금지** — `dto → core → infra → client → api/cli` 한 방향. `import-linter`가 강제.
2. **동기 인터페이스 추가 금지** — `AsyncAddressClient`만 둔다 (ADR-002).
3. **`pg_trgm.similarity_threshold` 전역 변경 금지** — 트랜잭션 단위로만 `SET LOCAL`.
4. **ORM에 비즈니스 로직 금지** — `infra/models.py`는 매핑만. 쿼리는 raw SQL (ADR-004).
5. **좌표 순서 혼동 금지** — 외부 인터페이스는 모두 `(lon, lat)`.
6. **`MVM_RES_CD` 매핑 하드코드 금지** — `load_codes` 테이블 또는 settings.
7. **응답에 `x_extension` 외 자체 필드 추가 금지** — vworld 호환성을 깬다 (ADR-003).
8. **외부 API 키 평문 커밋 금지** — 모두 `SecretStr`. `.env`는 권한 600 또는 systemd `EnvironmentFile`/vault.
9. **`ogr2ogr` subprocess 호출 금지** — GDAL Python binding 사용. CP949 디코딩 명시 (ADR-005).
10. **프론트엔드 패키지에 DB 드라이버 추가 금지** — `kraddr-geo-ui`는 REST API만 호출.

## 제공자 API 사용 원칙

- 외부 API 관련 작업은 단순 전달용 래퍼/어댑터/게이트웨이 지양 원칙을 먼저 확인하고 문서/코드에 반영한 뒤 진행한다.
- 하위 사용자에게는 안정된 공개 클라이언트(`AsyncAddressClient`), 타입 모델(`kraddr.geo.dto`), 열거형(`ZipSource` 등), 보조 함수를 제공한다.
- 단순 전달용 래퍼, 장기 호환 별칭, 임시 facade를 만들지 않는다.
- vworld·juso·epost의 발급/호출 절차는 `docs/external-apis.md`에 모아 둔다. 외부 API 호출은 `httpx.AsyncClient` + `tenacity` 재시도, 회로차단, 쿼터 보호를 갖춘다. 프론트엔드 VWorld/MapLibre 연동 문제가 발생하면 `digitie/maplibre-vworld-js`도 적극 수정 대상에 포함한다.
- 응답 구조는 vworld와 1:1로 호환되도록 유지하고 자체 확장은 `x_extension` 키에만 둔다.

## 작업 후 체크리스트

`SKILL.md` §7과 동일:

- [ ] `pytest -q` 통과
- [ ] `ruff check .` / `mypy --strict` / `lint-imports` 통과
- [ ] 프론트엔드 작업이면 `kraddr-geo-ui`에서 `npx react-doctor@latest . --offline --verbose --json` 실행 후 경고를 수정하고 재실행
- [ ] `docs/journal.md`에 작업 항목 추가 (역시간순)
- [ ] `docs/resume.md`의 진척도 갱신
- [ ] 의사결정이 있었다면 `docs/decisions.md`에 ADR 추가
- [ ] 사용자 가시 변경이면 `CHANGELOG.md` 갱신
- [ ] DTO/스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`

## 검증

```bash
# 백엔드 (구현 시점에 활성화)
python -m pytest -q
python -m ruff check .
python -m mypy src/kraddr/geo
lint-imports

# 프론트엔드 (kraddr-geo-ui 부트스트랩 후)
cd kraddr-geo-ui && npm run lint && npm run type-check && npm run test && npm run build
cd kraddr-geo-ui && npx react-doctor@latest . --offline --verbose --json
```
