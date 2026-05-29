# PR #69~#82 post-merge 리뷰 audit/fixup

## 범위

- 확인 시각: 2026-05-29 KST
- 확인 대상: PR #69부터 PR #82까지
- 확인 표면: `gh pr view --json comments,reviews,latestReviews`, GraphQL `reviewThreads`
- 결과: 대상 PR 모두 merged, conversation comment 0건, current review thread 0건

## 반영 요약

| PR | 리뷰 핵심 | 반영 |
|----|-----------|------|
| #69~#75 | v2 candidate schema, T-053 표본 범위, helper MV 운영 경고, callback retry, backup progress, release hook | PR #76과 `docs/postmerge-review-fixups-pr69-pr75.md` 반영 상태를 재확인했다. |
| #76 | PR #69~#75 review follow-up PR | formal review/comment/thread 없음. |
| #77 | 수동 table stats capture lock 충돌을 빈 성공 응답과 구분 | PR #81 반영 상태를 재확인했다. 추가로 scheduler 호출부에 `skip_if_locked=True`를 명시해 조용한 skip 의도를 고정했다. |
| #78 | `replace_current` maintenance window gate 통과 audit | PR #81에서 audit event를 추가했으나, PR #81 리뷰에서 실제 PostgreSQL CHECK 제약 위반이 발견됐다. 이번 PR에서 `actor_type="job"`을 허용값인 `system`으로 바꿔 `ops.audit_events.actor_type` CHECK와 맞췄다. |
| #79 | 실제 PostgreSQL 제약 테스트 guard | PR #79 머지 전 반영 상태를 재확인했다. |
| #80 | restore hot-swap plan edge case | PR #80 머지 전 반영 상태를 재확인했다. |
| #81 | `maintenance_window.authorize` audit의 `actor_type="job"` CHECK 위반 | 이번 PR에서 `actor_type="system"`으로 수정하고 source contract 테스트를 추가했다. |
| #82 | T-059 advisory lock review | PR #82 머지 전 follow-up commit에서 미사용 `wait` 경로 제거, `OPS_TABLE_STATS` enum 제거, queue `lock_conflict` progress event, kind 간 table 경합 범위 문서화를 반영했다. |

## 보류한 항목

- PR #70의 전수 위반 export job은 T-053 1차 범위를 넘어서 후속으로 둔다.
- PR #75의 release ledger 실패 후 수동 repair 자동화는 hot-swap 실행 표면과 함께 후속으로 다룬다.
- PR #78의 maintenance window single-use 소비는 도입하지 않는다. 현재 모델은 기간 gate이고, 반복 인가는 audit event로 추적한다.
- PR #82의 서로 다른 job kind가 같은 물리 table을 쓰는 cross-process 경합은 table 단위 공유 namespace 후속 후보로 둔다.

## 검증

- `ruff check src/kraddr/geo/infra/backup.py src/kraddr/geo/api/app.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q`
- `mypy --no-incremental src/kraddr/geo/infra/backup.py src/kraddr/geo/api/app.py`

- `ruff check .`
- `pytest -q` → `261 passed, 8 skipped`
- `mypy --no-incremental src/kraddr/geo`
- `lint-imports`
