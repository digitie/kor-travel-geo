# AGENTS.md

## 목표

`kor-travel-geo`는 대한민국 영토를 대상으로 하는 지오코딩·리버스 지오코딩 라이브러리이자 REST API다.

- **원천 데이터**: 행정안전부 "주소기반산업지원서비스"([business.juso.go.kr](https://business.juso.go.kr/))가 제공하는 원천 데이터를 가공·적재해 사용한다.
- **REST API (외부 활용)**: 두 가지 API 표면을 제공한다.
  - **v1** — vworld.kr의 지오코딩·리버스 지오코딩 API와 **100% 호환**을 목표로 한다.
  - **v2** — 자체 설계 API로, v1보다 폭넓은 기능을 제공한다.
- **운용**: 지도정보 원천 데이터 관리·DB 생성·백업·복원·기능 테스트를 비전문가도 다룰 수 있도록 **admin UI와 CLI** 인터페이스로 제공한다.

## Think Before Coding

- 요청이 모호할 때는 해석을 조용히 정하지 말 것
- 중요한 가정은 숨기지 말고 드러낼 것
- 해석에 따라 구현 방향이 크게 달라지면 그 차이를 먼저 표면화할 것
- 안전하게 진행하기 어려울 정도로 혼란스러우면 추측하지 말고 확인할 것

## Simplicity First

- 요청을 완전히 해결하는 최소한의 코드만 작성할 것
- 요청되지 않은 기능을 추가하지 말 것
- 일회성 용도를 위해 추상화를 만들지 말 것
- 구체적인 필요 없이 설정 가능성이나 유연성을 늘리지 말 것
- 구현이 문제에 비해 커졌다고 느껴지면 줄일 것

## Surgical Changes

- 요청을 처리하는 데 필요한 코드만 변경할 것
- 작업이 요구하지 않으면 주변 로직까지 다시 쓰지 말 것
- 관련 없는 코드의 포맷, 이름, 스타일을 건드리지 말 것
- 사용자가 더 넓은 변경을 원한 것이 아니라면 기존 패턴을 맞출 것
- 관련 없는 문제를 발견하면 패치에 섞지 말고 따로 언급할 것

## Goal-Driven Execution

- 모호한 요청을 구체적이고 검증 가능한 결과로 바꿀 것
- 버그 수정은 재현 없이 바로 신뢰하지 말 것
- 리팩터링은 동작 보존을 전제로 전후 기대를 확인할 것
- 넓고 막연한 점검보다 목적이 분명한 검증을 선호할 것
- 완전한 검증이 불가능하면 무엇이 아직 미검증인지 밝힐 것

## Practical Bias

- 비단순 작업에서는 성급함보다 신중함을 우선할 것
- 변경 내역은 리뷰 가능한 범위와 요청 범위에 가깝게 유지할 것
- 아주 단순하고 명백한 한 줄 작업은 과하게 무겁게 다루지 말 것

## 문서 언어 정책

이 저장소의 모든 Markdown/RST 문서는 한글로 작성한다. 공식 API 필드명, 코드 식별자, 명령어, URL, 제공자 원문처럼 그대로 보존해야 하는 값만 영어를 유지한다. 새 문서나 기존 문서를 수정할 때도 이 규칙을 우선한다.

## 역할

이 저장소(GitHub 이름 `kor-travel-geo`, Python 패키지 `kortravelgeo`)는 도로명주소 전자지도(PDF 사양)를 PostgreSQL + PostGIS로 적재해 제공하는 **한국 주소 지오코딩 라이브러리·REST API**다. 사용자 대상 UI가 아닌 디버깅/관리 UI는 별도 Node.js 패키지 `kor-travel-geo-ui`(Next.js 16 + Tailwind + MapLibre GL JS + VWorld WMTS)로 운영한다.

이전(v1) SpatiaLite + SQLite 기반 구현은 동일한 `kortravelgeo` 패키지였지만 `v1` 브랜치에 보존되어 있다. `main`은 PostgreSQL + PostGIS 기반 새 사양으로 처음부터 다시 구현한다(ADR-001).

## 식별자 (혼동 방지)

| 항목 | 값 |
|------|----|
| GitHub 저장소 이름 | `kor-travel-geo` |
| Python import | `from kortravelgeo import ...` |
| CLI 명령 | `ktgctl ...` |
| 환경변수 prefix | `KTG_*` |
| PostgreSQL DB 이름 | `kor_travel_geo` (dot 불가) |
| 프론트엔드 패키지 | `kor-travel-geo-ui` (Node.js) |

## 개발 환경 정책 (PC, WSL)

PC 개발의 Git source of truth는 NTFS의 `F:\dev\kor-travel-geo` 계열 checkout이다(ADR-041). 단, Python/Node 의존성 설치, 테스트, 장기 실행 검증은 NTFS worktree를 WSL ext4 테스트 미러로 복사한 뒤 수행한다.

- **메인 repo**: NTFS `/mnt/f/dev/kor-travel-geo/` (`F:\dev\kor-travel-geo`)
- **에이전트 worktree**: NTFS `/mnt/f/dev/kor-travel-geo-codex`, `/mnt/f/dev/kor-travel-geo-claude`, `/mnt/f/dev/kor-travel-geo-antigravity`
- **테스트 미러**: WSL ext4 `~/dev/kor-travel-geo-<agent>-test/` 같은 임시 복사본. `rsync --delete`로 갱신하고 여기서는 commit/push하지 않는다.
- **데이터(`data/`)**: 대용량 Juso 원천은 NTFS 공용 루트 `F:\dev\geodata\juso`(`/mnt/f/dev/geodata/juso`)를 기준으로 둔다. ext4 테스트 미러에서는 `data -> /mnt/f/dev/geodata` 심볼릭 링크를 두면 기존 `data/juso` 상대경로가 같은 원천을 본다. 현재 쓰지 않는 원천은 `F:\dev\geodata\juso\unused\`에 보존한다.
- **카피 정책**: 작업 시작/검증 전 NTFS worktree → ext4 테스트 미러로 복사한다. 작업 완료 후 별도 ext4 → NTFS 역카피를 source-of-truth 절차로 쓰지 않는다.
- **Git 실행 기준**: NTFS worktree의 Git metadata는 Windows Git 기준(`F:\...`)을 유지한다. WSL 테스트 미러에서 실행하는 벤치마크·운영 스크립트가 Git commit/branch를 기록해야 하면 Windows `git.exe`와 `F:/dev/kor-travel-geo-*` 경로를 사용한다. WSL `git`이 읽히도록 `.git`/`gitdir` 포인터를 `/mnt/f/...`로 바꾸지 않는다.
- **PostgreSQL/RustFS 접속**: 이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동·정지·재시작하지 않는다. 이미 동작 중인 DB와 bucket에 `KTG_PG_DSN`, `KTG_RUSTFS_*` 설정으로 접속해 사용한다.
- **로컬 키**: `.env`, `kor-travel-geo-ui/.env.local`, `.claude/settings.local.json` 등은 각 NTFS worktree에 복사하되 Git에 커밋하지 않는다.
- **프론트엔드 실행**: `kor-travel-geo-ui`의 의존성 설치, `next dev`/`next start`, lint, type-check, unit test, build, React Doctor는 WSL ext4 테스트 미러의 Linux Node/npm에서 실행한다.
- **Playwright**: e2e 실행과 브라우저는 Windows Node/브라우저에서만 수행한다. WSL에서는 Playwright를 실행하지 않고, Windows Playwright를 WSL UI 서버(`--hostname 0.0.0.0`)에 붙인다.

## 에이전트 공용 runbook (필독)

`docs/runbooks/` — Claude/Codex/Antigravity가 공유하는 운영 runbook. 작업 전 두 개는 훑는다:

- [`docs/runbooks/agent-workflow.md`](docs/runbooks/agent-workflow.md) — 표준 1-PR 흐름(worktree → 브랜치 → NTFS 편집 → WSL 4 게이트(`pytest`/`ruff`/`mypy`/`lint-imports`) → PR → CI green → 머지 → 동기화) + 갱신 필수 문서.
- [`docs/runbooks/agent-failure-patterns.md`](docs/runbooks/agent-failure-patterns.md) — 본 repo 반복 실패 패턴(CI/로컬 괴리, 자연키 `::` 캐스팅, 스키마 한정, upstream drift, 테스트 격리 등)과 회피·복구. 게이트가 깨지면 여기부터.

인덱스: [`docs/runbooks/README.md`](docs/runbooks/README.md). 환경 1차 문서는 `docs/dev-environment.md` / `docs/codegraph-worktree.md` / `docs/agent-guide.md`.

## 에이전트별 고정 worktree와 CodeGraph

AI 에이전트는 같은 checkout을 번갈아 쓰지 않고, NTFS의 `/mnt/f/dev` 아래 고정 worktree를 유지한다(ADR-041). `geo-*` 접두사는 더 이상 쓰지 않고 `kor-travel-geo-*` 접두사로 통일한다.

| 에이전트 | 고정 worktree | idle branch |
|----------|---------------|-------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` | `agent/codex-idle` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` | `agent/claude-idle` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` | `agent/antigravity-idle` |

- worktree는 에이전트별로 1회만 생성하고, 작업마다 해당 worktree 안에서 새 branch만 만든다.
- 예: `git fetch origin main && git switch -c agent/codex-next origin/main`
- 같은 branch를 여러 worktree에서 checkout하지 않는다. branch 이름에는 `agent/<agent>-<task>`처럼 소유자를 넣는다.
- CodeGraph는 worktree마다 1회 `codegraph init -i`로 초기화하고, 이후 branch 전환·pull·merge 뒤에는 재초기화하지 않고 `codegraph sync`로 유지한다. NTFS `/mnt` worktree에서는 live watch가 비활성화될 수 있으므로 수동 `sync`를 더 엄격히 지킨다.
- 동기화 상태는 `codegraph status`로 확인한다. `codegraph init -i`는 최초 1회 인덱싱용이고, 평상시 상태 확인용 명령은 아니다.
- 프로젝트 루트의 `.codex/config.toml`은 CodeGraph MCP stdio 서버를 등록한다. Codex Desktop 재시작 전에는 현재 세션 도구로 노출되지 않을 수 있으나, 설정 파일은 유지한다.
- `kor-travel-geo-ui` 컴포넌트 또는 공용 UI primitive를 수정하기 전에는 CodeGraph MCP의 `codegraph_explore` 도구로 영향 범위(호출자, 참조 파일, 테스트 표면)를 먼저 확인한다. MCP가 아직 노출되지 않은 과도기 세션에서는 그 사실을 작업 로그에 남기고 `codegraph sync`, `codegraph status`, `codegraph context`/`codegraph impact` CLI로 임시 확인한다.
- `.codegraph/`와 `.claude/`는 로컬 상태/secret이므로 Git에 커밋하지 않는다. `.gitignore`에 포함되어 있어야 한다.

작업 전에 반드시 다음을 읽는다:

1. `README.md` — 프로젝트 개요와 빠른 시작
2. `SKILL.md` — DO NOT 룰, 자주 묻는 작업, 도메인 어휘
3. `docs/architecture/architecture.md` — 두 패키지의 관계, 의존 방향
4. `docs/resume.md` — 현재 진척도와 "다음 한 작업"
5. `docs/adr/README.md` — 관련 ADR (인덱스 포인터 `docs/decisions.md`)

Windows 재설치, WSL 초기화, 새 세션에서 이어받는 상황이면 `docs/windows-reinstall-recovery.md`도 함께 읽는다. T-027 실 데이터 전체 적재는 이미 완료됐으므로 별도 금지선이 없다. 빈 DB가 필요하면 백업 복원(ADR-030/ADR-036) 또는 `scripts/fullload_test.sh` 재실행으로 처리한다. T-213/T-214 기준 원천과 산출물 경로는 `docs/t213-data-preservation.md`를 우선 참고하고, 과거 T-027 기준월 분리와 산출물 경로는 `docs/t027-fullload-plan.md`를 참고한다.

## 지시 우선순위

1. 사용자 요청
2. 이 `AGENTS.md`
3. `SKILL.md`
4. `docs/architecture/architecture.md`, `docs/adr/README.md`, `docs/architecture/data-model.md`, `docs/architecture/backend-package.md`, `docs/architecture/frontend-package.md`, `docs/agent-guide.md`, `docs/architecture/external-apis.md`
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
10. **프론트엔드 패키지에 DB 드라이버 추가 금지** — `kor-travel-geo-ui`는 REST API만 호출.
11. **PostgreSQL/RustFS 직접 구동 금지** — 이 저장소에 DB/RustFS Docker 구동·정지·재시작 절차나 스크립트를 추가하지 않는다. 필요한 것은 접속 설정뿐이다.

## 제공자 API 사용 원칙

- 외부 API 관련 작업은 단순 전달용 래퍼/어댑터/게이트웨이 지양 원칙을 먼저 확인하고 문서/코드에 반영한 뒤 진행한다.
- 하위 사용자에게는 안정된 공개 클라이언트(`AsyncAddressClient`), 타입 모델(`kortravelgeo.dto`), 열거형(`ZipSource` 등), 보조 함수를 제공한다.
- 단순 전달용 래퍼, 장기 호환 별칭, 임시 facade를 만들지 않는다.
- vworld·juso·epost의 발급/호출 절차는 `docs/architecture/external-apis.md`에 모아 둔다. 외부 API 호출은 `httpx.AsyncClient` + `tenacity` 재시도, 회로차단, 쿼터 보호를 갖춘다. 프론트엔드 VWorld/MapLibre 연동 문제가 발생하면 `digitie/maplibre-vworld-js`도 적극 수정 대상에 포함한다.
- 응답 구조는 vworld와 1:1로 호환되도록 유지하고 자체 확장은 `x_extension` 키에만 둔다.

## 작업 후 체크리스트

`SKILL.md` §7과 동일:

- [ ] `pytest -q` 통과
- [ ] `ruff check .` / `mypy --strict` / `lint-imports` 통과
- [ ] 프론트엔드 작업이면 `kor-travel-geo-ui`에서 `npx react-doctor@latest . --offline --verbose --json` 실행 후 경고를 수정하고 재실행
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
python -m mypy src/kortravelgeo
lint-imports

# 프론트엔드 (kor-travel-geo-ui 부트스트랩 후)
cd kor-travel-geo-ui && npm run lint && npm run type-check && npm run test && npm run build
cd kor-travel-geo-ui && npx react-doctor@latest . --offline --verbose --json
```
