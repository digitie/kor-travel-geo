# PR #69~#75 post-merge 리뷰 audit/fixup

## 범위

- 확인 시각: 2026-05-29 KST
- 확인 대상: PR #69, #70, #71, #72, #73, #74, #75
- 확인 표면: `gh pr view --json comments,reviews,latestReviews`, GraphQL `reviewThreads`
- 결과: 대상 PR 모두 merged, formal review 각 1건, conversation comment 0건, current review thread 0건

## 반영 요약

| PR | 리뷰 핵심 | 이번 반영 |
|----|-----------|-----------|
| #69 | v2 `distance_m`, confidence 의미, source enum, point precision, bbox 의미 | 이미 PR #69 후속 commit에서 `CandidateV2.distance_m`, reverse 거리 기반 confidence, `point_precision`, API reference를 반영했다. 이번 문서에서는 현재 `V2Source`가 구현 출처(`local`/`vworld`/`juso`/`cache`)만 나타내며 Kakao/Naver/Google은 직접 wrapper가 아니라 schema 참고 대상임을 재확인했다. |
| #70 | `package-lock`의 `maplibre-vworld` SSH URL, 표본/전수 범위, `reason_code` 어휘, sample list 중복 조회 | lockfile `resolved`를 `git+https`로 되돌렸다. T-053 문서에 `ops.consistency_case_samples`가 report 캡처 표본용임을 명시하고, 전수 위반 export는 별도 후속으로 뒀다. `reason_code`는 UI 권장 어휘 + 서버 자유 문자열임을 문서화했다. `AsyncAddressClient.list_consistency_case_samples()`는 결과가 0건일 때만 report 존재 여부를 추가 조회하도록 바꿨다. |
| #71 | helper MV 단독 stale 위험, T-055 sizing 반영 | `docs/t061-slim-text-search.md`, `docs/backend-package.md`, `docs/data-model.md`에 `mv_geocode_target` raw 단독 refresh 금지를 명시했다. T-055 문서에 helper total 2,426MiB, swap temp +11.67GiB, GIN build 메모리/temp 확인 항목을 추가했다. |
| #72 | upload cleanup active-ref snapshot과 `rmtree` 사이 TOCTOU | T-050 문서에 T-059 전까지 cleanup cron을 load enqueue와 겹치지 않게 단독 스케줄로 두고, T-059에서 `uploads cleanup`도 advisory lock 대상에 포함한다고 명시했다. |
| #73 | callback retry 멱등성, secret 미설정 시 외부 검증 불가 | T-046/T-050 문서에 replay 방어는 `(timestamp, callback_id)`, retry 중복 방지는 `(artifact_id, event)` stable key로 처리해야 한다고 명시했다. 외부 검증 가능한 callback에는 `KRADDR_GEO_BACKUP_CALLBACK_SECRET`이 필수임을 강조했다. |
| #74 | `SizeProgressProbe.sample()`이 매 line마다 directory rglob/stat | `SizeProgressProbe`에 sample cache/throttle을 추가했다. interval 안에서는 마지막 sample을 재사용하고 `force=True`로 강제 갱신할 수 있다. 단위 테스트로 캐시와 강제 갱신을 고정했다. |
| #75 | MV swap 이후 release ledger 부분 성공 창, ERROR gate 위치, `count(*)` 중복, concurrent release 정책, 테스트 취약성 | load-batch ERROR gate를 swap 이전 `ensure_load_batch_release_gate()`로 옮겼다. release 기록 hook은 post-swap gate raise를 제거했다. `mv_hash`는 row_counts의 `mv_geocode_target` count를 재사용해 대형 MV 두 번 count를 피한다. T-050 문서에 transaction 경계와 manual rebuild release 의도를 명시했고, source 문자열 테스트는 UI 한글 문구 의존을 제거했다. |

## 보류한 항목

- PR #70의 전체 위반 모집단 export job은 T-053 1차 범위를 넘어서므로 후속으로 남겼다.
- PR #70의 `reason_code` 서버 enum 승격은 운영 집계 요구가 커질 때 결정한다. 현재는 직접 API 호출 유연성을 유지한다.
- PR #71의 helper MV 자동 동기화 트리거/이벤트는 PostgreSQL MV 구조상 운영 runbook 명시를 우선한다.
- PR #72의 cross-process cleanup lock은 T-059에서 `load`/`refresh mv`/`backup`/`restore` lock 표준화와 함께 구현한다.
- PR #75의 실제 PostgreSQL constraint integration test는 T-050 마지막 항목으로 유지한다. 이번 PR은 post-merge 리뷰에서 바로 고칠 수 있는 hook 위치와 중복 count를 먼저 줄인다.

## 검증 기준

- `python -m ruff check .`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest -q`
- `python -m mypy --no-incremental src/kraddr/geo`
- `lint-imports`
- `cd kraddr-geo-ui && npm run lint && npm run type-check && npm run test && npm run build`
