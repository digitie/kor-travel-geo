# tasks.md — 백로그

열린 `[ ]`(진행 중/대기/보류) task만 두는 백로그. 완료·종료 이력은
[`docs/tasks-done.md`](tasks-done.md), 진척·"다음 한 작업"은 [`docs/resume.md`](resume.md)가
정본이다. 작성·유지 규약(역할 표·라우팅·ID 스킴·entry 형식)은
[`docs/tasks-rule.md`](tasks-rule.md), PR/리뷰 루프·병행 운영 같은 작업 진행 규칙은
[`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다. 현재 상태와 세션 연속성은
[`CLAUDE.md`](../CLAUDE.md)가 정본이다.

작업 항목은 `T-NNN` 형식의 ID로 관리한다(번호 배정은 tasks-rule.md §3). 새 작업은
"대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은
`tasks-done.md` 상단에 누적한다.

## 진행 중

### T-290 — geo 독립 Dagster 오케스트레이션 이관 (epic)

결정 [ADR-066](adr/066-geo-independent-dagster-orchestration.md), 구현 정본
[architecture/dagster-boundary.md](architecture/dagster-boundary.md), 단계·분해·contract·e2e 게이트는
[dagster-migration-plan.md](dagster-migration-plan.md)가 정본. 통합 브랜치
`agent/claude-dagster-migration`(전 milestone 완료 후 main 머지). 두 에이전트 A(실행엔진/백엔드)·
B(배포/관측/e2e) 병렬. **기준: 최소수정 X, 미래지향(유지보수성·안정성·완성도·품질·최적구조).**

- [x] **T-290a** (A) — `kortravelgeo_dagster` 패키지 스캐폴드 + resources + `mv_refresh` @job (M1) — #419
- [x] **T-290b** (A) — Dagster 배포(Dockerfile/compose/메타DB/포트 12502) + n150 mv_refresh run SUCCESS (M1) — #421·#422, manager #47
- [x] **T-290c** (A) — `load_jobs` executor/lease + recovery split + reconciler + cancel 골격 (M1, 4단계 게이트) — #420, 리뷰 후속 #424
- [x] **T-290d** (B) — API GraphQL observe 라우터 (M2) — #417
- [x] **T-290e** (B) — admin `/admin/dagster` 관측 화면 (M2) — #418
- [x] **T-290f** (A) — scheduled backup @schedule 온램프 + @run_failure_sensor + 알림 (M2)
- [x] **T-290g** (A) — `db_backup` Dagster 실행 + verify/copy/restore_drill (M3) — #464 계열
- [x] **T-290h** (B) — run detail 로그·artifact 링크 + 실패/overdue 알림 UI (M3) — #471
- [x] **T-290i** (A) — `db_restore`(새 빈 DB) Dagster 실행, hot-swap 수동 유지, RetryPolicy off (M4) — #472
- [x] **T-290j** (A) — loader + `full_load_batch` Dagster 실행(`batch_dag` 미러 + GDAL 이미지) (M5) — #476/#477
- [x] **T-290k** (A) — in-process 큐/이벤트루프 우회 은퇴, ADR-006/011 superseded (M5) — #479·#480·#481·#482·#483(DDL 0026)
- [x] **T-290l** (B) — live e2e harness를 Dagster 관측까지 확장 + 최종 회귀 (M5) — 전국 full-load 스테이징 라이브 e2e 성공(mv=6,416,637), cutover 배포·검증

**✅ T-290 에픽 완료 (2026-07-12)** — 통합 브랜치 `agent/claude-dagster-migration`(HEAD `9bcb949`)에 병합·n150
cutover 배포·검증 완료. 실행이 프로덕션에서 **Dagster-only**(in-process drain 삭제). live UI e2e 게이트 #1~#4
전부 통과(관측+온램프·backup 실행·restore 새DB·full-load+큐은퇴+최종회귀). 상세는 `tasks-done.md`·`resume.md`.

**후속 완료**: `integration→main` 머지(#485, merge commit `658a54e`) 및 geo Dagster 공개
URL(`geo-dagster.digitie.mywire.org`)을 관리자 `/admin/dagster` 화면에 iframe으로 임베드
(`DagsterEmbed` + `resolveDagsterPublicUrl`, 서버측 `KTG_DAGSTER_PUBLIC_URL` 해석; Dagster UI가
frame-busting 헤더를 보내지 않아 CSP 변경 불필요). 남은 것은 UI 컨테이너 재배포로 라이브 반영하는 단계뿐.

(그 외 진행 중 작업 없음. T-177A~T-177H·T-183 완료 — `tasks-done.md` 참조.)

## 대기

> 번호 배정 순서·ID 스킴(ADR-050)은 [`docs/tasks-rule.md`](tasks-rule.md) §3을,
> 두 에이전트 병행 권장 순서·병행 운영 원칙(PR/리뷰 루프)은
> [`docs/runbooks/agent-workflow.md`](runbooks/agent-workflow.md)를 본다.

T-178a~T-178f Claude Code 리뷰 후속과 T-177 파일 기반 full-load e2e 재검증은 모두 닫혔다.
T-177은 T-073 shell script에 맞추지 않고, opt-in pytest 통합/e2e가 실제 파일을 읽어 scratch
PostgreSQL DB를 구축하는 방향으로 완료했다. 상세 계획과 Task 분해는
[`docs/t177-file-driven-full-load-e2e-plan.md`](t177-file-driven-full-load-e2e-plan.md), 최종
성능 수용은 [`docs/t177h-benchmark-acceptance.md`](t177h-benchmark-acceptance.md)가
정본이다.

### 선행 리뷰 후속

2026-07-27 GitHub 열린 이슈 감사(15건 조사, `tasks-done.md` 참조) 결과 남은 미해결 리뷰 후속 6건
**전부 완료·종료** — 이슈 #298은 PR #491, #302는 PR #493, #299는 PR #495, #252는 PR #497, #307은
PR #499, #201은 PR #502(아래 tasks-done.md 참조). 근거는 각 이슈 본문·코멘트 참조.

### 신규 기능

- [ ] **T-291** — 데이터셋 버전 외부 공개 API + admin 버전 관측 (변경 감지). 외부 소비자가
  주소 DB 변경 여부·이력을 확인하고 자기 파생 데이터를 갱신할 수 있도록, active serving
  release에서 파생한 opaque 토큰을 `POST /v2/dataset/version`(known_version 조건부 폴링)·
  `POST /v2/dataset/history`로 공개한다. 인증은 기존 공개 API 키(ADR-064)+GeoIP 게이트
  (ADR-037) 재사용, 1차 스키마 변경 0건(기존 ops 테이블 사영), admin은 기존 releases 표면
  확장(읽기 전용)+외부 응답 미리보기. 결정
  [ADR-067](adr/067-external-dataset-version-api.md), 정본
  [t291-dataset-version-external-api.md](t291-dataset-version-external-api.md).
  - [x] **T-291a** — 서빙 전환 기록 완결 (**외부 공개의 선행 조건**, ADR-067 D0) — PR #529,
    n150 live e2e 완료. 위반 5류(CLI `all-sidos --refresh`·postload `execute_safe`·restore
    `replace_current`·직접 서빙 base table 단독 적재 pobox/sppn/polygon/bulk·benchmark
    스크립트 shadow-swap) 전부가 release를 기록한다. `record_mv_refresh_release`에
    `release_kind` override, `record_restore_candidate`에 `activate` 파라미터를 추가했다.
    `daily_delta`는 `ktgctl refresh mv --daily-delta`/REST `daily_delta=true`(문서화된
    daily-delta 운영 흐름의 정본 경로)와 `daily-juso`/`daily-parcel-links --refresh`,
    `shp --mode delta`에서 라벨링한다. n150에서 REST `daily_delta=true` refresh를 실제
    실행해 `ops.serving_releases`에 `release_kind=daily_delta` active row가 기록됨을
    확인했다(release `2c4272d6-6acf-44ce-89e7-99a011d7a862`). 적대적 리뷰 2건에서
    `all-sidos --no-refresh` 거짓 양성, 검증 테스트 2건의 공백을 찾아 수정했다. 남은
    should-fix 2건은 T-292·T-293으로 분리했다.
  - [ ] **T-291b** — 토큰·기준월 정규화기(4형태)·공용 사영·keyset 커서 (backend 내부만).
  - [ ] **T-291c** — 외부 v2 엔드포인트 + 전용 admission scope + openapi/gen:types +
    api-reference 4건(신규 문서·README·llm-summary·v2 공통 규약 Cache-Control 조항).
  - [ ] **T-291d** — admin 확장: `ServingRelease` additive 필드 + OpsPanel releases 표
    컬럼·상세·미리보기·curl + live e2e.
  - [ ] **T-291e** — 기록 경로 위생(독립): 백업 artifact FK 기입, BackupsPanel 백업 시점
    토큰, hot-swap source_set 자체 완결화, `batch_dag` repr 열화 수정, restore drill의
    원장 `pending` 누적 정리 판단.

- [ ] **T-292** — `db_restore mode=replace_current` 정합성 검증 + 기록 데이터 정확도
  (T-291a 적대적 리뷰에서 발견, PR #529). (a) `replace_current`는 대상이 이미 서빙 중인
  현재 DB이므로 `ensure_target_database_empty`를 거치지 않는데, 실제 `pg_restore`가
  비어있지 않은 DB(특히 `ops.*` 자체를 포함)에 대해 종단간 성공하는지 확인된 적이 없다
  (기존 `test_replace_current_guards_reject_...`는 가드 거부만 검증하고
  `build_pg_restore_command`를 raise하도록 monkeypatch해 실제 실행 경로를 우회함) — 실
  disposable DB로 실제 `replace_current` 종단간 restore를 1회 이상 실행해 확인/보강한다.
  (b) `record_restore_candidate`가 기록하는 `row_counts`는 백업 시점 manifest 값이며,
  `run_restore_job`이 `run_row_count_check=True`일 때 이미 계산하는 실측
  reconcile 결과(`reconcile_block`)를 사용하지 않는다 — `activate=True`(replace_current)
  경로에서는 이 값이 "지금 서빙 중인 데이터"의 정본 기록이 되므로, `allow_partial` 등으로
  실제 결과가 manifest와 다를 때 부정확한 기록이 active release에 남는다. 가능하면 reconcile
  결과를 row_counts로 우선 사용하도록 스레딩한다.
- [ ] **T-293** — `_insert_dataset_snapshot_and_release`의 동시 호출 시 lineage 유실
  가능성 (T-291a 적대적 리뷰에서 발견, PR #529). "활성 release는 항상 1건" 불변식 자체는
  partial unique index + 무조건 실행되는 `UPDATE ... WHERE state='active'`로 보장되지만,
  두 트랜잭션이 거의 동시에 진입하면 뒤에 커밋되는 쪽의 `SELECT ... FOR UPDATE`가 이미
  `superseded`로 바뀐 원래 행에서 블록되었다가 그 행 기준으로 `previous`를 `None`으로
  결정할 수 있어 `previous_serving_release_id`/`parent_dataset_snapshot_id` 계보가
  끊길 수 있다(활성 상태 자체는 정상적으로 최종 요청이 이김). T-291a로 직접 서빙 loader·
  benchmark 스크립트 등 신규 호출 지점이 늘어 동시 호출 가능성이 커졌으므로, INSERT 직전
  재조회 또는 advisory lock 등으로 보강할지 판단한다.

### 선택 후속 (낮은 우선순위)

- **진행 중 작업 없음.** (T-219 잔여 L까지 완료 — `tasks-done.md` 참조.)

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
