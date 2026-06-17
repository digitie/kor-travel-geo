# ADR-033: 운영 메타데이터는 `ops` 스키마의 감사·스냅샷·릴리스 테이블로 관리한다

- 상태: accepted (T-054 1차 구현 완료)
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

## 컨텍스트

T-027 이후 실제 전국 적재, T-045 source set, T-046 백업/복원, T-047 성능 튜닝이 이어지면 운영자가 추적해야 할 정보가 급격히 늘어난다. 현재 `load_jobs`, `load_manifest`, `load_consistency_reports`는 적재와 검증의 일부 상태를 담지만, 다음 질문에는 충분히 답하지 못한다.

- 현재 운영 중인 데이터셋이 어떤 source set, row count, migration revision, git commit으로 만들어졌는가?
- 어떤 정합성 리포트와 성능 리포트가 이 데이터셋의 운영 반영을 승인했는가?
- 어떤 job이 어떤 backup/export/report artifact를 만들었고, checksum과 보존 정책은 무엇인가?
- 누가 CLI/API/UI에서 위험 작업을 실행했고, 어떤 confirmation과 maintenance window 아래에서 실행했는가?
- `mv_geocode_target` swap 이후 active serving release가 무엇이고, rollback 가능한 직전 release는 무엇인가?

로그 파일과 PR 본문만으로 이 정보를 맞춰 보는 방식은 재설치, 장애 복구, 데이터 회귀 분석에서 취약하다. DB 내부에 운영 메타데이터를 구조화해서 남겨야 한다.

## 결정

운영 메타데이터 전용 `ops` 스키마를 추가한다.

```sql
CREATE SCHEMA IF NOT EXISTS ops;
```

`public`은 주소 원천·serving 테이블과 view/materialized view를 유지하고, `x_extension`은 PostGIS 보조 extension 격리 용도로 유지한다. `ops`는 운영 감사, 데이터셋 snapshot, serving release, artifact registry, maintenance window, table stats snapshot만 담는다. 애플리케이션 SQL은 `search_path`에 기대지 않고 `ops.<table>`을 명시한다.

T-049 구현에서 다음 테이블을 추가했다.

| 테이블 | 목적 |
|--------|------|
| `ops.audit_events` | 관리 작업과 위험 작업의 append-only 감사 이벤트. actor, request/trace id, action, resource, outcome, redacted payload hash를 저장 |
| `ops.dataset_snapshots` | full-load, daily delta, restore 후 검증 가능한 데이터셋 상태. source set, row count, consistency/performance/backup artifact, code/schema version을 연결 |
| `ops.serving_releases` | 어떤 snapshot이 현재 운영 조회 release인지 기록. active release 1건 강제, rollback lineage 보존 |
| `ops.artifacts` | backup, restore log, consistency export, performance report, source inventory, schema diff 등 운영 산출물의 공통 registry |
| `ops.maintenance_windows` | restore, schema migration, full-load, MV swap 같은 위험 작업의 의도된 maintenance 상태와 차단 규칙 |
| `ops.table_stats_snapshots` | 테이블/MV/index row count, size, bloat, analyze 상태를 시간축으로 기록 |

T-046에서 계획한 `db_backup_artifacts`는 신규 구현에서는 `ops.artifacts`의 `artifact_type='db_backup'`으로 수렴한다. 이미 별도 테이블이 생성된 배포가 있다면 compatibility view 또는 migration으로 흡수한다.

## 규칙

- `ops.audit_events`는 append-only다. 운영자가 삭제해야 하는 경우에도 삭제 row를 남기거나 archive 상태로 전환한다.
- `ops.audit_events.job_id`는 `load_jobs(job_id)`를 참조하되 `ON DELETE NO ACTION`으로 둔다. 감사 이벤트가 있는 job을 삭제하면 job id 연결이 사라지므로, `ON DELETE SET NULL`로 조용히 끊지 않고 정리 정책을 명시하도록 DB가 차단한다.
- API key, DSN password, callback secret, download token, 외부 API key는 어떤 `ops` 테이블에도 평문 저장하지 않는다.
- 주소 원문은 관리 작업 근거에 꼭 필요한 경우에도 마스킹 또는 hash를 우선한다. 검색 API 요청 전체를 감사 테이블에 저장하지 않는다.
- active serving release는 DB constraint로 한 건만 허용한다.
- destructive restore, 운영 DB overwrite, schema migration, full reset은 active maintenance window와 typed confirmation 없이는 실패한다.
- backup, consistency report, performance report, data-quality export는 가능하면 `ops.artifacts`에 등록하고 checksum을 검증한다.
- snapshot은 source set hash, row count, Alembic revision, git commit, PostgreSQL/PostGIS version을 포함해야 한다.
- T-047 성능 튜닝에서 보조 MV/index를 추가하면 table stats snapshot과 serving release metadata에도 영향이 기록되어야 한다.

## API와 UI

REST 표면은 `/v1/admin/ops/*`를 기본으로 둔다.

- `GET /v1/admin/ops/snapshots`
- `GET /v1/admin/ops/releases`
- `POST /v1/admin/ops/releases/{release_id}/rollback-plan`
- `GET /v1/admin/ops/artifacts`
- `GET /v1/admin/ops/audit-events`
- `GET /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows/{window_id}/end`
- `GET /v1/admin/ops/table-stats`
- `POST /v1/admin/ops/table-stats/capture`

프론트엔드는 `/admin/ops` 또는 기존 `/admin/load`, `/admin/backups`, `/admin/consistency` 내부 탭에서 시작한다. 첫 UI는 active release, 최근 snapshot, artifact 목록, maintenance window 상태, 주요 table/MV size를 보여 주면 충분하다.

## 근거

- `load_jobs`는 실행 상태, `ops.audit_events`는 운영 의사결정 이력을 담당하게 되어 역할이 분리된다.
- snapshot과 release를 분리하면 "검증된 데이터셋"과 "현재 운영 조회에 노출된 데이터셋"을 혼동하지 않는다.
- artifact registry를 공통화하면 T-046 백업 파일, T-047 성능 리포트, C2/C4/C6/C7 data-quality export가 같은 보존·checksum·download 규칙을 따른다.
- maintenance window를 DB에 두면 CLI, API, UI, background worker가 같은 차단 규칙을 공유한다.

## 결과

- T-049 구현 PR에서 `ops` 스키마 DDL, Alembic `0006_t049_ops_metadata_schema`, DTO/API/client/UI, redaction/hash helper, append-only audit trigger, active release partial unique index, table stats snapshot capture를 추가했다.
- `docs/t049-ops-metadata-schema.md`에 구현 상태와 남은 연결점을 둔다.
- T-045/T-046/T-047 구현 시 source set 확정, backup/restore artifact, performance report, MV swap gate를 snapshot/artifact/release에 실제로 연결한다.
- T-050 4차에서 `mv_refresh` 성공 시 `ops.dataset_snapshots`와 active `ops.serving_releases`를 자동 생성하도록 연결했다. restore 성공은 serving 전환이 아니므로 `validated` snapshot과 `pending` restore release 후보만 만들고, active 승격은 T-058 hot-swap으로 넘긴다.
