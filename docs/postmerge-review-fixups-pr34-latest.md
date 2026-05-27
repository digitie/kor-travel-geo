# PR #34~#47 리뷰 코멘트 audit/fixup

## 범위

2026-05-27에 GitHub PR #34부터 #47까지 다음 표면을 다시 확인했다.

- PR conversation issue comment
- formal review body
- inline review thread
- GraphQL `reviewThreads(isResolved, isOutdated)`
- 현재 코드/문서 반영 상태

확인 결과 PR #34~#43은 post-merge 리뷰 코멘트가 있었고, PR #44는 Windows Playwright 확인 메모만 있었다. PR #45~#47에는 확인 시점 기준 신규 리뷰 코멘트가 없었다. GraphQL review thread 기준 unresolved current thread는 전 PR에서 0개였다.

## 사용한 확인 쿼리

향후 같은 audit을 반복할 때는 `gh pr view`만 보지 말고 review thread 상태를 함께 본다.

```bash
gh api graphql \
  -f owner=digitie \
  -f name=python-kraddr-geo \
  -F number=<PR_NUMBER> \
  -f query='
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      number
      title
      state
      merged
      comments(first:50) { nodes { author { login } body createdAt url } }
      reviews(last:50) { nodes { author { login } state body submittedAt url } }
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          comments(first:20) {
            nodes { databaseId author { login } body createdAt url path line originalLine }
          }
        }
      }
    }
  }
}'
```

## PR별 판정

| PR | 상태 | 리뷰 코멘트 요약 | 이번 반영 |
|----|------|------------------|-----------|
| #34 | merged | T-043 audit 결과 분류 기준과 GraphQL query template 보강 권장 | 이 문서에 분류 기준과 query template을 남김 |
| #35 | merged | T-045 source set UX의 confirmation token, upload cleanup, `source_set` typed schema, CLI prompt, C10 기준 | confirmation token/CLI prompt는 T-045 구현으로 반영됨. 이번 PR에서 `LoadJobStatus.source_set`/`ConsistencyReport.source_set`을 `dict[str, Any]`로 넓히고 OpenAPI/TS 타입을 갱신 |
| #36 | merged | T-046 backup/restore progress, zstd, callback 보안, empty DB, `ops.artifacts` 수렴 | T-046 구현에서 path allowlist, `pg_dump -Fd`, zstd, manifest/checksum, 새 DB guard, download token, `ops.artifacts` 연결 반영. callback HMAC/retry는 후속 hardening |
| #37 | merged | T-047 p95/p99 목표, concurrency envelope, EXPLAIN 분리, 보조 MV trigger | ADR-031/docs에 목표와 보조 MV 후보가 반영됨. 실제 benchmark harness는 T-047에서 계속 진행 |
| #38 | merged | ADR-028 최신 정의 명확화, dependency SHA 갱신 검증, WSL Linux Node 표준화 | ADR-028에 ADR-032 우선 문구 추가, `maplibre-vworld-js` 최신 `7947b2e...`로 갱신, `scripts/frontend_check.sh` 추가 |
| #39 | merged | ops active release partial unique, `ops.artifacts`, redaction, maintenance window, backup 영향 | T-049 구현으로 대부분 반영됨. 이번 PR에서 감사 job FK 정책을 보강 |
| #40 | merged | README 법적 고지와 provider별 약관 링크 관찰 | README/외부 API 문서의 기존 고지를 유지. provider별 링크 표는 별도 정책 문서 보강 후보 |
| #41 | merged | baseline gate 재검증 실패 지적 | 이후 PR에서 CI/로컬 검증 재수행. 이번 PR에서도 backend/frontend 검증을 다시 수행 |
| #42 | merged | frontend 검증 누락, WSL Linux Node helper 권장 | `scripts/frontend_check.sh`와 문서 보강으로 반영 |
| #43 | merged | ops snapshot/release hook, redaction audit, table stats cron, confirmation flow, `audit_events.job_id ON DELETE SET NULL` | `audit_events.job_id` FK를 `ON DELETE NO ACTION`으로 변경하고 Alembic 0008 추가. 나머지는 후속 운영 hardening |
| #44 | merged | Windows Playwright 확인 메모 | 이번 지시에 맞춰 Playwright는 Windows에서만 수행한다는 문서를 유지 |
| #45 | merged | 신규 코멘트 없음 | 조치 없음 |
| #46 | merged | 신규 코멘트 없음 | 조치 없음 |
| #47 | open | 확인 시점 신규 코멘트 없음 | 이 audit 결과를 PR #47에 추가로 푸시 |

## 이번 PR에서 직접 반영한 항목

### 1. `source_set` nested JSON 타입 보존

PR #35 M3은 `LoadJobStatus.source_set`이 단순 `dict[str, str]`로 약화되면 `SourceSetPlan` 요약, `yyyymm_by_kind`, `mixed_yyyymm_acknowledged`, checksum 같은 중첩 JSON을 API/프론트엔드 타입에서 잃는다고 지적했다.

반영:

- `dto.admin.LoadJobStatus.source_set`: `dict[str, Any] | None`
- `dto.admin.ConsistencyReportSummary.source_set`: `dict[str, Any]`
- `core.protocols.LoadJobRow.source_set`: `dict[str, Any] | None`
- `core.protocols.ConsistencyReportRow.source_set`: `dict[str, Any]`
- `loaders.consistency.run_all_cases(source_set=...)`: `dict[str, Any] | None`
- `openapi.json`, `kraddr-geo-ui/types/api.gen.ts`, `kraddr-geo-ui/lib/api.ts` 갱신
- DTO 단위 테스트에 nested `source_set` 회귀 케이스 추가

### 2. `ops.audit_events.job_id` FK 보존

PR #43 M5는 `ops.audit_events.job_id ON DELETE SET NULL`이 audit append-only 정책과 충돌한다고 지적했다. 감사 이벤트의 job 연결이 조용히 끊기면 "어떤 작업 때문에 생긴 의사결정인지"를 잃는다.

반영:

- fresh DDL: `ops.audit_events.job_id TEXT REFERENCES load_jobs(job_id) ON DELETE NO ACTION`
- Alembic `0008_pr34_review_followups.py`: 기존 FK를 drop 후 `ON DELETE NO ACTION`으로 재생성
- downgrade는 기존 동작인 `ON DELETE SET NULL`로 되돌림
- `docs/t049-ops-metadata-schema.md`, `docs/data-model.md`, ADR-033에 retention/archive 정책 전까지 삭제를 DB가 막는다고 명시
- unit test에서 fresh DDL과 Alembic migration 문자열을 고정

### 3. `maplibre-vworld-js` 최신성 재확인

PR #38 M2는 dependency SHA를 바꾸는 PR마다 최신 upstream 확인과 소비자 검증을 요구했다. 2026-05-27 재확인 시 upstream `main`은 `7947b2e170ddb36ab28a7a9034dd4dbf8f18370b`였다.

반영:

- `kraddr-geo-ui/package.json`, `package-lock.json`의 `maplibre-vworld` SHA를 `7947b2e...`로 갱신
- lockfile `resolved`는 CI SSH key 의존을 피하기 위해 `git+https` 유지
- `docs/frontend-package.md`, `docs/external-apis.md`, ADR-020/028/032, `docs/resume.md`, `docs/tasks.md`, `kraddr-geo-ui/README.md`의 현재 SHA 갱신
- npm audit moderate 7건은 기존 baseline과 동일하게 남음

### 4. 프론트엔드 검증 helper

PR #42 M1은 WSL에서 Windows `npm`이 잡혀 frontend 로컬 검증을 건너뛴 문제를 지적했다.

반영:

- `scripts/frontend_check.sh` 추가
- Windows `npm` 또는 `.exe/.cmd` 경로가 잡히면 즉시 실패
- Linux Node/npm에서 `gen:types`, lint, type-check, unit test, build를 순서대로 실행
- `--install`을 주면 `npm ci`부터 수행
- Playwright는 사용자 지시에 따라 Windows Node/브라우저에서만 실행한다고 `docs/dev-environment.md`와 `kraddr-geo-ui/README.md`에 명시

## 후속으로 남긴 항목

| 출처 | 항목 | 이관 |
|------|------|------|
| PR #35 M2 | upload set cleanup TTL, 실행 중 job이 참조하는 upload set lock/grace period | T-050 운영 hardening |
| PR #36 M1/M3 | backup/restore sub-progress 고도화, callback HMAC/retry/replay protection | T-050 운영 hardening |
| PR #37 M1~M4 | 실제 benchmark harness, latency target enforcement, plan/latency run 분리, query군별 보조 MV trigger | T-047 |
| PR #38 M2 | SHA 갱신 때 Windows Playwright smoke 결과 기록 | T-044 또는 지도 UI 변경 PR |
| PR #40 L3 | provider별 약관 링크 표 보강 | 문서 hardening 후보 |
| PR #43 M1/M3/M4/L24 | full-load/MV/restore job 완료 hook에서 snapshot/release 자동 생성, table stats cron, destructive confirmation flow 통합, 실제 PG constraint integration test | T-050 운영 hardening |

## 검증 방침

- 백엔드 계약 변경은 `pytest`, `ruff`, `mypy`, `lint-imports`, OpenAPI drift check로 검증한다.
- `source_set` 타입 변경은 `scripts/export_openapi.py`와 `kraddr-geo-ui npm run gen:types`를 함께 수행한다.
- 프론트엔드 unit/type/build 검증은 WSL Linux Node/npm에서 `scripts/frontend_check.sh`로 수행한다.
- Playwright와 실제 브라우저 렌더링은 Windows Node/브라우저에서만 수행한다.
