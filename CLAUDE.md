# CLAUDE.md — 프로젝트 컨텍스트

이 파일은 Claude Code가 매 세션 시작 시 자동으로 읽는다. **현재 상태**와 **세션 간 연속성**에
집중하고, 세부는 아래 정본 문서로 위임한다.

| 무엇 | 정본 |
|------|------|
| 에이전트 매뉴얼 (작업 전 필독) | `SKILL.md` |
| 목표·작업 규칙 (Think Before Coding / Simplicity / Surgical 등) | `AGENTS.md` |
| 아키텍처 | `docs/architecture/architecture.md` |
| 열린 백로그 / 완료 이력 / 진척·"다음 한 작업" | `docs/tasks.md` · `docs/tasks-done.md` · `docs/resume.md` |
| ADR (결정 기록) | `docs/adr/` (색인 `docs/adr/README.md`) — 옛 `docs/decisions.md`는 stub |
| 로컬 포트·접속 설정 | `docs/ports.md` |
| 개발 환경 (NTFS main + WSL 미러, worktree) | `docs/dev-environment.md` |

## 프로젝트 현황 (2026-06-18)

한국 주소 지오코딩 라이브러리+REST API (`kortravelgeo`, CLI `ktgctl`, env prefix `KTG_*`,
DB `kor_travel_geo`). PostgreSQL+PostGIS 백엔드 + `kor-travel-geo-ui` 프론트엔드.
v1(vworld 호환)·v2(자체 확장) API를 동시 운영하고, 전국 실 데이터 적재·검증을 완료했다(T-027).

활발히 개발 중이다 — **현재 진행 중 작업과 다음 할 일은 `docs/resume.md`와 `docs/tasks.md`가
정본**이므로 세션 시작 시 이 둘을 먼저 읽는다. 완료 이력은 `docs/tasks-done.md`.
이 Claude worktree는 idle 시 `agent/claude-idle`(origin/main 동기화)이며,
새 작업은 여기서 작업 branch(`agent/claude-*`)를 새로 따서 진행한다.

### 보류 (외부 조건)

- **T-063** N150/Odroid 실측 — 실제 장비가 준비되면 runbook으로 full-load / SQL·REST benchmark /
  MV refresh·swap / backup·restore를 최소 3회씩 측정한다. 하드웨어가 없으면 진행하지 않는다.

## 로컬 개발 환경 (NTFS main + WSL ext4 테스트 미러, ADR-041)

Git source of truth는 **NTFS** worktree다(편집·branch·commit·PR 기준). `pip`/`npm test`/`uvicorn`
같은 설치·장기 실행은 **WSL ext4 테스트 미러**에서 한다. 경로·worktree 목록·rsync 절차 상세는
`docs/dev-environment.md`.

- main 저장소: `F:/dev/python-kraddr-geo` (main 동기화 + worktree 관리)
- 에이전트별 고정 worktree(ADR-034/041): `F:/dev/kor-travel-geo-{claude,codex,antigravity,opencode}`
- WSL ext4 미러: rsync 사본(대용량 data는 심볼릭 링크). 미러 셸에서 `source scripts/agent_env.sh`를
  먼저 실행하면 `TMPDIR`·venv·Node PATH가 한 번에 맞춰진다.

### 로컬 포트 (ADR-048, `docs/ports.md` 정본)

이 저장소는 PostgreSQL/PostGIS·RustFS를 직접 구동하지 않고 `kor-travel-docker-manager`의
공용 인프라에 접속만 한다. 애플리케이션(API/UI)은 로컬 단독 실행과 Docker 실행을 같은 포트로 맞춘다.

| 표면 | host 포트 | 비고 |
|------|-----------|------|
| FastAPI 백엔드 | `12501` | `uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 12501` |
| `kor-travel-geo-ui` | `12505` | `npm run dev -- --port 12505`, Playwright base URL도 12505 |
| PostgreSQL + PostGIS (공용) | `5432` | DSN `postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo` |
| RustFS S3 API / console | `12101` / `12105` | `KTG_RUSTFS_ENDPOINT_URL` 기준값 |

## 데이터 기준월

원천별 기준월은 `JUSO_YYYYMM`(도로명주소 한글 전체분)·`LOCSUM_YYYYMM`(위치정보요약DB)·
`NAVI_YYYYMM`(내비게이션용DB) 등 환경변수로 지정한다. 원천마다 기준월이 다르면 C10 정합성
검증에서 WARN/ERROR가 날 수 있고, 이는 원천 자료 품질 이슈일 뿐 버그가 아니다.
**현재 혼합 기준월의 실제 값은 `docs/resume.md`** 를 본다.

## 빠른 검증 명령

설치·장기 실행은 WSL ext4 미러에서, 편집·branch·commit·PR은 NTFS worktree에서. 단계별 런북은
`docs/runbooks/agent-workflow.md`. 미러 셸에서 `source scripts/agent_env.sh`를 먼저 실행한다.

```bash
# 백엔드 (ext4 미러)
pytest -q
ruff check .
mypy src/kortravelgeo scripts/export_openapi.py
lint-imports
python scripts/export_openapi.py --check --output openapi.json   # OpenAPI drift

# 프론트엔드 (Windows Node 권장 — Playwright/브라우저)
cd kor-travel-geo-ui && npm run lint && npm run type-check && npm run test && npm run build
# WSL에서 정적 검증만: scripts/frontend_check.sh  (Windows npm shim이면 즉시 실패)
```

### CodeGraph 코드 인텔리전스

코드 구조·호출 관계·영향도 질의는 **CodeGraph MCP 서버**(`.mcp.json`의 `codegraph`,
도구 `mcp__codegraph__*`)로 한다 — 코드 작성·수정 전 `codegraph_context`/`codegraph_explore`로
먼저 확인한다. NTFS worktree는 파일 watcher가 비활성이므로 branch 전환·pull·rebase 뒤
인덱스를 수동 sync한다.

```bash
codegraph sync && codegraph status
```

## 주요 결정 사항 (전체: `docs/adr/`, 현재 ADR-001~063)

핵심 구조 결정만 발췌한다. 순수 개발 규칙 ADR은 `SKILL.md`로 이관됐고, 전체 색인·분류는
`docs/adr/README.md`가 정본이다.

- ADR-001: PostgreSQL+PostGIS (SpatiaLite에서 전환)
- ADR-004: ORM 위에 raw SQL Repository
- ADR-007: `mv_geocode_target`은 건물당 대표 출입구 1건
- ADR-012: 텍스트 정본 1차 + SHP polygon 보조 하이브리드
- ADR-017: batch DAG(`load_batch_id`, `parent_job_id`) + 정합성 게이트 후 MV swap
- ADR-019: Next.js 16 보안 하한선
- ADR-033: 운영 메타데이터는 `ops` 스키마 감사·스냅샷·릴리스 테이블로 관리
- ADR-034 / ADR-041: AI 에이전트 고정 worktree + CodeGraph 인덱스 / NTFS main + WSL ext4 미러
- ADR-036: 적재 완료 DB restore는 같은 cluster `ALTER DATABASE RENAME` hot-swap 1차
- ADR-037: 외부 IP 호출 REST API는 대한민국 IP만 허용 (GeoIP gate)
- ADR-038 / ADR-039: API v1(vworld 호환)·v2(자체 통합) 분리 / Python 라이브러리는 후보 목록 API만 공개
- ADR-048: 로컬 API/UI 포트는 Docker 실행과 같은 12501/12505를 사용
- ADR-063: 디버그 UI 지도는 GitHub `maplibre-vworld-react` 패키지를 소비

## 환경 복구 / 세션 연속성

- 프로젝트 상태의 source of truth는 **Git branch와 PR, `docs/tasks.md`·`docs/resume.md`**다.
- Windows 재설치 후 복구 순서: `docs/windows-reinstall-recovery.md`, `docs/dev-environment-recovery.md`.
- **Windows 네이티브 git 주의**: WSL에서 생성된 worktree는 `.git` 포인터가 `/mnt/f/...` 경로라
  Windows git이 인식하지 못할 수 있다. `git -C <main-repo> worktree repair <worktree>`로
  Windows 경로(`F:/...`)로 복구한다(다른 worktree에서 같은 증상이 보이면 동일 명령).
