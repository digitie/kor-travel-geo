# ADR-036: 적재 완료 DB Restore는 같은 cluster 안 `ALTER DATABASE RENAME` 기반 hot-swap을 1차 패턴으로 지원한다

- 상태: accepted (1차 plan/preflight 구현 완료, ADR-030 결과 섹션 amend)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, claude

## 컨텍스트

ADR-030 / T-046은 적재 완료 DB의 backup/restore 워크플로를 정의했지만, 복원은 "기본 새 빈 DB"만 명문화하고 운영 serving DB로의 즉시 전환(hot-swap)은 "별도 위험 경로"로만 언급했다. 운영 시나리오:

1. T-046으로 복원본 DB(`kor_travel_geo_restore_<ts>`)를 만든다.
2. smoke/consistency/performance gate가 통과한다.
3. 운영 serving DB(`kor_travel_geo`)를 복원본으로 즉시 교체한다.

이를 위한 결정과 절차를 명문화한다.

## 결정

복원본 DB가 운영 serving DB와 **같은 PostgreSQL cluster 안**에 있는 경우, `ALTER DATABASE ... RENAME TO ...` 기반 hot-swap을 1차 패턴으로 지원한다.

1. 사전 조건: `ops.maintenance_windows(kind='restore', state='active')` + typed confirmation hash 일치 + 복원본 DB smoke/consistency 통과.
2. swap 절차:
   - maintenance용 별도 DB(`postgres` 또는 admin DB) connection 사용.
   - 두 DB의 기존 connection을 `pg_terminate_backend`로 종료.
   - 운영 DB → `<current>_previous_<ts>` 로 rename.
   - 복원본 DB → `<current>` 로 rename.
   - application engine pool refresh.
   - post-swap smoke test 실행.
3. release/audit 연계:
   - 새 `ops.serving_releases(release_kind='restore', previous_release_id=...)` row 생성.
   - `ops.audit_events`에 `serving_release.hot_swap.started|succeeded|failed|rolled_back` 4종 outcome 기록.
4. rollback 절차: `<current>_previous_<ts>` alias가 retention 기간 안이면 같은 절차로 반대 방향 rename. 새 `release_kind='rollback'` row 생성, `rollback_target_release_id`로 원본 release 참조.
5. 다른 host/cluster로의 fail-over(cluster 간 hot-swap)는 본 ADR 범위가 아니다. 별도 ADR/task에서 다룬다.

## 근거

- `ALTER DATABASE ... RENAME`은 metadata-only ALTER로 < 1초 안에 완료. application DSN을 바꾸지 않고 같은 cluster 안에서 즉시 교체 가능.
- ADR-033의 `ops.serving_releases` + `ops.maintenance_windows` + active partial unique index가 동시 swap을 DB 수준에서 1건으로 제한한다.
- application 변경 범위는 engine pool refresh + maintenance connection helper로 한정된다. application 코드 침투 최소.
- DSN switch 방식(다른 host fail-over)은 본 task scope를 넘는다. 별도 ADR/task.

## 결과

- T-058 1차에서 hot-swap plan/preflight API·CLI를 구현했다.
- ADR-030 "결과/후속" 섹션에 본 결정을 참조하는 amend를 추가한다.
- REST 1차: `POST /v1/admin/restores/hot-swap-plan`으로 typed confirmation, rollback confirmation, blocker, SQL/steps를 산출한다.
- CLI 1차: `ktgctl serving hot-swap-plan`.
- 후속 실행 REST/CLI: 실제 `ALTER DATABASE ... RENAME`, post-swap smoke, rollback round-trip.
- 실행 통합 검증은 대구광역시 부분 DB로 backup → restore → hot-swap → smoke → rollback round-trip.

## 남은 위험

- swap 중 `pg_terminate_backend`로 모든 connection을 끊으므로 in-flight query 중단이 호출자에게 노출된다. LB drain + 호출자 retry로 보완.
- multi-process(Gunicorn workers) 환경은 worker별 engine refresh 신호 필요.
- `<current>_previous_<ts>` alias retention 종료 후에는 rollback 불가. retention 기간(권장 7일)을 운영자가 설정.
- 복원본 DB가 다른 PostgreSQL major version에서 만들어졌다면 hot-swap 거절(major mismatch hard-fail).

## Amend (2026-09-29, T-312): 공용 DB instance에서는 적용하지 않는다

T-308로 geo DB가 공용 control-plane PostgreSQL instance로 옮겨지면서 app role(`kor_travel_geo_app`)은
`NOCREATEDB`이고 maintenance DB `postgres`에 `CONNECT`도 없다. 이 결정의 전제(maintenance DB 연결 +
`ALTER DATABASE RENAME` = owner + `CREATEDB`)가 성립하지 않으므로:

- 연결 role의 capability(`CREATEDB`·superuser, `postgres` `CONNECT`)를 런타임에 판정하고(`KTG_DB_LIFECYCLE_MODE`
  auto|enabled|disabled), 부족하면 hot-swap plan/execute/rollback을 `E0410`(HTTP 409)로 즉시 거절한다. 같은 판정이
  restore drill, blue-green scratch full-load, `db_restore`에도 적용된다(API 1차, Dagster op 2차).
- 공용 instance에서의 새 DB 복원·rename 교체는 운영자가 manager `ktdctl`로 수행한다. 절차와 app role 백업의 복원
  형식(`pg_dump --no-privileges`, 비-superuser 복원 시 `--no-owner --no-privileges` + 미리 만든 extension/`x_extension`
  TOC 제외)은 `docs/t046-db-backup-restore.md` "공용 DB instance (T-312)" 절.
- 전용(superuser) instance에서는 `auto`가 그대로 허용하므로 이 ADR의 절차·동작은 바뀌지 않는다.
