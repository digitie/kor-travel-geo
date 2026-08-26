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

- [ ] **T-293** — `_insert_dataset_snapshot_and_release`의 동시 호출 시 lineage 유실
  가능성 (T-291a 적대적 리뷰에서 발견, PR #529). "활성 release는 항상 1건" 불변식 자체는
  partial unique index + 무조건 실행되는 `UPDATE ... WHERE state='active'`로 보장되지만,
  두 트랜잭션이 거의 동시에 진입하면 뒤에 커밋되는 쪽의 `SELECT ... FOR UPDATE`가 이미
  `superseded`로 바뀐 원래 행에서 블록되었다가 그 행 기준으로 `previous`를 `None`으로
  결정할 수 있어 `previous_serving_release_id`/`parent_dataset_snapshot_id` 계보가
  끊길 수 있다(활성 상태 자체는 정상적으로 최종 요청이 이김). T-291a로 직접 서빙 loader·
  benchmark 스크립트 등 신규 호출 지점이 늘어 동시 호출 가능성이 커졌으므로, INSERT 직전
  재조회 또는 advisory lock 등으로 보강할지 판단한다.
- [ ] **T-294** — 신뢰 admin 프록시(`kor-travel-geo-ui/app/api/proxy/[...path]/route.ts`)가
  upstream 응답 헤더를 `content-type` 하나만 골라 전달하고 나머지(`Cache-Control` 등)는 전부
  버린다(T-291d n150 live e2e에서 발견 — `dataset-version-live.spec.ts`의
  `POST /v2/dataset/version` 프록시 호출이 `Cache-Control: no-store` 부재로 실패, 실 공개 API
  직접 호출 검증으로 대체하고 이 task로 분리). 모든 admin 엔드포인트에 공통인 기존 동작이라
  T-291d가 만든 회귀는 아니다. 현재 실사용 영향은 낮다 — 이 헤더가 실제로 의미 있는
  `/v2/dataset/version`·`/v2/dataset/history`가 둘 다 POST이고, 브라우저·대부분의 HTTP
  캐시는 헤더 유무와 무관하게 POST 응답을 캐시하지 않는다. 그러나 향후 GET 기반 admin
  엔드포인트가 `ETag`/`Cache-Control`/rate-limit 헤더 같은 응답 헤더에 의존하게 되면 프록시를
  거치는 순간 조용히 사라진다 — `ALLOWED_FORWARD_HEADERS`(요청 헤더, `lib/proxy.ts`)와
  대칭되는 응답 헤더 allowlist를 `route.ts`에 추가할지, 아니면 admin 프록시 전체에 획일적으로
  `Cache-Control: no-store`를 강제할지(어차피 admin은 상호작용형이라 캐시가 필요 없음) 판단한다.
- [ ] **T-295** — `tests/integration/test_full_load_batch_dagster_roundtrip.py`의
  `_stub_leaves` 안 `fake_source` monkeypatch 스텁이 `run_source_loader`의 현재 시그니처와
  어긋난다(T-292 live-scratch-DB 게이트 실행 중 우연히 발견 — T-292와 무관, backup/restore를
  전혀 건드리지 않는 파일). `run_source_loader`(`loaders/batch_dag.py`)는 T-291a에서
  `load_batch_id: str | None = None` 키워드 인자를 얻었지만, 이 테스트의 `fake_source(engine,
  *, kind, payload, cancel_event, progress)` 스텁은 이를 받지 않아
  `TypeError: fake_source() got an unexpected keyword argument 'load_batch_id'`로 즉시
  실패한다(`test_dagster_batch_roundtrip_converges_all_children`,
  `test_dagster_batch_gate_blocks_mv_on_consistency_error` 2건). opt-in 테스트라
  `KTG_TEST_PG_DSN` 없이 도는 기본 `pytest -q`에서는 드러나지 않는다. `fake_source`에
  `load_batch_id=None` 파라미터(또는 `**_kwargs`)를 추가하면 해소.
- [ ] **T-296** — T-292가 고친 `replace_current` 자기참조 wipe 문제의 잔여 항목(우선순위
  낮음, T-292 적대적 리뷰에서 발견, 크래시는 아니고 조용한 정확도/추적성 손실). (a)
  `maintenance_window.authorize` 감사 이벤트(`ops.audit_events`)가 복원 시 함께 wipe되는데
  재기록하지 않는다 — 아무 것도 이를 다시 읽지 않아 현재는 inert로 보이지만, 감사 완결성
  관점에서 재기록 여부 판단. (b) `record_restore_candidate`가 기록하는
  `ops.dataset_snapshots.backup_artifact_id`는 FK가 없어 조용히 매달린 참조가 된다 —
  복원 대상 백업 artifact 자신은 정의상 자기 dump 안에 존재할 수 없으므로(dump 파일이
  있어야 체크섬/크기를 계산해 artifact를 만들 수 있는 선후관계), `--clean` 복원 후
  `ops.artifacts`가 백업 시점 상태로 되돌아가면 그 backup_artifact_id는 영구히 풀리지 않는다
  — "이 스냅샷이 어느 백업에서 복원됐는지" 조회가 매 실 `replace_current` 복원마다 끊긴다.
  (c) `build_pg_restore_command`에 전역으로 추가한 `--clean --if-exists`가 PostGIS
  extension을 template로 미리 설치해 둔 `new_database` 대상(빈 테이블이지만 extension은
  이미 존재)에서 `DROP EXTENSION IF EXISTS postgis` 이후 재생성이 항상 무사히 성공하는지
  실측 검증되지 않았다(`ensure_target_database_empty`는 테이블만 확인하고 extension은
  확인하지 않음) — 흔한 pg_restore+PostGIS 마찰 지점이라 별도 테스트로 확정할 가치가 있다.
- [ ] **T-297** — n150 디스크 공간 위험(2026-08-26 T-292 live restore-drill 검증 중
  실제 PostgreSQL 크래시 발생시킴) 사후 조치. 즉시 위험은 2026-08-27 해소(96%→58%,
  189G 여유 — 아래 참조), 남은 항목은 낮은 우선순위 후속.
  - 근본 원인: n150 루트 디스크(`/dev/mapper/ubuntu--vg-ubuntu--lv`, 466G)가 restore-drill
    시작 전부터 이미 98% 사용 중(13G 여유)이었다 — drill의 스크래치 대상 DB
    (`kor_travel_geo_restoretest_20260826T082157Z`, 전국 규모 backup을 `new_database` 모드로
    복원 중, 16GB까지 성장하며 다수의 GIST/btree 인덱스를 빌드하던 도중)가 디스크를 100%까지
    채웠고, PostgreSQL이 WAL을 더 쓸 수 없어 crash했다(unclean shutdown → automatic recovery).
  - 결과: PostgreSQL은 WAL redo로 자체 복구에 성공했다(69초 만에 "database system is ready to
    accept connections"). `kor-travel-geo-api-latest` 컨테이너는 복구 완료 전 접속 실패로
    3회 재시작 루프를 돌다 정상화. 사후 검증: `ops.serving_releases` active release 1건 정상,
    `mv_geocode_target` 6,416,637 row(알려진 정상값과 일치) — **데이터 손실/손상 없음** 확인.
    크래시 원인이 `pg_restore --clean --if-exists` 자체의 결함이 아니라 순수 디스크 용량
    문제임을 확인했으므로(크래시 전 4시간+ 동안 수십 개 테이블/인덱스에 걸쳐 정상 동작 관측),
    T-292는 이 증거 + 로컬 통합 테스트 전체 통과를 근거로 그대로 merge한다(사용자 승인).
  - **즉시 조치 완료 (2026-08-27)**: 남은 16GB 스크래치 restoretest DB DROP(21G 여유,
    96%) → `docker system df`로 실측하니 이 공유 호스트(n150)의 디스크 압박 대부분이
    이 프로젝트가 아니라 **Docker 이미지/빌드 캐시 누적**이었다(다른 프로젝트의 시간별
    스테이징 빌드가 정리 없이 계속 쌓임 — 예: `pinvi-pr477-stage-*` 태그가 서로 다른
    커밋 해시로 40개+ 존재, 각 ~2GB). `docker builder prune -af`(빌드 캐시, 순수
    재생성 가능·무위험) → 61.4GB 회수, 85%(68G 여유). 이어서 사용자 확인 후 `docker image
    prune -af`(어떤 컨테이너도 참조하지 않는 이미지만 삭제, 실행 중 컨테이너는 무영향) →
    추가 회수, **최종 58% 사용(189G 여유)**. 실행 중이거나 정지된 컨테이너가 참조하는
    이미지·볼륨은 전혀 건드리지 않았다(볼륨은 76개 중 32.31GB가 미참조로 잡히지만
    다른 프로젝트 데이터일 수 있어 이번엔 손대지 않음 — 필요해지면 프로젝트별 확인 후
    별도 판단). **위험 수준 해소, 최우선 아님으로 하향.**
  - **남은 후속** (낮은 우선순위): 재발 방지 — `backup_require_free_space_check`가 이
    restore-drill 경로(그리고 일반 `new_database` 복원)에도 적용되는지 확인, 적용 안 된다면
    보강 판단. n150은 다른 프로젝트와 공유하는 호스트라 이미지/빌드 캐시가 다시 쌓일 수
    있으므로, 주기적 `docker system prune` 또는 자동화된 이미지 보존 정책이 있는지(없다면
    kor-travel-docker-manager 쪽에 건의할지) 판단 — 이 저장소 범위 밖일 수 있음.

### 선택 후속 (낮은 우선순위)

- **진행 중 작업 없음.** (T-219 잔여 L까지 완료 — `tasks-done.md` 참조.)

## 보류 (외부 조건)

- [ ] **T-063** — N150/Odroid 실측 실행. 실제 N150/Odroid 장비가 준비되면 T-055 runbook을
  사용해 full-load, SQL 벤치마크, REST 벤치마크, MV refresh/swap, backup/restore를 최소
  3회씩 측정하고 `artifacts/perf/n150-vs-odroid-*`와 요약 문서를 남긴다. 하드웨어가 없으면
  진행하지 않는다. 상세: `docs/t055-deployment-n150-odroid.md`.
