# CLAUDE.md — 프로젝트 컨텍스트

이 파일은 Claude Code가 매 세션 시작 시 자동으로 읽는다.
프로젝트 규칙은 `AGENTS.md`에, 아키텍처는 `docs/architecture.md`에 있다.
이 파일은 **현재 상태**와 **세션 간 연속성**에 집중한다.

## 프로젝트 현황 (2026-05-24)

한국 주소 지오코딩 라이브러리+REST API. PostgreSQL+PostGIS 백엔드.
T-001~T-026 완료 (PR #11, #12 merged). 프론트엔드(`kraddr-geo-ui`) 부트스트랩 완료.

### 현재 작업

- **T-027** (PR #13, 브랜치 `claude/t027-docker-fullload-plan`):
  실 데이터 전체 적재 검증. Docker PostGIS + ext4 bind mount.
  - 상태: 계획+스크립트 작성 완료 (커밋 4개), 실제 적재는 미수행.
  - 이번 세션에서 추가: `kraddr-geo init-db` CLI 명령, `--copy-data` 단계, bind mount 전환, 복구 문서.
  - 다음 단계: 로컬 WSL에서 `--copy-data` → 적재 → C1~C10 검증.

### 잔존 기술 부채 (PR #12 리뷰 LOW)

PR #12 리뷰(GitHub 코멘트 참조)에서 C1/C2/H1~H3/M1~M5는 `7a0fa07`에서 수정됨.
아래 LOW 3건은 미수정:

- L1: `proxy/route.ts` — `forwardedHeaders()`가 `cookie`/`authorization`도 전달. 내부망 전용이라 실질 위험 낮음.
- L2: `ReverseDebugger.tsx` — 빈 입력 시 `Number('')=0`으로 아프리카 해상 표시. `NaN` 미처리.
- L3: `ConsistencyPanel.tsx` — `loadReports()`/`openReport()`에 try/catch 없음. API 실패 시 UI 에러 상태 없음.

### 브랜치 정리

머지 완료된 리모트 브랜치 (삭제 가능):
- `claude/move-progress-to-v1-t9qM4` — main과 동일. 삭제 권장.
- `claude/spec-review-polish` — PR #8 merged.
- `claude/spec-fixups-table-count-pnu` — PR merged.
- `claude/epost-15000302-clarify` — PR merged.
- `codex/t017-text-primary-load` — PR #10 merged.
- `codex/t020-cli-api-openapi` — PR #11 merged.
- `codex/t026-frontend-admin-ui` — PR #12 merged.
- `codex/package-settings-dto` — PR merged.

### 후속 백로그

- T-028: 일변동 ZIP 증분 로더
- T-029: `jibun_rnaddrkor_*` 활용 여부 ADR
- T-030: 상세주소 동 도형/건물 도형 로더 검토

## 로컬 개발 환경

```
~/kraddr-geo-data/              # WSL ext4 — 성능 최적 (NTFS 아님)
├── juso/                       # 주소DB 작업 사본 (--copy-data로 생성)
├── epost/                      # 우편번호 데이터
└── pgdata/                     # PostgreSQL bind mount (컨테이너 삭제해도 유지)

F:\dev\python-kraddr-geo\data\  # NTFS 원본 보관
```

Docker:
```bash
docker compose -p kraddr-geo-t027 up -d   # 기동
docker compose -p kraddr-geo-t027 down    # 중지 (pgdata 유지)
```

## 데이터 기준월

| 자료 | 기준월 | 환경변수 |
|------|--------|----------|
| 도로명주소 한글 전체분 | 202603 | `JUSO_YYYYMM` |
| 위치정보요약DB | 202604 | `LOCSUM_YYYYMM` |
| 내비게이션용DB | 202604 | `NAVI_YYYYMM` |

기준월이 다르므로 C10 정합성 검증에서 WARN/ERROR 가능 — 버그 아님.

## 빠른 검증 명령

```bash
# 백엔드
python -m pytest -q
python -m ruff check .
python -m mypy src/kraddr/geo scripts/export_openapi.py
lint-imports

# 프론트엔드
cd kraddr-geo-ui && npm run lint && npm run type-check && npm run test && npm run build

# OpenAPI drift
python scripts/export_openapi.py --check --output openapi.json

# 전체 적재 (WSL + Docker)
bash scripts/fullload_test.sh --copy-data   # NTFS→ext4 복사 (최초 1회)
bash scripts/fullload_test.sh               # 적재+검증
PLAN_ONLY=1 bash scripts/fullload_test.sh   # 경로만 확인 (dry run)
```

## 주요 결정 사항

- ADR-001: PostgreSQL+PostGIS (SpatiaLite에서 전환)
- ADR-002: async-only (`AsyncAddressClient`)
- ADR-004: raw SQL, ORM 매핑 전용
- ADR-007: 텍스트 정본 우선, SHP 보조
- ADR-017: batch DAG (`load_batch_id`, `parent_job_id`)
- ADR-019: Next.js 16 보안 하한선

## 환경 복구

Windows 재설치 후 복구 순서: `docs/dev-environment-recovery.md` 참조.
