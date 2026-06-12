# PR #53~#64 post-merge 리뷰 audit/fixup

## 범위

사용자 지시: T-057 종료 후 다음 작업 전에 지금까지의 PR 중 리뷰를 검토하지 않은 PR을 모두 읽고, PR 리뷰 반영을 먼저 진행한다.

마지막 별도 audit 문서는 `docs/postmerge-review-fixups-pr51-pr52.md`였으므로 이번 범위는 PR #53부터 T-057 PR #64까지로 잡았다.

확인 표면:

- `gh pr view <번호> --json comments,reviews,latestReviews`
- GitHub GraphQL `reviewThreads`(`isResolved`, `isOutdated`, file/line 포함)
- conversation comment와 formal review body

## 요약

| PR | 제목 | comment | review | thread | unresolved | 처리 |
|----|------|--------:|-------:|-------:|-----------:|------|
| #53 | T-047 search exact preflight tuning | 1 | 0 | 0 | 0 | 일부 직접 반영, 일부 후속화 |
| #54 | T-060 document PR51 PR52 review followups | 1 | 0 | 0 | 0 | 추가 조치 없음 |
| #55 | T-047 add benchmark observability artifacts | 1 | 0 | 0 | 0 | 일부 직접 반영 |
| #56 | T-047 record active observability run | 1 | 0 | 0 | 0 | 문서상 후속으로 유지 |
| #57 | T-047 document operational impact run | 1 | 0 | 0 | 0 | 일부 완료, 일부 T-050 |
| #58 | T-047 document stress benchmark | 1 | 0 | 0 | 0 | 대부분 후속 PR에서 완료 |
| #59 | T-047 add REST e2e latency benchmark | 1 | 0 | 0 | 0 | 코드 직접 반영 |
| #60 | T-047 document REST pool comparison | 1 | 0 | 0 | 0 | 후속 PR에서 대부분 완료 |
| #61 | T-047 add REST admission grid | 0 | 1 | 0 | 0 | 기존 테스트 확인, 일부 후속 |
| #62 | T-047 document REST admission repeat | 0 | 1 | 0 | 0 | 문서 직접 보강 |
| #63 | T-047 document backup archive compression | 1 | 0 | 0 | 0 | 문서와 checksum 측정 직접 반영 |
| #64 | T-057 region hint search filters | 0 | 0 | 0 | 0 | 추가 조치 없음 |

모든 PR의 unresolved review thread는 0건이었다.

## 이번 PR에서 직접 반영

### PR #53

- `rn_nrm`/`buld_nm_nrm` 정규화 규칙을 `docs/data-model.md`에 명시했다. Python `_normalize_search_query()`와 SQL 생성 컬럼이 같은 공백 제거 규칙을 써야 exact preflight가 broad trigram fallback으로 빠지지 않는다.
- shadow MV 문서의 index 목록에 `idx_mv_next_rn_nrm_exact`, `idx_mv_next_buld_nm_nrm_exact`를 추가하고, 기존 오타성 `rn_norm`/`buld_nm` 표기를 `rn_nrm`/`buld_nm_nrm`로 바로잡았다.
- benchmark corpus에 `search_fuzzy` case를 추가했다. 이는 의도적으로 exact match가 없도록 `임의불일치` suffix를 붙여 broad trigram fallback path를 계속 실행하게 한다.
- REST benchmark 변환도 `search_fuzzy`를 별도 `sql_name`으로 보존한다. 일반 `search`와 합치면 exact preflight와 broad trigram fallback의 REST latency가 섞이기 때문이다.

### PR #55

- `pg_stat_statements` 조회와 reset SQL을 `x_extension.pg_stat_statements` / `x_extension.pg_stat_statements_reset()`로 schema-qualified 처리했다.
- 단위 테스트에서 `capture_pg_stat_statements()`와 `_pg_stat_statements_status()`가 `x_extension` prefix를 쓰는지 고정했다.

### PR #59

- reverse 좌표 bounds 오류를 `PydanticCustomError("kor_travel_geo.coordinate_bounds", ...)`로 바꿨다.
- API exception handler는 더 이상 `str(exc)` 전체 문자열 매칭으로 좌표 오류를 판별하지 않고, `exc.errors()`의 structured `type`을 확인한다.
- 일반 Pydantic validation error는 계속 HTTP 400 `E0100`, 좌표 bounds는 HTTP 400 `E0102`로 매핑되는 테스트를 추가했다.

### PR #62

- REST admission repeat 문서에 "c1/c4/c16은 세 profile 모두 목표 범위라 c64 tail만 비교했다"는 설명을 추가했다.

### PR #63

- archive SHA256 단계도 직접 측정했다. `sha256sum artifacts/perf/t047-operational-impact-20260528/pgdump-dir.tar.zst` wall time은 21.76초, max RSS는 3,584KiB였다.
- `docs/t047-query-performance-tuning.md`의 백업 envelope를 `pg_dump -Fd` 2분 21.60초 + archive 33.31초 + checksum 21.76초로 보강했다.
- `docs/t046-db-backup-restore.md`와 ADR-030에 `tar.zst`는 압축률보다 단일 artifact 포장, UI 다운로드, checksum 검증 단순화가 핵심이라는 실측 해석을 추가했다.

## 후속으로 유지

| 출처 | 항목 | 후속 |
|------|------|------|
| PR #53 M4 | v2 `match_mode` 옵션 | T-052 v2 API 설계에서 `prefer_exact`/`exact_only`/`fuzzy_only` 검토 |
| PR #55 M2 | `setup_ms`와 `execute_ms` 추가 분리 | T-047 harness schema 3 후보. 현재 `execute_ms`는 transaction setup + SQL 실행을 포함한다. |
| PR #56 M1/M2 | 기존 배포 DB의 구 Alembic revision ID와 T-027 clean `upgrade head` | T-027 최종 클린 적재 전 preflight에 유지 |
| PR #57 M1/M2 | MV swap timeout/progress 정책 | T-050 운영 hardening에서 job timeout 자동 상향과 sub-progress로 처리 |
| PR #58 M2 | stress corpus와 standard corpus overlap 비율 | 다음 stress 재측정 또는 T-061 corpus 설계 시 기록 |
| PR #60 M2 | REST e2e의 HTTP/DB/pool 3분할 | REST benchmark schema 후속. 현재 SQL benchmark는 checkout/execute를 분리한다. |
| PR #61 M1/M2 | process-local admission의 운영 의미와 v2 path 포함 | T-052/T-050에서 path 설정화 또는 endpoint별 admission으로 처리 |
| PR #62 M1/M2 | 운영 query mix 기반 profile 선택, c64 SLA 정책 | T-055 하드웨어 실측 또는 운영 트래픽 관측 후 결정 |
| PR #63 M1 | `pg_dump --compress=0` + `tar.zst -19` 또는 `pg_dump --compress=zstd` 비교 | T-046/T-050 백업 hardening 후속. 대구 부분 DB로 1회 비교 가능 |

## 검증

- `/home/digitie/dev/kor-travel-geo/.venv/bin/ruff check .` → 통과.
- `PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/mypy src/kortravelgeo` → 통과.
- `PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/lint-imports` → Layered architecture kept.
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp PYTHONPATH=/home/digitie/dev/geo-codex/src:/home/digitie/dev/geo-codex /home/digitie/dev/kor-travel-geo/.venv/bin/python -m pytest -q` → 216 passed, 6 skipped, 3 warnings.
- `git diff --check` → 통과.
- `codegraph sync` → 통과.
