# PR #69~#80 post-merge 리뷰 audit/fixup

## 범위

- 확인 시각: 2026-05-29 KST
- 확인 대상: PR #69부터 PR #80까지
- 확인 표면: `gh pr view --json comments,reviews,latestReviews`, GraphQL `reviewThreads`
- 결과: 대상 PR 모두 merged, conversation comment 0건, current review thread 0건

## 반영 요약

| PR | 리뷰 핵심 | 반영 |
|----|-----------|------|
| #69 | v2 `distance_m`, confidence 의미, `point_precision`, source enum | 기존 PR #76 반영 상태를 재확인했다. `CandidateV2.distance_m`, 거리 기반 reverse confidence, `point_precision`, v2 문서가 이미 main에 있다. Kakao/Naver/Google은 live wrapper가 아니라 schema 참고 대상이므로 `V2Source`는 현재 구현 출처만 둔다. |
| #70 | T-053 표본/전수 범위, lockfile URL, `reason_code`, sample 조회 최적화 | 기존 PR #76 반영 상태를 재확인했다. 전수 export는 후속 범위로 보류한다. |
| #71 | helper MV raw refresh 금지, T-055 sizing | 기존 PR #76 반영 상태를 재확인했다. |
| #72 | upload cleanup TOCTOU | T-059 advisory lock 범위에 남겨 둔다. T-050 문서에는 cron 단독 스케줄 권고가 이미 있다. |
| #73 | callback retry 멱등성, secret 미설정 시 외부 검증 불가 | 기존 PR #76 반영 상태를 재확인했다. |
| #74 | `SizeProgressProbe` directory sample hot-path | 기존 PR #76에서 sample cache/throttle이 반영된 상태를 재확인했다. |
| #75 | serving release hook transaction 경계, gate 위치, `count(*)` 중복 | 기존 PR #76 반영 상태를 재확인했다. release ledger 실패 창은 문서화된 운영 repair 대상으로 유지한다. |
| #76 | PR #69~#75 review follow-up PR | formal review/comment/thread 없음. |
| #77 | 수동 table stats capture가 lock 충돌 시 `[]` 성공 응답처럼 보임 | 수동 API/클라이언트 capture는 lock 충돌 시 `409 E0409`를 반환하고, scheduler만 `skip_if_locked=True`로 조용히 건너뛰도록 분리했다. |
| #78 | `replace_current` maintenance window가 소비되지 않고, gate 통과 audit가 없음 | window는 기간 gate로 유지한다고 문서화했다. 대신 각 `replace_current` 인가 통과를 `ops.audit_events(action='maintenance_window.authorize')`로 기록한다. |
| #79 | 실제 PostgreSQL 제약 테스트의 extension/disposable DB guard | PR #79 머지 전 반영 상태를 재확인했다. |
| #80 | restore hot-swap 자동 alias 이중 `now()`, 빈 inventory, alias 길이, maintenance DB 설정 | PR #80 머지 전 반영 상태를 재확인했다. |

## 보류한 항목

- PR #70의 전수 위반 export job은 T-053 1차 범위를 넘어서 후속으로 둔다.
- PR #72의 cleanup/load enqueue cross-process TOCTOU는 T-059에서 `uploads cleanup`을 같은 advisory lock 표준에 포함해 닫는다.
- PR #78의 maintenance window single-use 소비는 이번 PR에서 도입하지 않는다. 현재 모델은 기간 gate이고, 반복 인가는 audit event로 추적한다.
- PR #75의 release ledger 실패 후 수동 repair 자동화는 hot-swap 실행 표면과 함께 후속으로 다룬다.

## 검증

- `ruff check src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py tests/unit/test_ops_metadata.py`
- `pytest tests/unit/test_ops_metadata.py tests/unit/test_backup_restore.py -q` -> `22 passed`
- `mypy --no-incremental src/kortravelgeo/infra/admin_repo.py src/kortravelgeo/client.py src/kortravelgeo/infra/backup.py`
- `ruff check .`, `pytest -q` -> `257 passed, 8 skipped`, `mypy --no-incremental src/kortravelgeo`, `lint-imports`
