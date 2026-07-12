# ADR-066: geo 백업/복원·적재 오케스트레이션은 서비스 전용 독립 Dagster로 이관한다

- 상태: accepted (계획 확정, T-290 구현 착수)
- 날짜: 2026-07-08
- 결정자: 사용자 요청, claude·codex 공동 리뷰
- 관련: ADR-006(in-process 큐), ADR-011(`load_jobs` 영속 큐), ADR-017(full-load batch DAG),
  ADR-030(DB 백업/복원), ADR-033(ops 메타데이터), ADR-036(restore hot-swap),
  ADR-063(디버그 지도 패키지 소비), ADR-065(Linux-only 개발환경)

## 컨텍스트

현재 backup/restore·full-load·mv-refresh는 `load_jobs` 영속 큐(ADR-011) + advisory lock +
`FOR UPDATE SKIP LOCKED` + lifespan recovery로 구동된다(ADR-006에서 외부 큐를 의도적으로 회피). 이 구조는
이미 async ETL(ADR-030), 다운로드 artifact, 그리고 T-239 정기 백업(외부 cron이 `/v1/admin/backups/
scheduled/run-due`를 치는 멱등 due-check)까지 제공한다.

사용자가 제기한 개선 pain은 두 가지다.

- (a) **스케줄이 외부 cron 의존이라 불안** — 트리거가 앱 밖에 있어 조용히 끊길 수 있다.
- (b) **실패/이력 관측이 UI로 약함** — `load_jobs`에 데이터는 있으나 run 이력·재시도·스케줄 tick을
  보는 면이 빈약하다.

판단 기준은 사용자가 **외부 dependency 추가 비용은 제외하고 안정성·유지보수성**으로 못박았고, 방향은
**"geo 전용 독립 Dagster 운영"**으로 결정했다. 전체 검토·수렴 과정의 정본은
[`docs/backup-restore-orchestration.md`](../backup-restore-orchestration.md)(codex 원안 → claude 보강 →
codex 후속 → claude round-3, 3라운드 수렴)이다.

결정적 근거: sibling `kor-travel-map`이 **서비스 전용 독립 Dagster를 이미 프로덕션 운영**한다
(@asset 30·@op/@job 20+·@schedule 20·@sensor 2; 정본 `kor-travel-map/docs/architecture/dagster-boundary.md`).
`batch_dag.py`가 geo ADR-017을 이미 미러했으므로 full-load는 1:1 역이식이 가능하다. 즉 geo는 새 설계가
아니라 검증된 in-house 청사진의 이식이다.

## 결정

geo 백업/복원·적재 오케스트레이션을 **서비스 전용 독립 Dagster 인스턴스**(`kor-travel-geo-dagster`)로
이관한다. 세부 결정은 다음과 같다. 구현 청사진·규약은 [`docs/architecture/dagster-boundary.md`](
architecture/../architecture/dagster-boundary.md), 단계·분해는
[`docs/dagster-migration-plan.md`](../dagster-migration-plan.md)가 정본이다.

1. **실행 주체는 Dagster다(관측 sidecar가 아니라).** 목표 상태에서 Dagster `@op`이 geo leaf 함수
   (`run_backup_job()`, `run_restore_job()`, loader, consistency gate)를 **직접 실행**하고, FastAPI API는
   Dagster webserver를 **GraphQL로 launch·observe**한다(map 모델). "Dagster가 일하려고 Admin API를
   호출"하는 sidecar 모델은 **온램프(마이그레이션 초기 단계)로 한정**하며 목표 구조가 아니다 —
   그렇게 두면 in-process 큐와 그 부채(`_run_loader_off_event_loop`(T-193), drain nudge(T-192),
   lifespan running→failed 일괄 처리)가 영구 존치되어 유지보수성이 개선되지 않기 때문이다.

2. **정본은 하나가 아니라 "깨끗한 2-정본 경계"다.** split-brain은 같은 사실을 둘 다 정본으로 둘 때만
   생긴다. 경계를 다음으로 고정한다.
   - **Dagster run store**(별도 DB `kor_travel_geo_dagster`) = run/event/**schedule/retry 이력** 정본.
   - **앱 `load_jobs`** = admin **progress/cancel/audit** 정본. 실행 주체(= Dagster op)가 기존
     `progress()` 콜백으로 `load_jobs`를 갱신한다 → progress 정본은 하나로 유지된다.
   - `ops.artifacts`·`ops.serving_releases`·`ops.dataset_snapshots`는 **geo 도메인 코드가 기록**한다.
     Dagster는 직접 제조하지 않고 metadata에 `job_id`/`artifact_id`/`serving_release_id`/checksum prefix/
     redacted URI 같은 참조·요약만 둔다.

3. **파괴적 경계는 map 실증 밖이다 — 수동 승인을 유지한다.** map의 검증은 멱등 provider 적재에 대한
   것이고 restore/hot-swap 같은 파괴적 DB 수술에는 확장되지 않는다. Dagster 실행 범위는
   **backup · 새 빈 DB로의 restore · verify · restore drill · loader/full-load**까지다.
   **hot-swap과 `replace_current`는 실행자가 Dagster여도 자동 schedule 금지, 수동 typed confirmation +
   maintenance window(ADR-036 경로)를 그대로 요구**한다. Dagster는 plan/observe만 한다.

4. **retry는 멱등 stage에만.** Dagster `RetryPolicy`는 파괴적/비멱등 op에서 끈다. map이 feature load에
   붙이는 `RetryPolicy(max_retries=3)`을 restore/hot-swap op에 복제하지 않는다. 자동 retry는 enqueue 전
   단계·외부 copy transient·알림에만 허용하고, `pg_restore` version mismatch·checksum mismatch·disk
   preflight 실패는 자동 retry 금지(ADR-030/기존 정책 유지).

5. **recovery 변경은 실행 이관의 선결 게이트다.** 현 `JobQueue.recover_startup()`은 모든 `running`을
   API restart로 보고 실패 처리한다. Dagster가 실행하는 running job이 존재하기 *전에* `load_jobs`에
   `executor`/`orchestrator_run_id`/`lease_expires_at` + executor별 recovery + reconciler를 먼저 넣는다.
   cancel은 양방향으로 닫는다(API cancel → Dagster run termination, Dagster 실패/취소 → `load_jobs`
   terminal 수렴).

6. **패키지 레이아웃은 별도 top-level distribution `kortravelgeo_dagster`로 한다.** map은
   `kortravelmap.__init__`에서 `pkgutil.extend_path`로 `kortravelmap.dagster.*` namespace를 확장하지만,
   geo `kortravelgeo.__init__`은 eager import를 하는 일반 패키지라 namespace 확장을 얹으면 editable
   install·mypy·빌드 백엔드에서 취약점이 생긴다. **안정성·유지보수성 우선 원칙에 따라 namespace 매직
   없는 별도 top-level `kortravelgeo_dagster`**를 채택한다(같은 강제 단방향 경계를 더 적은 매직으로
   얻음). main lib `kortravelgeo`는 **Dagster-free**로 유지한다(`@asset`/`@op`/`Definitions` 미사용).

7. **독립 런타임·포트·저장소.** Dagster webserver + daemon + db-init를 `kor-travel-docker-manager`
   compose에 별도 서비스로 추가하고, 메타 DB `kor_travel_geo_dagster`(같은 Postgres 클러스터)를 쓴다.
   webserver 포트는 `docs/ports.md`에 신규 예약한다(map=12702 점유). n150 host-network 충돌을 배포 전
   확인한다.

## 근거

- (b) 관측: Dagster run/event/schedule/retry 이력 UI는 손으로 만들지 않고 프레임워크에서 얻는다. map은
  이를 자기 admin에 GraphQL 요약 + Dagster UI iframe으로 임베드해 이미 해결했다 → 이식 가능한 blueprint.
- (a) 스케줄: Dagster `@schedule`(cron, `Asia/Seoul`) + `@run_failure_sensor`가 외부 cron 의존과 조용한
  실패를 대체한다. daemon 건강성은 supervised 서비스로 관측된다.
- 유지보수성: in-process 큐의 손수 만든 부채가 Dagster executor로 은퇴한다. geo가 Dagster 생태계
  (map/pinvi)에서 유일한 예외였던 상태도 해소된다.
- 안정성: 스케줄러·retry·run 복구·상태추적 primitives는 검증된 프레임워크가 hand-rolled보다 낫다. 단
  도메인 임계 leaf(hot-swap 등)는 재사용하고 재검증(roundtrip/fault-injection 테스트)으로 회귀를 막는다.

## 결과

### 긍정
- 정기 백업·실패 관측이 견고해지고(a·b 해소), full-load/backup/restore가 하나의 Dagster 그래프·이력으로
  관측된다.
- geo가 map과 동일 오케스트레이션 아키텍처로 수렴 → 두 서비스 유지보수 컨텍스트 세금 감소.
- in-process 큐 부채(T-192/T-193 우회, lifespan 복구 로직) 은퇴.

### 부정
- 신규 런타임(webserver+daemon+메타 DB) + Dagster 버전 업그레이드 tax(단, map과 공유 비용).
- 마이그레이션 기간의 회귀 위험(특히 restore/hot-swap) — 위상 이관 + 기존 테스트 재검증 + n150 live
  e2e 게이트로 관리한다.

## 후속

- (계획) [`docs/dagster-migration-plan.md`](../dagster-migration-plan.md)의 M1~M6 milestone과 T-290
  A/B 병렬 분해, live UI e2e 게이트대로 이행한다.
- (문서) geo판 [`docs/architecture/dagster-boundary.md`](../architecture/dagster-boundary.md)를 구현 정본으로
  둔다.
- (done, T-290k) 이관 완료 후 ADR-006/011의 in-process 큐 관련 결정을 superseded로 표기했다 —
  ADR-006은 `superseded by ADR-066`, ADR-011은 `partially superseded`(테이블 유지·실행만 은퇴).
  in-process `JobQueue` drain은 삭제됐고 모든 실행은 Dagster op으로 구동된다.
