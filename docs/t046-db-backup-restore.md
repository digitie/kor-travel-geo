# T-046: 적재 완료 DB 백업/복원 구현 기록

## 범위

본 문서는 완전히 또는 부분적으로 적재된 PostgreSQL + PostGIS DB를 빠르게 백업하고 복원하기 위한 설계와 T-046 구현 결과를 함께 기록한다. 사용자는 전체 데이터를 다시 로드하지 않고도, 검증된 DB 상태를 압축 아카이브로 저장하고 필요할 때 복원할 수 있어야 한다.

T-046에서는 코드 구현, 단위 테스트, 관리 UI, OpenAPI 타입 동기화, Windows Playwright 렌더 검증, 대구광역시 부분 적재 DB 기반 실제 backup → restore 검증까지 수행했다. 전국 full-load 재실행은 본 task 범위가 아니며, 후속 T-027/T-047에서 별도 수행한다.

## 구현 요약

구현된 파일과 역할은 다음과 같다.

| 영역 | 파일 | 내용 |
|------|------|------|
| DTO | `src/kortravelgeo/dto/admin.py` | `BackupCreateRequest`, `RestoreCreateRequest`, `BackupArtifact`, `db_backup`/`db_restore` job kind 추가 |
| 설정 | `src/kortravelgeo/settings.py` | `backup_allowed_dirs`, `backup_temp_dir`, `backup_default_jobs`, `backup_default_compression_level`, `backup_artifact_ttl_days`, `backup_callback_allowed_hosts`, `backup_callback_secret`, `backup_callback_max_attempts`, `backup_callback_backoff_ms`, `backup_download_token_secret` 추가 |
| 실행 로직 | `src/kortravelgeo/infra/backup.py` | path allowlist 검증, `pg_dump -Fd`, `tar.zst`, checksum, manifest, `pg_restore -Fd`, target DB empty check, HMAC callback retry, download token |
| metadata | `src/kortravelgeo/infra/admin_repo.py` | `ops.artifacts` insert/get/update/delete helper 추가 |
| job queue | `src/kortravelgeo/api/_jobs.py`, `src/kortravelgeo/api/app.py` | handler payload에 `_job_id` 주입, `db_backup`/`db_restore` handler 등록, full-load batch successor 계산에서 control kind로 분리 |
| REST API | `src/kortravelgeo/api/routers/admin.py` | `/v1/admin/backups`, `/v1/admin/backups/{artifact_id}`, `/download`, `/delete`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events` 추가 |
| CLI | `src/kortravelgeo/cli/main.py` | `ktgctl backup create/list/show/delete`, `ktgctl restore create` 추가 |
| UI | `kor-travel-geo-ui/app/admin/backups/page.tsx`, `components/admin/BackupsPanel.tsx` | 백업 생성, 복원 등록, job 진행률/취소, artifact 목록, 다운로드/삭제 UI |
| 타입 | `openapi.json`, `kor-travel-geo-ui/types/api.gen.ts`, `kor-travel-geo-ui/lib/schemas.gen.ts` | OpenAPI와 프론트엔드 생성 타입 갱신 |

현재 구현의 기본 동작은 다음과 같다.

1. `POST /v1/admin/backups` 또는 `ktgctl backup create`가 `db_backup` job을 등록/실행한다.
2. 백업 대상 디렉터리는 `KTG_BACKUP_ALLOWED_DIRS` 하위 resolve path만 허용한다. 상대 경로는 첫 allowlist root 기준으로 해석한다.
3. `pg_dump --format=directory --jobs=N` 결과를 임시 디렉터리에 만든다.
4. `manifest.json`, `checksums.sha256`, job log를 만들고 `tar --use-compress-program=zstd -T0 -<level>`로 `.tar.zst.part` 파일을 생성한다.
5. archive SHA256과 크기를 계산한 뒤 `.part` 파일을 최종 `.tar.zst` 경로로 rename한다.
6. archive SHA256과 크기를 `ops.artifacts(artifact_type='db_backup')`에 저장한다.
7. 완료 artifact는 HMAC 기반 download token이 붙은 `download_url`을 API 응답에 포함한다.
8. `POST /v1/admin/restores` 또는 `ktgctl restore create`는 artifact 또는 archive path를 받아 새 빈 DB에 `pg_restore --format=directory --jobs=N`로 복원한다.
9. 기본 복원 모드 `new_database`는 현재 DB와 같은 target DB를 거절하고, target DB가 비어 있지 않으면 실패한다.
10. 복원 후 `ANALYZE`와 smoke test를 수행한다. `run_consistency=true`는 현재 target DB 연결 구조상 별도 후속 실행이 필요하므로 job log에 명시한다.
11. 백업/복원 job은 기존 `load_jobs` 상태 전이, 진행률, `log_tail`, 취소, startup recovery 규칙을 공유한다.

## 문제 정의

전국 전체 원천을 새 DB에 다시 적재하면 수 시간 단위 시간이 걸린다. SHP 대형 레이어, MV refresh/swap, C1~C10 정합성 검증까지 포함하면 반복 테스트와 운영 복구가 느리다. 반면 plain SQL 덤프는 파일이 매우 커지고, 복원 시 단일 스트림으로 DDL과 data를 재생하게 되어 병렬성이 약하다. 따라서 "DDL 형태" 또는 `.sql` 단일 파일 백업은 운영 기본값으로 현실적이지 않다.

필요한 것은 다음이다.

- 사용자가 지정한 서버 측 저장 공간에 압축된 백업 파일을 만든다.
- 백업과 복원은 백그라운드 작업으로 실행한다.
- 진행 상황을 UI와 API에서 확인한다.
- 완료 또는 실패 시 callback을 받을 수 있다.
- UI는 진행률을 실시간으로 보여 주고, 백업 완료 후 다운로드 링크를 제공한다.
- 복원은 운영 DB를 바로 덮어쓰지 않고, 기본적으로 새 빈 DB에 복원한 뒤 검증한다.
- 구현 검증은 대구광역시 부분 적재 데이터로 먼저 수행한다.

## 형식 결정

### 기본 형식: directory dump + tar.zst

기본 백업 형식은 다음 2단계다.

1. `pg_dump -Fd --jobs <N>`로 임시 디렉터리에 PostgreSQL directory format dump를 만든다.
2. 임시 디렉터리와 metadata JSON을 `tar`로 묶고 `zstd`로 압축해 단일 `.tar.zst` 파일로 저장한다.

T-047 전국 DB 실측에서는 `pg_dump -Fd` 산출물의 대형 table data가 이미 `.dat.gz`로 압축되어 있어 `tar.zst` 단계의 추가 압축률은 매우 작았다. dump directory 4,313,361,824 bytes가 archive 4,308,457,630 bytes가 되어 약 4.9MiB만 줄었다. 따라서 `directory_tar_zstd` 선택의 핵심 가치는 압축률이 아니라 병렬 dump/restore와 단일 artifact 보관, UI 다운로드, checksum 검증 단순화다.

이 방식의 장점:

- `pg_dump -Fd`는 dump 단계에서 병렬 작업을 사용할 수 있다.
- `pg_restore -Fd --jobs <N>`로 복원도 병렬화할 수 있다.
- 단일 `.tar.zst`로 보관하면 UI 다운로드와 외부 저장이 쉽다.
- plain SQL보다 파일 크기와 복원 시간이 현실적이다.
- directory dump와 metadata를 한 아카이브에 함께 넣을 수 있다.

보조 형식:

- 작은 샘플 DB 또는 단순 내보내기에는 `pg_dump -Fc` custom format도 허용할 수 있다.
- 전국 운영 기본값은 `directory+tar.zst`다.
- plain SQL format(`pg_dump -Fp`, `.sql`)은 디버깅 목적 외에는 금지한다.

### 대안 비교

| 방식 | 장점 | 단점 | T-046 판단 |
|------|------|------|------------|
| plain SQL (`pg_dump -Fp`) | 사람이 열어 보기 쉽고 단일 파일 | 대용량에서 파일이 커지고 복원 병렬성이 약함 | 운영 기본값 금지 |
| custom format (`pg_dump -Fc`) | 단일 파일, `pg_restore` 사용 가능 | dump 자체 병렬성이 제한적이고 초대형 DB 복원 속도에서 불리 | 작은 샘플 DB 보조 옵션 |
| directory format (`pg_dump -Fd`) | dump/restore 모두 `--jobs` 병렬 가능 | 산출물이 디렉터리라 별도 포장 필요 | 기본 dump 형식 |
| directory + `tar.zst` | 병렬 dump/restore와 단일 artifact 보관을 모두 만족 | 압축/해제 단계가 추가됨 | T-046 기본값 |
| `pg_basebackup`/volume snapshot | 같은 호스트 복구가 매우 빠를 수 있음 | cluster 전체 단위, WAL/권한/서버 중지 여부 의존, 이식성 낮음 | 별도 ADR 후보 |

따라서 "더 좋은 방법" 후보인 물리 snapshot은 재해복구 전용으로는 매력적이지만, 이 기능의 1차 목표인 단일 DB 이식성, UI 다운로드, manifest 기반 검증, 부분 DB 통합 테스트에는 `directory_tar_zstd`가 더 적합하다.

### 물리 백업을 기본값으로 두지 않는 이유

`pg_basebackup`, Docker volume snapshot, 파일시스템 snapshot은 더 빠를 수 있지만 다음 제약이 있다.

- PostgreSQL cluster 전체 단위라 단일 DB 이식성이 낮다.
- Docker/WSL/운영 호스트 파일시스템에 강하게 묶인다.
- 복원 절차가 권한, WAL, 서버 중지 여부에 의존한다.

따라서 T-046의 1차 구현은 단일 DB 단위의 논리 백업이다. 같은 호스트에서 초고속 재해복구가 필요해지면 물리 snapshot은 별도 ADR로 다룬다.

## 백업 아카이브 구조

압축 파일명 예:

```text
kor_travel_geo_backup_20260526T153000Z_pg16_postgis34_daegu.tar.zst
```

아카이브 내부:

```text
manifest.json
dump/                         # pg_dump -Fd 산출물
  toc.dat
  *.dat.gz 또는 *.dat
checksums.sha256
logs/
  backup-job.ndjson
```

`manifest.json` 필수 필드:

```json
{
  "artifact_schema_version": 1,
  "created_at": "2026-05-26T15:30:00Z",
  "app_version": "0.1.0",
  "git_commit": "unknown-or-sha",
  "database": {
    "name": "kor_travel_geo",
    "postgres_version": "16.x",
    "postgis_version": "3.4.x",
    "alembic_revision": "head",
    "database_size_bytes": 1234567890
  },
  "backup": {
    "format": "directory_tar_zstd",
    "compression": "zstd",
    "compression_level": 3,
    "jobs": 4,
    "profile": "serving-ready",
    "include_materialized_views": true,
    "exclude_table_data": []
  },
  "source_set": {
    "yyyymm_by_kind": {
      "juso": "202603",
      "locsum": "202604",
      "navi": "202604",
      "shp": "202604"
    },
    "mixed_yyyymm": true,
    "mixed_yyyymm_acknowledged": true
  },
  "row_counts": {
    "tl_juso_text": 0,
    "mv_geocode_target": 0,
    "mv_geocode_text_search": 0
  },
  "checksums": {
    "archive_sha256": "filled-after-write"
  }
}
```

백업 profile:

| profile | 내용 | 용도 |
|---------|------|------|
| `serving-ready` | master table, 보조 table, MV data, index, manifest, consistency report 포함 | 기본. 복원 후 즉시 조회 검증 |
| `lean-serving` | `geo_cache`, 오래된 `load_jobs.log_tail` 같은 휘발성 table data 제외 | 반복 개발/테스트 |
| `forensic` | cache, load job, log tail까지 포함 | 장애 분석과 완전 상태 보존 |

기본값은 `serving-ready`다. MV data를 포함하지 않으면 복원 후 `refresh mv --swap`이 필요해져 시간을 다시 쓰게 되므로, 백업 크기가 커져도 기본값에서는 MV를 포함한다.

## 백업 작업 흐름

1. 사용자가 UI 또는 API에서 백업 저장 경로, profile, parallel jobs, callback 설정을 입력한다.
2. 서버가 경로를 검증한다.
3. `db_backup` job을 기존 `load_jobs` 영속 큐에 등록한다.
4. 작업은 백그라운드에서 실행된다.
5. preflight 단계에서 다음을 확인한다.
   - 대상 경로가 allowlist 하위인지
   - 예상 여유 공간이 충분한지
   - 현재 DB에 `postgis`, `pg_trgm`, `unaccent`, Alembic revision 정보가 있는지
   - 실행 중인 `full_load_batch`, `mv_refresh`, `db_restore`가 없는지
6. `pg_dump -Fd --jobs N`을 임시 디렉터리에 실행한다.
7. `manifest.json`, `checksums.sha256`, job log를 만든다.
8. `tar.zst` 아카이브를 생성한다.
9. archive SHA256과 크기를 계산한다.
10. `ops.artifacts`에 `artifact_type='db_backup'` metadata를 기록한다. 이미 전용 `db_backup_artifacts`를 가진 배포를 지원해야 하면 compatibility view 또는 migration으로 흡수한다.
11. job을 `done`으로 전환하고 callback을 호출한다.
12. UI는 download link를 표시한다.

진행률 phase:

| phase | progress 범위 | 기준 |
|-------|----------------|------|
| `preflight` | 0.00~0.05 | 경로/용량/DB metadata 확인 |
| `dump` | 0.05~0.65 | `pg_dump --verbose` object count와 dump 디렉터리 증가량 |
| `dump checksum` | 0.65~0.70 | `manifest.json`과 dump 디렉터리 checksum 처리 byte |
| `archive` | 0.70~0.90 | `.part` archive 증가량 / archive 입력 byte |
| `checksum` | 0.90~0.97 | archive SHA256 읽은 byte / 전체 archive byte |
| `finalize` | 0.97~1.00 | metadata 저장, callback, cleanup |

`pg_dump`는 정확한 row-level progress를 제공하지 않으므로 진행률은 phase별 추정값이다. T-050 3차 이후 dump/archive/checksum/extract 구간은 기존 line count 추정에 file size sampler를 더한다. UI에는 "추정 진행률"임을 표시하되, `current_stage`, 현재 처리 파일, dump 디렉터리 크기, archive 입력/출력 크기, checksum byte, elapsed time을 함께 보여 준다. `tar.zst` output은 입력보다 작을 수 있으므로 archive byte progress는 완료율 확정값이 아니라 정체 여부를 보기 위한 보조 지표다.

## 복원 작업 흐름

복원은 기본적으로 새 빈 DB로만 수행한다.

1. 사용자가 백업 artifact를 선택하거나 서버 경로를 입력한다.
2. target DB 이름 또는 target DSN을 입력한다.
3. 서버가 archive SHA256과 `manifest.json`을 검증한다.
4. target DB가 비어 있는지 확인한다.
5. 기본 모드에서는 target DB가 비어 있지 않으면 실패한다.
6. `db_restore` job을 등록한다.
7. 작업은 임시 디렉터리에 archive를 해제한다.
8. `pg_restore -Fd --jobs N --dbname <target>`를 실행한다.
9. `ANALYZE`와 기본 smoke test를 실행한다.
10. row count와 manifest row count를 비교한다.
11. 선택적으로 `validate consistency --scope full` 또는 축소 scope를 실행한다.
12. 성공하면 UI에 "복원 완료"와 target DB 정보를 보여 준다.

운영 DB를 직접 덮어쓰는 `--replace-current`는 기본 금지다. 필요한 경우 maintenance mode, 모든 app connection 종료, typed confirmation, 백업 선행 생성, rollback plan을 요구한다. 일반 운영 경로는 "새 DB 복원 → 검증 → `KTG_PG_DSN` 전환 → 앱 재시작"이다.

**복원 뒤 `alembic upgrade head` (T-319).** 복원·hot-swap 흐름은 Alembic migration을 돌리지 않는다. 복원한 DB의
`alembic_version`이 앱 head보다 낮으면(T-319 이전 백업은 `0026`/`0027`) serving으로 올리기 전(hot-swap·DSN 전환
전)에 그 DB를 대상으로 `KTG_PG_DSN=<복원 DB DSN> alembic upgrade head`를 돌린다. 예를 들어 `0028`은 원천 기준월
manifest 행(`load_manifest`)을 채운다 — 건너뛰면 MV refresh·백업이 기록하는 기준월(`source_set.yyyymm_by_kind`,
`/v2/dataset/version`)은 manifest 행이 없는 원천을 복원본의 active release 기준월로 이어 쓰는 데 그친다(빈 테이블·
release에 없는 원천은 `null`). 이 upgrade는 manifest 행이 없는 원천 테이블마다 seq scan 1회를 한다.

복원 진행률 phase:

| phase | progress 범위 | 기준 |
|-------|----------------|------|
| `preflight` | 0.00~0.05 | archive/target DB 검증 |
| `extract` | 0.05~0.20 | extract 디렉터리 증가량 / archive byte |
| `restore` | 0.20~0.80 | `pg_restore --verbose` object count와 dump 디렉터리 총량 |
| `analyze` | 0.80~0.90 | 대상 table ANALYZE |
| `validate` | 0.90~0.98 | row count, smoke, 선택 consistency |
| `finalize` | 0.98~1.00 | metadata 저장, callback, cleanup |

## 저장 위치와 보안

사용자가 지정하는 저장 공간은 브라우저 로컬 경로가 아니라 서버가 접근할 수 있는 경로다. UI에서는 다음 둘 중 하나만 허용한다.

1. 운영자가 설정한 allowlist root 중 하나를 선택한다.
2. allowlist 하위 상대 경로를 입력한다.

설정 예:

```text
KTG_BACKUP_ALLOWED_DIRS=/mnt/f/backups/kor-travel-geo,/mnt/d/backups/kor-travel-geo
KTG_BACKUP_TEMP_DIR=/tmp/kor-travel-geo-backup
KTG_BACKUP_DEFAULT_JOBS=4
KTG_BACKUP_ARTIFACT_TTL_DAYS=30
KTG_BACKUP_CALLBACK_ALLOWED_HOSTS=localhost,127.0.0.1,internal.example
```

보안 규칙:

- `..`, symlink escape, absolute path 우회는 거절한다.
- 백업 파일은 기본 `0600` 권한으로 만든다.
- 다운로드 endpoint는 내부망 전용이어도 artifact id와 token을 모두 요구한다.
- download response는 대용량 파일을 메모리에 올리지 않고 stream 또는 web server offload로 처리한다.
- callback URL은 allowlist host만 허용한다. 임의 내부망 SSRF가 되지 않게 한다.
- callback payload에는 DB password, DSN, 실제 API key를 넣지 않는다.

## REST/API 설계

백업:

```text
POST /v1/admin/backups
  body: {
    "destination_dir": "/mnt/f/backups/kor-travel-geo",
    "profile": "serving-ready",
    "format": "directory_tar_zstd",
    "jobs": 4,
    "compression_level": 3,
    "callback_url": "http://localhost:9000/hooks/backup-complete"
  }
  res: LoadJobStatus(kind="db_backup")

GET /v1/admin/backups
  res: list[BackupArtifact]

GET /v1/admin/backups/{artifact_id}
  res: BackupArtifact

GET /v1/admin/backups/{artifact_id}/download
  res: streaming archive

POST /v1/admin/backups/{artifact_id}/delete
  res: BackupArtifact
```

복원:

```text
POST /v1/admin/restores
  body: {
    "artifact_id": "backup_...",
    "target_database": "kor_travel_geo_restore_20260526",
    "mode": "new_database",
    "jobs": 4,
    "run_smoke_test": true,
    "run_consistency": false,
    "callback_url": "http://localhost:9000/hooks/restore-complete"
  }
  res: LoadJobStatus(kind="db_restore")
```

작업 상태:

```text
GET /v1/admin/jobs/{job_id}
GET /v1/admin/jobs/{job_id}/events   # Server-Sent Events
POST /v1/admin/jobs/{job_id}/cancel
```

기존 `/v1/admin/loads`는 호환 경로로 유지할 수 있지만, `db_backup`/`db_restore`는 적재가 아닌 maintenance job이므로 UI는 `/v1/admin/jobs/*` alias를 우선 사용한다.

callback payload:

```json
{
  "event": "db_backup.done",
  "callback_id": "cb_...",
  "timestamp": "2026-05-26T15:40:00+00:00",
  "attempt": 1,
  "max_attempts": 3,
  "artifact_id": "backup_...",
  "artifact_type": "db_backup",
  "state": "done",
  "job_id": "job_...",
  "size_bytes": 123456789,
  "sha256": "..."
}
```

callback header:

```text
content-type: application/json
x-kor-travel-geo-event: db_backup.done
x-kor-travel-geo-callback-id: cb_...
x-kor-travel-geo-timestamp: 2026-05-26T15:40:00+00:00
x-kor-travel-geo-signature: sha256=<hmac-sha256-hex>
```

T-050 2차 이후 callback은 현재 구현된 terminal delivery 경로(`done`, `failed`)에서 최대 `KTG_BACKUP_CALLBACK_MAX_ATTEMPTS`회 시도한다. 기본값은 3회이며 retry 간격은 `KTG_BACKUP_CALLBACK_BACKOFF_MS`를 기준으로 exponential backoff를 적용한다. 서명은 `timestamp + "." + callback_id + "." + body` byte sequence에 HMAC-SHA256을 적용한다. 수신자는 timestamp window와 `callback_id` de-duplication으로 replay를 거절할 수 있다. retry 중복은 별도 문제이므로, attempt 1 처리 후 응답이 유실되어 attempt 2가 새 `callback_id`로 도착하는 경우에는 수신자가 `(artifact_id, event)`를 stable idempotency key로 사용해 중복 업무 처리를 막아야 한다. 외부 수신자가 서명을 검증하려면 `KTG_BACKUP_CALLBACK_SECRET`을 설정한다. 미설정 fallback 서명은 서버 내부 secret에서 파생되어 외부 수신자가 재현할 수 없다. callback 실패는 백업 파일 또는 복원 로그 artifact의 성공 여부를 뒤집지 않고, `ops.artifacts.callback_state`와 `manifest.callback_delivery`에 최종 delivery 상태, attempt 수, callback ID 목록, 마지막 오류를 따로 기록한다.

## UI 설계

새 페이지: `/admin/backups`

탭 구성:

| 탭 | 기능 |
|----|------|
| 백업 생성 | 저장 위치, profile, jobs, compression, callback URL 입력 |
| 진행 중 | `db_backup`, `db_restore` job 실시간 진행률, stage, log tail, 취소 버튼 |
| 백업 목록 | artifact 목록, 크기, 생성일, source set, SHA256, 다운로드 링크, 삭제 |
| 복원 | artifact 선택, target DB 입력, preflight 결과, 복원 시작 |

진행률 표시:

- 백엔드는 Server-Sent Events(`/v1/admin/jobs/{job_id}/events`)를 제공한다.
- T-046 1차 UI는 TanStack Query polling으로 job/artifact 상태를 갱신한다. SSE 연결과 polling fallback 전환 UI는 후속 고도화 후보로 둔다.
- progress bar는 phase별 label과 전체 퍼센트를 함께 표시한다.
- 완료되면 백업 row에 다운로드 버튼을 표시한다.
- 실패하면 `error_message`, 마지막 log tail, 재시도 가능한 phase를 표시한다.

다운로드 링크:

- 백업 job이 `done`이고 artifact가 존재할 때만 노출한다.
- 링크 텍스트는 파일명, 크기, SHA256 앞 12자리를 함께 보여 준다.
- 브라우저 다운로드와 서버 저장 위치는 별개다. 파일은 이미 서버 지정 공간에 저장되어 있고, 다운로드 링크는 사용자가 로컬로 받을 때 쓰는 부가 경로다.

복원 UI 안전장치:

- 기본 target은 새 DB 이름이다.
- 현재 연결 중인 DB 이름과 같은 target은 금지한다.
- `replace_current` 모드는 숨김 또는 별도 위험 모달 뒤로 둔다. T-050 6차부터 이 모드는 `target_dsn`을 받지 않고 target DB 이름이 현재 DB 이름과 같으며, 확인 문구 `RESTORE <현재 DB 이름>`이 일치하고, 같은 확인 문구 hash를 가진 active `restore` maintenance window가 있을 때만 실행된다.
- 복원 시작 전 archive metadata, PostGIS/PostgreSQL 버전, Alembic revision, 예상 복원 크기를 보여 준다.

## 작업 큐와 취소

`db_backup`과 `db_restore`는 기존 `load_jobs` 기반 직렬 큐를 재사용한다. 다만 이름이 적재 전용처럼 보이므로 후속 리팩터링에서는 중립 alias `/v1/admin/jobs`를 표준으로 둔다.

구현된 취소 동작:

- `preflight`: 즉시 취소 가능.
- `dump`: `pg_dump` subprocess에 `SIGTERM`을 보내고 임시 dump dir 삭제.
- `archive`: `tar`/`zstd` subprocess 종료 후 임시 작업 디렉터리 삭제.
- `restore`: `pg_restore` subprocess에 `SIGTERM`을 보낸다. T-046 1차 구현은 target DB를 자동 drop하지 않는다. 운영자가 새 빈 DB를 target으로 지정한다는 전제에서 실패 상태를 명확히 남기고, target DB 삭제 정책은 후속 hardening 후보로 둔다.
- `finalize`: artifact metadata 쓰기 직전이면 취소 가능하다. 완료된 archive는 `available` 상태로 보존한다.

## 대구광역시 부분 검증 시나리오

전국 full-load는 실행하지 않는다. 구현 후 첫 검증은 대구광역시 데이터만 사용한다.

### 사전 조건

- Docker PostgreSQL/PostGIS가 떠 있다.
- 빈 DB `kor_travel_geo_t046_daegu`를 만든다.
- `data/juso`에 다음 원천이 있다.
  - `202603_도로명주소 한글_전체분/rnaddrkor_daegu.txt`
  - `202603_도로명주소 한글_전체분/jibun_rnaddrkor_daegu.txt`
  - `202604_위치정보요약DB_전체분.zip` 내부 대구 member
  - `202604_내비게이션용DB_전체분` 내부 대구 파일
  - `도로명주소 전자지도/대구광역시`

### 부분 적재

1. Alembic schema를 적용한다.
2. 대구 `juso`, `parcel_link`, `locsum`, `navi`, `shp`만 적재한다.
3. `resolve_text_geometry_links()`를 실행한다.
4. `refresh mv --swap`을 실행한다.
5. 최소 smoke test를 실행한다.
   - `tl_juso_text` row count > 0
   - `tl_locsum_entrc` row count > 0
   - `tl_spbd_buld_polygon` row count > 0
   - `mv_geocode_target` row count > 0
   - 대구 주소 1건 geocode 성공
   - 대구 좌표 1건 reverse geocode 성공

### 백업 검증

1. `/v1/admin/backups` 또는 CLI로 `db_backup` job을 등록한다.
2. 저장 위치는 테스트 전용 디렉터리로 둔다.
3. 진행률이 `preflight → dump → dump checksum → archive → checksum → finalize`를 지나 `done`이 되는지 확인한다.
4. artifact 파일이 존재하고 size > 0인지 확인한다.
5. `manifest.json`에 DB 이름, row counts, source set, format, jobs가 들어 있는지 확인한다.
6. SHA256이 metadata와 일치하는지 확인한다.
7. callback 테스트 서버를 켠 경우 terminal callback이 1회 이상 도착했는지 확인한다.

### 복원 검증

1. 빈 DB `kor_travel_geo_t046_daegu_restore`를 만든다.
2. archive를 restore job으로 복원한다.
3. restore progress가 `preflight → extract → restore → analyze → validate → finalize`를 지나 `done`이 되는지 확인한다.
4. 원본 DB와 복원 DB의 핵심 row count를 비교한다.
5. 같은 대구 주소 geocode와 reverse geocode가 성공하는지 확인한다.
6. `mv_geocode_target`과 T-061 이후 `mv_geocode_text_search`가 비어 있지 않고, 복원 직후 추가 full-load 없이 조회 가능한지 확인한다.

### 실제 검증 결과 (2026-05-27)

검증 환경:

| 항목 | 값 |
|------|----|
| 작업 디렉터리 | `/home/digitie/dev/kor-travel-geo` |
| Docker DB | `kor-travel-geo-t027-db-1`, `localhost:15432` |
| source DB | `kor_travel_geo_t046_daegu` |
| restore DB | `kor_travel_geo_t046_daegu_restore` |
| 백업 디렉터리 | `/tmp/kortravel-t046/backups` |
| zstd | sudo 설치 없이 `apt download zstd` 후 `/tmp/codex-zstd/usr/bin/zstd`를 PATH에 추가 |
| 검증 시작/종료 | 2026-05-27 09:07:16 KST ~ 2026-05-27 09:27:19 KST |

대구 부분 적재 결과:

| 객체 | row count |
|------|-----------|
| `tl_juso_text` | 228,875 |
| `tl_juso_parcel_link` | 26,594 |
| `tl_locsum_entrc` | 228,610 |
| `tl_navi_buld_centroid` | 291,281 |
| `tl_navi_entrc` | 12,830 |
| `mv_geocode_target` | 228,875 |

백업/복원 결과:

| 항목 | 결과 |
|------|------|
| 백업 파일 | `/tmp/kortravel-t046/backups/t046_daegu_backup.tar.zst` |
| 파일 크기 | 86,752,398 bytes, 약 83 MiB |
| archive SHA256 | `3718e98d25226215606d6324ce19422756fe900721abc22c060583322329cb57` |
| `db_backup` artifact 상태 | `available` |
| `db_backup` artifact 시간 | 5.70초 |
| `db_restore_log` artifact 상태 | `available` |
| `db_restore` 시간 | 21.25초 |
| 복원 row count | source와 동일 (`228875/26594/228610/291281/228875`) |
| smoke | 복원 DB에서 `대구광역시 중구 공평로 88` geocode `OK`, 해당 좌표 reverse `OK` |

검증 중 발견해 코드에 반영한 문제:

- `KTG_BACKUP_ALLOWED_DIRS=/tmp/a,/tmp/b`처럼 문서에 적은 CSV 환경변수가 pydantic-settings의 complex JSON decoding 단계에서 실패했다. `Settings.backup_allowed_dirs`와 `backup_callback_allowed_hosts`에 `NoDecode`를 적용해 CSV validator가 실제 env 값에도 동작하도록 수정했다.
- SHP 로더는 `.../대구광역시/27000`이 아니라 `.../대구광역시`처럼 시도 루트를 받아 내부 SIG 코드 디렉터리를 찾아야 한다. 검증 명령과 문서에 이 경로 기준을 명시했다.

### 실패/예외 시나리오

| 시나리오 | 기대 동작 |
|----------|-----------|
| 저장 경로가 allowlist 밖 | preflight 실패, 파일 생성 없음 |
| 디스크 여유 공간 부족 | preflight 실패 또는 archive phase 실패, partial 삭제 |
| 백업 중 취소 | `cancelled`, temp dir와 `.part` 삭제 |
| callback URL host가 allowlist 밖 | job 등록 거절 |
| archive SHA256 불일치 | restore preflight 실패 |
| target DB가 비어 있지 않음 | restore preflight 실패 |
| target DB가 현재 운영 DB와 같음 | 기본 모드에서는 거절 |
| PostgreSQL/PostGIS major mismatch | 경고 또는 실패. 정책은 restore preflight에서 선택 |
| 복원 중 취소 | target DB drop 또는 보존 정책에 따라 정리 |

T-046 1차 구현에서 아직 완전 자동화하지 않은 실패/예외 항목:

- ~~디스크 여유 공간 사전 추정은 아직 명시적으로 계산하지 않는다.~~ **T-228에서 구현됨**: `run_backup_job`이 dump 시작 전(디렉터리 생성 전) `pg_database_size × backup_space_safety_factor(기본 1.3)`로 temp(dump)·destination(archive) 여유 공간을 `estimate_backup_space_requirement`로 추정하고, 부족하면 `InvalidInputError`로 fail-fast한다(temp·destination 동일 파일시스템이면 합산). `KTG_BACKUP_REQUIRE_FREE_SPACE_CHECK=false`로 우회. `pg_dump`/`tar` 실패는 여전히 job 실패와 artifact `failed` 상태로 남긴다.
- callback retry/backoff와 attempt 기록은 T-050 2차에서 구현했다. 수신자 측 replay 저장소는 이 저장소가 관리하지 않으므로, 운영자가 callback endpoint에서 timestamp window와 callback ID de-duplication을 적용해야 한다. retry 중복 처리는 `(artifact_id, event)` 멱등 key를 별도로 둔다.
- 복원 중 취소된 target DB 자동 drop은 아직 구현하지 않았다. 운영 안전을 위해 target DB는 새 빈 DB로 제한하고, 취소/실패 후 정리는 운영자가 명시적으로 수행한다.
- PostgreSQL/PostGIS major mismatch는 manifest에 기록하지만 restore preflight에서 hard fail로 막지는 않는다.

### 시나리오 누락 점검

| 관점 | 확인 항목 | 설계 반영 |
|------|-----------|-----------|
| 시작 전 검증 | 저장 경로, callback host, 디스크 여유 공간, 충돌 job 존재 여부 | backup/restore preflight에서 차단 |
| 진행률 | `pg_dump`/`pg_restore`가 정확한 row progress를 주지 않는 문제 | phase 추정 progress + stage/log/size/elapsed time 병행 표시 |
| 취소 | subprocess와 partial 파일/DB 정리 | phase별 cancel 규칙과 `.part` archive/temp dir 삭제 |
| 완료 알림 | callback 실패가 artifact 성공을 뒤집는 문제 | `callback_state`와 `manifest.callback_delivery`를 artifact state와 분리 |
| 다운로드 | 대용량 파일을 API 프로세스 메모리에 올리는 문제 | streaming 또는 web server offload |
| 복원 안전 | 운영 DB 덮어쓰기 위험 | 기본 `new_database`, 현재 DB와 같은 target 거절 |
| 검증 범위 | 전국 full-load 재실행 비용 | 대구광역시 부분 DB로 최초 통합 검증 |
| 감사 추적 | 어떤 원천 기준월/row count에서 만든 백업인지 불명확 | `manifest.json`, `source_set`, `row_counts`, SHA256 저장 |
| 보존 정책 | 오래된 artifact 누적 | `backup_artifact_ttl_days`, delete endpoint, `expired` state. **T-229**: backup finalize가 `expires_at = finalize 시각 + retention_days`(미지정 시 `backup_artifact_ttl_days`)와 `retention_class='default'`를 `update_artifact`로 기록(이전엔 항상 NULL). 자동 만료 정리(janitor)는 T-230 (주기 실행은 Dagster `backup_retention_janitor_daily` 06:00 — `docs/architecture/dagster-boundary.md` §5, 2026-08-18). |
| 보안 | path traversal, symlink escape, SSRF, secret 유출 | allowlist path, tokenized download, callback host allowlist, secret redaction |

## 구현 후 테스트 항목

- 완료: unit path allowlist, symlink escape, artifact filename, callback host allowlist.
- 완료: unit `pg_dump`/`pg_restore` command builder password redaction과 `PGPASSWORD` env 분리.
- 완료: unit manifest/checksum round-trip과 checksum mismatch 실패.
- 완료: unit restore target DSN 생성, download token 검증.
- 완료: API app contract route test.
- 완료: CLI command help contract test.
- 완료: frontend unit `backup-workflow` download URL, phase, terminal state, checksum/profile 표시.
- 완료: 대구 부분 DB backup → restore → row count 비교.
- 완료: 복원 DB geocode/reverse smoke test.
- 완료: Windows Playwright mock API 기반 `/admin/backups` 렌더, backup/restore submit, download link 확인.
- 보류: corrupted archive restore 실패 통합 테스트. 현재 unit checksum mismatch로 핵심 helper를 검증했고, 실제 corrupted `.tar.zst` 통합은 비용 대비 후속 hardening으로 둔다.
- 완료: callback HMAC header, retry/backoff, attempt별 callback ID, delivery manifest 기록.

## 후속 hardening 후보

- 디스크 여유 공간 사전 추정과 dump/archive 예상 크기 경고.
- callback 수신 endpoint 예제와 replay window/de-duplication 및 `(artifact_id, event)` 멱등 운영 가이드.
- restore 취소 시 target DB 자동 drop 또는 quarantine 정책.
- PostgreSQL/PostGIS major mismatch hard-fail 정책.
- `pg_dump`/`pg_restore` verbose line count보다 더 안정적인 progress estimator.

## 비상 부분 복원 (allow_partial, T-243)

> **비상 최후 수단이다.** 기본은 `allow_partial=false`로, 내부 checksum이 하나라도 깨지면 복원 전체를
> 중단한다(회귀 0). 백업본이 유일한 사본이고 일부 테이블 데이터 파일만 손상됐을 때에 한해 손상되지
> 않은 테이블이라도 살리기 위한 경로다. **일반 복원에 켜지 말 것** — 손상 테이블의 데이터는 조용히
> 비워진다.

`RestoreCreateRequest.allow_partial=true`일 때 복원은 다음을 한다(`infra/partial_restore.py` + `run_restore_job`).

1. `verify_internal_checksums`(첫 실패에서 중단) 대신 `collect_internal_checksum_failures`로 **손상 파일 전체 목록**을 모은다.
2. `partition_checksum_failures`로 손상 파일을 분류한다.
   - `manifest.json` / `dump/toc.dat` 손상 → **하드 실패**(신뢰할 TOC가 없으면 선택 복원 자체가 무의미).
   - `dump/<dumpId>.dat`(테이블 데이터 파일)만 손상 → 스킵 가능.
3. `pg_restore -l`로 TOC를 읽어 `build_partial_restore_uselist`가 손상 dumpId에 해당하는 엔트리만 `;`로 주석 처리한 `--use-list` 파일을 만든다.
4. `pg_restore --use-list`로 **멀쩡한 테이블만 복원**한다(손상 테이블은 스키마는 생성되되 데이터는 비어 있음).
5. 복원 로그 manifest `partial_restore` 블록에 스킵한 `dumpId`/파일/엔트리/개수를 기록한다. row-count reconcile(T-233)은 스킵된 테이블을 행 수 불일치 **warning**으로 남겨 무엇이 비었는지 드러낸다.

합격: 일부 `.dat` 손상 시 해당 테이블만 스킵하고 나머지는 복원, `allow_partial=false`면 기존(전체 중단) 동작. 손상 archive를 실제로 주입하는 통합 검증은 **T-245**(fault injection)에서 수행한다.

## 공용 DB instance (T-312)

T-308로 geo DB(`kor_travel_geo`, `kor_travel_geo_dagster`)는 공용 control-plane PostgreSQL 16/PostGIS 3.5
instance(`kor-travel-shared-postgres`)로 옮겨졌다. 2026-09-29 read-only 조회 기준 app role
`kor_travel_geo_app`은 `rolsuper=f`, `rolcreatedb=f`, `has_database_privilege(..., 'postgres', 'CONNECT')=f`
이고, 두 DB의 owner다. extension(postgis, pg_trgm, unaccent, pg_stat_statements)은 cluster admin
(`shared_admin`)이 만든 `x_extension` schema에 있고 app role은 그 schema에 `USAGE`만 있다.

### capability 판정과 조기 거절

ADR-036 hot-swap(maintenance DB에서 `ALTER DATABASE RENAME`), restore drill(throwaway
`CREATE DATABASE`), blue-green scratch full-load(scratch `CREATE DATABASE`), `db_restore`(새 DB 복원,
실패 시 maintenance DB에서 drop/quarantine)는 모두 `CREATEDB`(또는 superuser)와 maintenance DB
`postgres` `CONNECT`가 필요하다. `infra/db_capabilities.py`가 연결 role을 한 번 조회해 5분 캐시하고,
부족하면 job을 만들기 전에 `UnsupportedOnInstanceError`(`E0410`, HTTP 409)로 거절한다.

| 설정 | 동작 |
|------|------|
| `KTG_DB_LIFECYCLE_MODE=auto` (기본) | role 조회. `CREATEDB` + maintenance DB `CONNECT`면 지원 — 전용 superuser instance(dev/테스트)는 그대로 전부 허용 |
| `KTG_DB_LIFECYCLE_MODE=enabled` | 조회 없이 허용 (운영자가 권한을 따로 준 경우 override) |
| `KTG_DB_LIFECYCLE_MODE=disabled` | 조회 없이 차단 |

maintenance DB는 기본 `postgres`다. hot-swap plan/execute/rollback만 요청의 `maintenance_database`(API 필드,
`ktgctl serving hot-swap-plan --maintenance-db`)로 다른 DB를 고를 수 있으므로, 그 요청은 **실제로 연결할 DB의
`CONNECT`**를 조회한다(T-321). 예를 들어 `postgres` `CONNECT`가 막힌 hardened cluster에서 `CREATEDB` role이
`maintenance_database=kor_travel_geo_admin`을 쓰면 hot-swap은 통과하고, 반대로 `postgres`만 되는 role이 연결할 수
없는 DB를 고르면 raw 연결 오류 대신 E0410으로 거절된다. 이름을 잘못 적은 DB는 `maintenance DB '<name>' 없음`으로
구분된다. `GET /v1/admin/db-capabilities`·restore drill·scratch·복원 cleanup은 계속 `postgres` 기준이며, probe
캐시(5분)는 연결 URL + maintenance DB별로 따로 둔다.

| 기능 | 1차(API) | 2차(Dagster/CLI) |
|------|----------|------------------|
| hot-swap plan/execute/rollback | `client.restore_hot_swap_plan`/`execute_*` 진입 즉시, 요청의 `maintenance_database` 기준 (`/restores/hot-swap*`, `ktgctl serving hot-swap-plan`) | — |
| restore drill | `client.run_restore_drill` 진입 즉시 (`ktgctl backup restore-drill`) | daily schedule은 tick 평가에서 `SkipReason`(run 없음, T-321), `restore_drill` op는 시작 시 `Failure`(수동 launch) |
| scratch full-load (`full_load_batch` + `target_database`) | `launch_full_load_batch_dagster_run` — scratch DB 생성·row insert 전 | `run_full_load_batch` op가 scratch engine 생성 전 `Failure` |
| `db_restore` (`new_database`/`replace_current`) | `POST /restores` — load_jobs row·Dagster run 생성 전 | `run_db_restore` op leaf 첫 단계(row를 사유와 함께 failed), `run_restore_job` 첫 단계(`ktgctl restore create`) |

- `target_dsn`을 명시한 복원은 그 DSN의 자격증명으로 도는 운영자 경로라 게이트하지 않는다 — 공용 instance에서
  지원하는 복원은 이 경로다(아래 "공용 instance에서 복원하기").
- `db_restore`의 E0410 `hint`는 role 사유 뒤에 그 절차를 붙인다(`; 공용 instance 복원 절차: ...`). admin UI 복원
  위저드도 같은 절차를 안내한다.
- `POST /restores/dry-run`은 archive 검증용으로 계속 동작하되 같은 사유를 `blockers`에 넣어 `can_restore=false`를 돌려준다.
- `POST /restores/hot-swap-plan`이 E0410으로 거절돼도 dry-run처럼 `serving_release.hot_swap_plan` `denied` 감사
  행(`error_code=E0410`, payload `blockers`에 사유)을 남긴다(T-321). 감사 기록 실패는 409 응답을 가리지 않는다.
- daily restore drill schedule(`backup_restore_drill_daily`)은 기본 STOPPED다. 공용 instance에서 켜 두어도 매일
  `Failure` run이 쌓이지 않고 tick이 사유와 함께 skip된다. capability 조회 자체가 실패하면(DB 연결 불가 등)
  skip하지 않고 run을 만든다 — op guard가 다시 판정하고 실패는 run-failure sensor 알림으로 간다.
- `GET /v1/admin/db-capabilities`가 판정(`supported`, `reason`, role 속성, `maintenance_database`)을 돌려주고, admin UI
  백업/복원 화면은 이를 읽어 복원 제출·hot-swap plan/실행/rollback을 비활성화하고 "공용 DB instance에서는 지원하지
  않음 — 운영자가 manager ktdctl로 수행"을 표시한다. `hot-swap-source-verify`는 수명주기 권한이 필요 없어 그대로 둔다.

### 공용 instance에서 복원하기 (지원 절차, T-321)

게이트는 `target_dsn` 없는 복원(app 자격증명으로 도는 `target_database` 복원)을 role 권한(`CREATEDB` + maintenance
`CONNECT`)으로 판정해 막는다 — 실패 시 대상 DB drop/quarantine이 maintenance DB를 쓰기 때문이다. `target_dsn`을
명시한 복원은 운영자 경로라 게이트하지 않으므로, cluster admin이 빈 DB를 만들어 주면 app role로 `target_dsn` 복원이
된다(비-superuser TOC 필터 + `--no-owner --no-privileges`, 아래 "비-superuser(app role) 복원"). 게이트 자체는
넓히지 않았다(T-321 결정 — 넓히려면 cleanup이 maintenance DB 없이 동작해야 한다). 이 경로는 `tests/integration/test_t312_shared_instance_restore.py`(`app_role` case)가 NOCREATEDB role에서
검증한다 — 같은 role의 `target_database` 복원이 E0410으로 거절되고 hint에 이 절차가 있는 것도 함께 확인한다.

1. **cluster admin**: app role 소유의 빈 DB와 `x_extension`·extension을 만든다 — 아래 "cluster admin 복원 절차"의
   1)번과 같다(`CREATE DATABASE <새 DB> OWNER kor_travel_geo_app TEMPLATE template0` + `REVOKE CONNECT ... FROM
   PUBLIC` + `CREATE SCHEMA x_extension` + `GRANT USAGE ... TO kor_travel_geo_app` + `CREATE EXTENSION ... WITH SCHEMA
   x_extension`).
2. **운영자**: `pg_restore` 16·`zstd`가 있는 geo API 컨테이너(`docker/api.Dockerfile`)에서 app role 자격증명으로 복원한다.
   DSN에 비밀번호를 넣지 말고 `PGPASSWORD`(또는 `~/.pgpass`)로 준다 — 명령행 인자는 process 목록에 보인다.

   ```bash
   PGPASSWORD=<app role 비밀번호> ktgctl restore create --artifact-id <db_backup artifact_id> \
     --target-dsn "postgresql://kor_travel_geo_app@<host>:11000/<새 DB>"
   ```

   복원 로그 manifest `preprovisioned_toc_skipped`에 건너뛴 extension/`x_extension` entry가 남고, smoke test가
   app role의 `x_extension` `USAGE`까지 확인한다.
3. 실패하면 job 소유 대상 DB의 자동 drop/quarantine은 maintenance DB에 연결하지 못해 실패로 끝난다(best-effort,
   `db_restore.target_cleanup` `failed` 감사) — 남은 DB는 admin이 drop한다.
4. serving 교체(ADR-036 rename)는 `CREATEDB`가 필요하므로 계속 admin이 수행한다.

admin UI는 `target_dsn`을 받지 않는다 — DSN 자격증명이 브라우저를 거쳐 `load_jobs.payload`·Dagster run config에 그대로
남기 때문이다. `POST /v1/admin/restores`에 `target_dsn`을 넣어도 동작하지만 같은 이유로 CLI를 권장한다.

### 백업 형식 (app role로 찍어도 복원 가능)

- `pg_dump`는 owner와 ACL(GRANT/REVOKE) entry를 **그대로 담는다**(`--no-owner`/`--no-privileges`를 붙이지 않는다).
  공용 instance에서 의미 있는 grant는 admin의 `GRANT USAGE ON SCHEMA x_extension TO kor_travel_geo_app` 하나인데,
  이것은 dump의 `ACL - SCHEMA x_extension` entry에만 있다. superuser `pg_restore --clean --if-exists`는 `x_extension`을
  지우고 dump에서 다시 만들므로, ACL을 뺀 dump를 superuser가 복원하면 app role이 `x_extension` USAGE를 잃고 모든
  PostGIS/pg_trgm 호출이 `function st_makepoint(...) does not exist`로 실패한다(pg_restore는 exit 0). owner·ACL은
  복원 시점에, 복원 role이 적용할 수 없을 때만(비-superuser, 아래) 뺀다.
- `--no-owner`는 어차피 archive(directory) 형식 `pg_dump`에서 무시된다(owner가 TOC에 남음, PG16 실측).
- app role의 `pg_dump`는 공용 instance에서 성립한다: `public`/`ops`의 모든 relation을 app role이 소유(SELECT
  가능 확인)하고, extension config table `x_extension.spatial_ref_sys`는 `PUBLIC` `SELECT`가 있다
  (config 필터로 표준 SRID는 빠지므로 dump되는 행은 사용자 추가 SRID뿐).
- dump 명령·checksum/manifest/verify는 T-312 이전과 같다. 옛 백업도 그대로 verify되고 아래 경로로 복원된다.
- 복원 smoke test(`run_smoke_test`, restore drill, hot-swap 후 smoke 공통)는 대상 DB owner가 extension이 사는
  schema(`x_extension` 등)에 `USAGE`가 있는지도 확인한다 — grant가 빠진 복원을 성공으로 보고하지 않고
  `GRANT USAGE ON SCHEMA ... TO <owner>` 힌트로 실패한다.

### 비-superuser(app role) 복원

`run_restore_job`은 복원 대상 DB에서 현재 role이 superuser인지, 관리할 수 없는(소유하지 않은) extension과 그
extension이 사는 admin 소유 schema를 조회한다(`infra/restore_toc.py`). 비-superuser면:

1. `pg_restore -l` TOC에서 해당 `EXTENSION`/`COMMENT - EXTENSION`, `SCHEMA - x_extension`,
   `ACL/COMMENT - SCHEMA x_extension`, namespace가 `x_extension`인 entry(`TABLE DATA x_extension spatial_ref_sys`)를
   `;`로 주석 처리한 `--use-list`를 만든다(T-243 부분 복원 list와 합성). `public`/`pg_catalog`는 절대 schema 단위로
   거르지 않는다.
2. `pg_restore`에 `--no-owner --no-privileges`를 붙인다 — 옛 owner(`addr` 등)로의 `ALTER OWNER`나 없는 role로의
   `GRANT`가 실패하지 않고, 모든 객체가 복원 role 소유가 된다.
3. 건너뛴 entry는 복원 로그 manifest `preprovisioned_toc_skipped`에 남는다.

superuser 복원(`target_dsn`에 cluster admin 자격증명)은 필터가 비고 옵션도 붙지 않아 기존과 같다 — dump의
`SCHEMA - x_extension`·`ACL - SCHEMA x_extension`으로 schema와 app role `USAGE`를 다시 만든다. 로컬 재현(공용
instance와 같은 role/schema 구성의 PG16 컨테이너)에서 필터 없이 app role로 복원하면 `must be owner of extension`/
`must be owner of schema x_extension`/`schema "x_extension" already exists`/`permission denied for table
spatial_ref_sys`로 exit 1, 필터와 옵션을 적용하면 exit 0이었다. 두 경로(app role 복원, superuser 복원) 모두
`tests/integration/test_t312_shared_instance_restore.py`(opt-in, `KTG_TEST_PG_DSN`=superuser)가 app role로 찍은
백업을 복원한 뒤 app role 연결에서 PostGIS 함수가 풀리는지 확인한다.

### cluster admin 복원 절차 (manager `ktdctl` 상당)

공용 instance에서는 새 DB 생성·복원·rename을 운영자가 한다. app role로 찍은 백업을 app role 소유의 새 DB로
복원하는 수동 절차(로컬 재현으로 exit 0·relation 194개 모두 `kor_travel_geo_app` 소유 확인):

```bash
# 1) 새 DB (owner = app role) + extension 사전 구성 — superuser/cluster admin
psql -d postgres -c "CREATE DATABASE kor_travel_geo_restore OWNER kor_travel_geo_app TEMPLATE template0" \
                 -c "REVOKE CONNECT ON DATABASE kor_travel_geo_restore FROM PUBLIC"
psql -d kor_travel_geo_restore \
  -c "CREATE SCHEMA x_extension" -c "GRANT USAGE ON SCHEMA x_extension TO kor_travel_geo_app" \
  -c "CREATE EXTENSION postgis WITH SCHEMA x_extension" -c "CREATE EXTENSION pg_trgm WITH SCHEMA x_extension" \
  -c "CREATE EXTENSION unaccent WITH SCHEMA x_extension" -c "CREATE EXTENSION pg_stat_statements WITH SCHEMA x_extension"

# 2) archive 해제 + 내부 checksum 확인
mkdir restore_work && tar --use-compress-program=zstd -xf <backup>.tar.zst -C restore_work
(cd restore_work && sha256sum -c --quiet checksums.sha256)

# 3) 미리 만든 extension/x_extension entry를 뺀 TOC list
pg_restore -l restore_work/dump \
  | grep -v -E '^[0-9]+; [0-9]+ [0-9]+ (SCHEMA - x_extension |ACL - SCHEMA x_extension |EXTENSION - |COMMENT - EXTENSION |[A-Z][A-Z ]* x_extension )' \
  > restore_work/restore.list

# 4) app role 권한으로 복원 (--role = SET ROLE → 모든 객체가 app role 소유)
pg_restore --format=directory --jobs=4 --no-owner --no-privileges --role=kor_travel_geo_app \
  --use-list restore_work/restore.list --dbname "postgresql://<admin>@<host>:11000/kor_travel_geo_restore" \
  restore_work/dump
```

이후 `ANALYZE`, smoke, 그리고 필요하면 운영 DB와의 rename 교체(ADR-036 절차)를 admin이 수행한다. 교체 전에
복원본의 `alembic_version`이 앱 head보다 낮으면 복원본을 대상으로 `alembic upgrade head`를 먼저 돌린다(위
"복원 작업 흐름"의 T-319 항목).

manager `ktdctl`이 필터·`--role` 없이 plain superuser `pg_restore --clean --if-exists`로 복원해도 된다 — dump의
`SCHEMA - x_extension`·`ACL - SCHEMA x_extension` entry가 schema와 `kor_travel_geo_app` `USAGE`를 다시 만들고,
owner는 dump 그대로(`kor_travel_geo_app`)다. 어느 경로든 교체 전에 app role 연결에서
`SELECT has_schema_privilege('x_extension', 'USAGE')`가 참이고 PostGIS 함수가 풀리는지 확인한다.

### 다른 cluster로 superuser 복원 — dump owner role 사전 생성 (T-321)

superuser 복원(`ktgctl restore create --target-dsn <superuser DSN>`, manager plain `pg_restore`)은 dump의 owner와
ACL을 그대로 적용한다(`--no-owner`를 붙이지 않는다 — 위 "백업 형식"). 그래서 공용 instance의 백업을 **그 role이 없는
다른 cluster**(dev·재해 복구용 새 instance 등)에 superuser로 복원하면 `ALTER ... OWNER TO kor_travel_geo_app`,
`ALTER SCHEMA x_extension OWNER TO shared_admin`, `GRANT USAGE ... TO kor_travel_geo_app`가
`role "..." does not exist`로 실패하고 `pg_restore`가 exit 1로 끝나 복원 job도 실패한다. 복원 전에 dump가 참조하는
role을 대상 cluster에 **`NOLOGIN`으로** 만든다 — 객체 소유와 grant만 받는 role이라 로그인 경로가 늘지 않는다.

```bash
# 1) archive 해제 뒤 dump가 참조하는 owner/grantee role 목록 (공용 instance 백업이면 kor_travel_geo_app, shared_admin)
pg_restore --schema-only --file=- restore_work/dump \
  | grep -oE '(OWNER TO|TO) [a-z_][a-z0-9_]*;' | awk '{print $NF}' | tr -d ';' | sort -u

# 2) 대상 cluster에 없는 role만 NOLOGIN으로 생성 — superuser/cluster admin (public·postgres는 제외)
psql -d postgres -c "CREATE ROLE kor_travel_geo_app NOLOGIN" -c "CREATE ROLE shared_admin NOLOGIN"
```

- 대상 cluster에 같은 이름의 role이 이미 있으면(예: 그 cluster도 geo app role을 쓴다) 만들지 않는다 — 그 role이
  그대로 owner가 된다.
- 복원된 객체는 `kor_travel_geo_app` 소유다. 그 cluster의 앱이 superuser가 아닌 다른 login role로 붙으면
  `GRANT kor_travel_geo_app TO <login role>`로 멤버십을 주거나, 처음부터 그 login role 자격증명의 `target_dsn`으로
  복원한다(비-superuser 경로 — owner·ACL을 빼고 모든 객체가 복원 role 소유가 된다).
- 복원 경로가 role을 자동으로 만들지는 않는다 — role은 cluster 전역 객체라 DB 하나의 복원이 cluster에 부작용을
  남기지 않도록 운영자가 명시적으로 만든다.

로컬 재현(PostGIS 16-3.5 컨테이너, 2026-09-29): app role이 owner이고 `x_extension`이 별도 admin role 소유(app role은
`USAGE`만)인 DB를 app role로 `pg_dump`한 뒤, 두 role을 없앤 cluster에 superuser `pg_restore --clean --if-exists`로
복원하면 `role "..." does not exist` 오류(`errors ignored on restore: 4`)로 exit 1, 두 role을 `NOLOGIN`으로 만든 뒤 새 DB에 복원하면 exit 0이었고
테이블 owner·`x_extension` owner·app role `USAGE`가 dump 그대로 복원됐다. 위 1)의 목록 명령은 정확히 그 두 role을
돌려줬다.
