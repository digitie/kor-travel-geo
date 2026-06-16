# T-153 최종 안정화 acceptance

작성일: 2026-06-16
담당: Codex(Agent A), Claude Code(Agent B)

## 결론

T-153은 Agent A 성능·정확도 트랙과 Agent B Admin UI·백업/복원 트랙을 하나의 pre-release gate로 묶어 확인한 최종 수락 기록이다. 현재 기준에서는 geocoder, reverse geocoder, Admin UI 운영 표면, 백업/복원 기본 운영 경로를 **수락**한다.

단, 이 결론은 "새로운 release blocker 없음"이다. 이미 별도 task로 분리된 항목은 유지한다.

| 항목 | 판정 | 처리 |
|------|------|------|
| C1~C10 정합성 `ERROR` | 수락 조건부 유지 | T-213 r3 force promotion으로 알려진 source-quality 상태다. 코드 회귀로 보지 않는다. |
| C11 active serving promotion | 금지 유지 | T-137 결론대로 validation-only다. T-119는 새 증거, ADR-051 accepted, 사용자 승인 전까지 보류한다. |
| T-140 live golden corpus | 환경 의존 보류 | fixture/schema 25/25는 통과했다. live mode는 유효한 `KTG_PG_DSN`이 있는 환경에서 재실행한다. |
| 60분 live soak | 외부 실행 보류 | T-163 runner와 guard는 준비됐지만 이번 T-153에서 실제 60분 DB/API soak artifact는 만들지 않았다. |
| N150/Odroid 실측 | 외부 장비 보류 | T-055/T-247 runbook 기준으로 T-063에서 실행한다. |
| T-219/T-105 follow-up | 하위 우선순위 잔여 | v1 published contract/OpenAPI/typegen 정합과 T-105 audit 이후 ADR-060 반영 backlog는 T-153 안정화 blocker로 보지 않는다. |

## 정확도·데이터 gate

| 범위 | 근거 | 결과 |
|------|------|------|
| Golden corpus fixture | T-140 | corpus SHA-256 `0b4ff00d1a59520da3237daf57c51e9be1e870a699976f1b86e1d48482d32b99`, 25/25 통과 |
| v1/v2 대표 smoke | T-215, T-218 | geocode/search/zipcode/reverse 7개 표면 HTTP 200/`OK` |
| C1~C10 정합성 | T-215, T-218 | T-218 독립 재실행에서 T-215 count와 byte-identical, `severity_max=ERROR` 유지 |
| C11~C17 optional 검증 | T-216, T-218, T-127 | custom match set에서 runnable/skipped/failed `7/0/0`, 구조 validator 보강 완료 |
| reverse 경계·공간 조회 | T-142, T-176 | reverse/zipcode/SPPN smoke 7건 error 0, KNN/`ST_Covers`/GiST index 경로 확인 |
| search/exact/fuzzy plan | T-143, T-171 | Q4 search smoke 3건 error 0, exact branch와 trigram fallback plan 확인 |
| 입력 안전성 | T-173, T-175 | 악성 입력·좌표 bounds·모순 hint가 구조화 4xx 또는 `NOT_FOUND`로 끝남 |

T-215 기준 C1~C10 상태는 다음과 같다.

| case | severity | count |
|------|----------|------:|
| C1 | `WARN` | 33,897 |
| C2 | `ERROR` | 32,496 |
| C3 | `WARN` | 3,513,854 |
| C4 | `ERROR` | 3,416 |
| C5 | `WARN` | 202 |
| C6 | `ERROR` | 803 |
| C7 | `ERROR` | 6,815 |
| C8 | `WARN` | 24,483 |
| C9 | `OK` | 0 |
| C10 | `WARN` | 7 |

## 성능·안정성 gate

| 범위 | 근거 | 결과 |
|------|------|------|
| T-214 SQL baseline | T-214 | c64 worst p95 `Q4_SEARCH/search_fuzzy=245.895ms`, errors 0 |
| T-217 독립 SQL 재실행 | T-217 | c64 worst p95 `Q4_SEARCH/search_fuzzy=268.370ms`, errors 0, T-214~T-215 band 안 |
| T-216 REST c64 수용 | T-216 | 425 REST cases, errors 0, worst p95 `Q4_SEARCH/search_hint=415.022ms`, T-214 기준 `534.031ms` 이하 |
| pool/admission/fail-fast | T-154, T-145, T-161, T-159 | checkout timeout, admission overload, disconnect cancellation, DB fault response를 구조화 |
| p99/soak guard | T-163, T-164 | runner와 enforce guard 구현 완료. 실제 60분 live soak는 별도 운영 실행 |
| runtime warm/cache | T-156, T-162 | hot-key cache와 runtime warm runner 구현, 기본 비활성 opt-in |
| post-load maintenance | T-146 | read-only plan과 `execute-safe` 유지보수 runner, runbook 갱신 |

## API 계약·typegen gate

| 범위 | 근거 | 결과 |
|------|------|------|
| 성능 우선 v2 계약 | T-144 | `include_geometry=false`, `response_model_exclude_none=True`, geocode/search 상한 100 유지 |
| OpenAPI drift | T-144 이후 PR 검증 | `scripts/export_openapi.py --check` 통과 |
| Frontend typegen drift | T-153 현재 PR | `npm run gen:types` 후 NTFS source와 CRLF 정규화 비교에서 drift 0 |
| v1/V2 contract 후속 | T-219, T-105 | T-219 runtime wire-shape 회귀와 T-105 audit은 일부 완료. published OpenAPI/typegen 정합과 ADR-060 반영 backlog는 하위 우선순위 후속 |

## Admin UI gate

| 범위 | 근거 | 결과 |
|------|------|------|
| benchmark/validation artifact 노출 | T-265, T-222 | `/admin/ops`에서 benchmark와 C1~C17 상태를 read-only 노출 |
| source-files 상위 e2e | T-223 | Chromium 8 + Firefox 8 통과 |
| source-files 단계별 e2e | T-259~T-263 | 업로드, 대기/재개/409, 구조 검증, match set, rebuild-db 흐름 통과 |
| 백업/복원 Admin UI e2e | T-255~T-258 | backup/restore/hot-swap 접근성·회복성 e2e 완료 |
| 기존 표면 a11y/회복성 | T-227 | `/admin/source-files`, `/admin/consistency`, `/admin/ops`에서 Chromium 46 + Firefox 20 통과 |
| T-153 React Doctor | 현재 PR | hard error 3건 제거, `ok=true`, error 0, warning 16 |

현재 PR에서 정리한 React Doctor hard error는 다음이다.

- `JobProgress`의 mount 직후 prop-state sync 진단을 제거했다.
- `MatchSetComparePanel`의 TanStack Query result 객체 전체 구독을 `data` destructuring으로 좁혔다.
- `useModalA11y` effect dependency를 명시해 stale closure 경고를 제거했다.

남은 warning 16건은 T-160 이후 알려진 구조 경고다. `ManifestViewer`, `ConsistencyPanel`, `ReconcileTab`, `HotSwapTab`, `UploadTab`, `RestoreWizard`의 dialog/useReducer/component export 정리 후보이며, 이번 T-153의 release blocker로 보지 않는다.

## 백업·복원 gate

| 범위 | 근거 | 결과 |
|------|------|------|
| restore dry-run/version guard/reconcile | T-232~T-234 | archive checksum, target 복원성, PostgreSQL/PostGIS major mismatch, row count reconcile 구현 |
| round-trip restore | T-244 | backup -> restore round-trip opt-in integration 경로 구현 |
| restore-drill | T-242 | 복원 리허설 CLI/runbook 구현, live restore/drop은 T-244/T-246 계열에서 커버 |
| 장애 주입 | T-245 | checksum flip/truncated tar/checksum 위조/누락, cancel, `replace_current` guard opt-in test 구현 |
| hot-swap/rollback | T-246 | 로컬 Docker PostGIS에서 3 cases 통과, throwaway DB 잔류 0 |
| 백업/복원 benchmark | T-247 | 27행 matrix 계획/실행기 구현. 실제 장비·도구 있는 실행은 별도 |

T-246은 Claude가 완료한 결과를 acceptance 근거로만 인용한다. 사용자 지시에 따라 이 PR에서 T-246 추가 작업이나 추가 리뷰는 하지 않았다.

## 현재 PR 검증

T-153 문서와 React Doctor hard error 정리를 반영한 뒤 WSL ext4 테스트 미러에서 다음을 확인했다.

| 명령 | 결과 |
|------|------|
| `python -m pytest -q` | `997 passed, 69 skipped` |
| `python -m ruff check .` | 통과 |
| `python -m mypy src/kortravelgeo` | `Success: no issues found in 145 source files` |
| `lint-imports` | `Layered architecture KEPT` |
| `python scripts/export_openapi.py --check` | 통과 |
| `./scripts/frontend_check.sh` | `gen:types`, lint, type-check, unit `110 passed`, build 통과 |
| `npx react-doctor@latest . --offline --verbose --json` | `ok=true`, warning 16, error 0 |
| generated type drift | `api.gen.ts`, `schemas.gen.ts` 모두 CRLF 정규화 비교 drift 0 |

## 최종 판정

T-153은 완료로 닫는다. 현재 pre-release baseline에서 새 release blocker는 없다. 남은 항목은 T-119/C11 active promotion 보류, T-063 외부 장비 실측, 60분 live soak 실행, T-219 published contract 정합, T-105 audit 이후 ADR-060 반영 backlog다.
