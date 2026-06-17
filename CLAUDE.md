# CLAUDE.md — 프로젝트 컨텍스트

이 파일은 Claude Code가 매 세션 시작 시 자동으로 읽는다.
프로젝트 규칙은 `AGENTS.md`에, 아키텍처는 `docs/architecture/architecture.md`에,
작업 백로그는 `docs/tasks.md`에, ADR은 `docs/decisions.md`에 있다.
이 파일은 **현재 상태**와 **세션 간 연속성**에 집중한다.

## 프로젝트 현황 (2026-05-31)

한국 주소 지오코딩 라이브러리+REST API. PostgreSQL+PostGIS 백엔드 + `kor-travel-geo-ui` 프론트엔드.
T-001~T-072 완료 (최신 머지: PR #105). 실 데이터 전국 적재·검증 완료.

### 현재 작업

- **진행 중 작업 없음.** `docs/tasks.md`의 "진행 중"/"대기"가 모두 비어 있다.
- 이 worktree(`/mnt/f/dev/kor-travel-geo-claude`)는 idle branch `agent/claude-idle`이며
  `origin/main`과 동기화된 깨끗한 상태다. 새 작업은 여기서 작업 branch(`agent/claude-*`)를 새로 따서 진행한다.

### 보류 (외부 조건)

- **T-063** N150/Odroid 실측 — 실제 장비가 준비되면 `docs/t055-deployment-n150-odroid.md` runbook으로
  full-load / SQL·REST benchmark / MV refresh·swap / backup·restore를 최소 3회씩 측정한다.
  하드웨어가 없으면 진행하지 않는다.

### 적재 상태 (T-027 완료)

전국 실 데이터 클린 재적재가 **이미 완료**됐다 (T-027, 2026-05-29).
- 전체 약 3,963초, `mv_geocode_target = 6,416,642`, `mv_geocode_text_search = 6,416,642`, `tl_sppn_makarea = 24,204`.
- C1~C10 정합성은 원천 자료 품질 이슈로 `severity_max=ERROR` (기준월 불일치 등 — 버그 아님).
- 상세: `docs/t027-fullload-plan.md`, `docs/t027-data-quality-followup.md`.

→ 따라서 "사용자 승인 전 Docker 기동 금지" 같은 옛 금지선은 더 이상 유효하지 않다.
재적재가 필요할 때만 `scripts/fullload_test.sh`를 다시 쓴다.

## 로컬 개발 환경 (NTFS main + WSL ext4 테스트 미러, ADR-041)

Git source of truth는 **NTFS** worktree다. `pip`/`npm test`/`uvicorn` 같은 설치·장기 실행은
**WSL ext4 테스트 미러**에서 수행한다. 상세: `docs/dev-environment.md`.

```text
/mnt/f/dev/kor-travel-geo/                 # NTFS main repo (main 동기화 + worktree 관리)
/mnt/f/dev/kor-travel-geo-claude/          # Claude Code worktree  (agent/claude-idle)
/mnt/f/dev/kor-travel-geo-codex/           # ChatGPT Codex worktree (agent/codex-idle)
/mnt/f/dev/kor-travel-geo-antigravity/     # Antigravity worktree   (agent/antigravity-idle)
~/dev/kor-travel-geo-claude-test/          # WSL ext4 테스트 미러 (rsync 사본, data는 심볼릭 링크)

/mnt/f/dev/kor-travel-geo/data/            # 대용량 원천/작업 데이터 기준 위치
```

> 옛 `geo-*` worktree 접두사와 `~/kor-travel-geo-data/` ext4 데이터 정책은 폐기됐다(T-072/ADR-041로 대체).

### 공식 로컬 포트 (ADR-040, `docs/ports.md`)

| 표면 | host 포트 | 내부 | 비고 |
|------|-----------|------|------|
| PostgreSQL + PostGIS | `15434` | 5432 | docker-compose 기본 `KTG_DB_PORT`. DSN: `postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo` |
| FastAPI 백엔드 | `8888` | 8888 | `uvicorn kortravelgeo.api.app:app --host 127.0.0.1 --port 8888` |
| `kor-travel-geo-ui` | `13088` | 3000 | Docker `-p 13088:3000`, dev `npm run dev -- --port 13088`. Playwright base URL도 13088 |

기본 포트 `5432`/`3000`은 다른 프로젝트와 충돌하기 쉬워 외부 진입점으로 쓰지 않는다.

```bash
KTG_DB_PORT=15434 docker compose up -d db   # DB 기동
docker compose down                                # 중지 (pgdata volume 유지)
```

## 데이터 기준월

| 자료 | 기준월 | 환경변수 |
|------|--------|----------|
| 도로명주소 한글 전체분 | 202603 | `JUSO_YYYYMM` |
| 위치정보요약DB | 202604 | `LOCSUM_YYYYMM` |
| 내비게이션용DB | 202604 | `NAVI_YYYYMM` |

기준월이 다르므로 C10 정합성 검증에서 WARN/ERROR 가능 — 버그 아님.

## 빠른 검증 명령

설치·장기 실행은 WSL ext4 테스트 미러에서 수행한다. NTFS worktree는 편집·branch·commit·PR 기준.
따라할 수 있는 단계별 런북은 `docs/runbooks/agent-workflow.md`. 미러 셸에서 `source scripts/agent_env.sh`를 먼저 실행하면 `TMPDIR`·venv·Node PATH가 한 번에 맞춰져 아래 명령에 `TMPDIR=...` 접두를 붙일 필요가 없다.

```bash
# 백엔드 (ext4 미러)
pytest -q
ruff check .
mypy src/kortravelgeo scripts/export_openapi.py
lint-imports

# 프론트엔드 (Windows Node 권장 — Playwright/브라우저)
cd kor-travel-geo-ui && npm run lint && npm run type-check && npm run test && npm run build
# WSL에서 정적 검증만: scripts/frontend_check.sh  (Windows npm shim이면 즉시 실패)

# OpenAPI drift
python scripts/export_openapi.py --check --output openapi.json

# CodeGraph (NTFS worktree는 watcher 비활성 → branch 전환·pull·rebase 뒤 수동 sync)
codegraph sync && codegraph status

# 전국 재적재가 필요할 때만 (적재 자체는 T-027에서 이미 완료)
bash -n scripts/fullload_test.sh            # syntax 확인
PLAN_ONLY=1 bash scripts/fullload_test.sh   # 경로만 확인 (preflight)
```

## 주요 결정 사항 (전체: `docs/decisions.md`, 현재 ADR-001~041)

- ADR-001: PostgreSQL+PostGIS (SpatiaLite에서 전환)
- ADR-002: async-only (`AsyncAddressClient`)
- ADR-004: ORM 위에 raw SQL Repository
- ADR-007: `mv_geocode_target`은 건물당 대표 출입구 1건
- ADR-012: 텍스트 정본 1차 + SHP polygon 보조 하이브리드
- ADR-017: batch DAG(`load_batch_id`, `parent_job_id`) + 정합성 게이트 후 MV swap
- ADR-019: Next.js 16 보안 하한선
- ADR-033: 운영 메타데이터는 `ops` 스키마 감사·스냅샷·릴리스 테이블로 관리
- ADR-034: AI 에이전트는 고정 Git worktree + CodeGraph 인덱스 사용
- ADR-036: 적재 완료 DB restore는 같은 cluster `ALTER DATABASE RENAME` hot-swap 1차
- ADR-037: 외부 IP 호출 REST API는 대한민국 IP만 허용 (GeoIP gate)
- ADR-038: API 표면을 v1(vworld 호환)·v2(자체 통합 candidate)로 분리
- ADR-039: Python 라이브러리는 후보 목록 API만 공개, `_v2` 접미사 제거
- ADR-040: PC/WSL 개발 환경 로컬 포트 고정 (15434 / 8888 / 13088)
- ADR-041: NTFS main repo + WSL ext4 테스트 미러

## 환경 복구 / 세션 연속성

- 프로젝트 상태의 source of truth는 **Git branch와 PR 문서, `docs/tasks.md`**다.
- Windows 재설치 후 복구 순서: `docs/windows-reinstall-recovery.md`, `docs/dev-environment-recovery.md` 참조.
- **Windows 네이티브 git 주의**: 이 worktree는 WSL에서 생성돼 `.git` 포인터가 `/mnt/f/...` 경로였고,
  Windows git이 인식하지 못했다. `git -C F:\dev\kor-travel-geo worktree repair F:\dev\kor-travel-geo-claude`로
  Windows 경로(`F:/...`)로 복구 완료(2026-05-31). 다른 worktree에서 같은 증상이 보이면 동일 명령으로 repair한다.

## 후속 백로그

현재 `docs/tasks.md` "대기"는 비어 있다. 새 작업은 거기에 `T-NNN`으로 등록한 뒤 시작한다.
