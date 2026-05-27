# T-046: 적재 완료 DB 백업/복원 구현 기록

## 범위

본 문서는 완전히 또는 부분적으로 적재된 PostgreSQL + PostGIS DB를 빠르게 백업하고 복원하기 위한 설계와 T-046 구현 결과를 함께 기록한다. 사용자는 전체 데이터를 다시 로드하지 않고도, 검증된 DB 상태를 압축 아카이브로 저장하고 필요할 때 복원할 수 있어야 한다.

T-046에서는 코드 구현, 단위 테스트, 관리 UI, OpenAPI 타입 동기화, Windows Playwright 렌더 검증, 대구광역시 부분 적재 DB 기반 실제 backup → restore 검증까지 수행했다. 전국 full-load 재실행은 본 task 범위가 아니며, 후속 T-027/T-047에서 별도 수행한다.

## 구현 요약

구현된 파일과 역할은 다음과 같다.

| 영역 | 파일 | 내용 |
|------|------|------|
| DTO | `src/kraddr/geo/dto/admin.py` | `BackupCreateRequest`, `RestoreCreateRequest`, `BackupArtifact`, `db_backup`/`db_restore` job kind 추가 |
| 설정 | `src/kraddr/geo/settings.py` | `backup_allowed_dirs`, `backup_temp_dir`, `backup_default_jobs`, `backup_default_compression_level`, `backup_artifact_ttl_days`, `backup_callback_allowed_hosts`, `backup_download_token_secret` 추가 |
| 실행 로직 | `src/kraddr/geo/infra/backup.py` | path allowlist 검증, `pg_dump -Fd`, `tar.zst`, checksum, manifest, `pg_restore -Fd`, target DB empty check, callback, download token |
| metadata | `src/kraddr/geo/infra/admin_repo.py` | `ops.artifacts` insert/get/update/delete helper 추가 |
| job queue | `src/kraddr/geo/api/_jobs.py`, `src/kraddr/geo/api/app.py` | handler payload에 `_job_id` 주입, `db_backup`/`db_restore` handler 등록, full-load batch successor 계산에서 control kind로 분리 |
| REST API | `src/kraddr/geo/api/routers/admin.py` | `/v1/admin/backups`, `/v1/admin/backups/{artifact_id}`, `/download`, `/delete`, `/v1/admin/restores`, `/v1/admin/jobs/{job_id}/events` 추가 |
| CLI | `src/kraddr/geo/cli/main.py` | `kraddr-geo backup create/list/show/delete`, `kraddr-geo restore create` 추가 |
| UI | `kraddr-geo-ui/app/admin/backups/page.tsx`, `components/admin/BackupsPanel.tsx` | 백업 생성, 복원 등록, job 진행률/취소, artifact 목록, 다운로드/삭제 UI |
| 타입 | `openapi.json`, `kraddr-geo-ui/types/api.gen.ts`, `kraddr-geo-ui/lib/schemas.gen.ts` | OpenAPI와 프론트엔드 생성 타입 갱신 |

현재 구현의 기본 동작은 다음과 같다.

1. `POST /v1/admin/backups` 또는 `kraddr-geo backup create`가 `db_backup` job을 등록/실행한다.
2. 백업 대상 디렉터리는 `KRADDR_GEO_BACKUP_ALLOWED_DIRS` 하위 resolve path만 허용한다. 상대 경로는 첫 allowlist root 기준으로 해석한다.
3. `pg_dump --format=directory --jobs=N` 결과를 임시 디렉터리에 만든다.
4. `manifest.json`, `checksums.sha256`, job log를 만들고 `tar --use-compress-program=zstd -T0 -<level>`로 `.tar.zst.part` 파일을 생성한다.
5. archive SHA256과 크기를 계산한 뒤 `.part` 파일을 최종 `.tar.zst` 경로로 rename한다.
6. archive SHA256과 크기를 `ops.artifacts(artifact_type='db_backup')`에 저장한다.
7. 완료 artifact는 HMAC 기반 download token이 붙은 `download_url`을 API 응답에 포함한다.
8. `POST /v1/admin/restores` 또는 `kraddr-geo restore create`는 artifact 또는 archive path를 받아 새 빈 DB에 `pg_restore --format=directory --jobs=N`로 복원한다.
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
kraddr_geo_backup_20260526T153000Z_pg16_postgis34_daegu.tar.zst
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
    "name": "kraddr_geo",
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
    "mv_geocode_target": 0
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
| `dump` | 0.05~0.70 | `pg_dump --verbose` object count와 dump 디렉터리 증가량 |
| `archive` | 0.70~0.90 | 압축된 byte / dump 디렉터리 예상 byte |
| `checksum` | 0.90~0.97 | archive SHA256 계산 byte |
| `finalize` | 0.97~1.00 | metadata 저장, callback, cleanup |

`pg_dump`는 정확한 row-level progress를 제공하지 않으므로 진행률은 phase별 추정값이다. UI에는 "추정 진행률"임을 표시하되, `current_stage`, 현재 처리 파일, 현재 archive 크기, elapsed time을 함께 보여 준다.

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

운영 DB를 직접 덮어쓰는 `--replace-current`는 기본 금지다. 필요한 경우 maintenance mode, 모든 app connection 종료, typed confirmation, 백업 선행 생성, rollback plan을 요구한다. 일반 운영 경로는 "새 DB 복원 → 검증 → `KRADDR_GEO_PG_DSN` 전환 → 앱 재시작"이다.

복원 진행률 phase:

| phase | progress 범위 | 기준 |
|-------|----------------|------|
| `preflight` | 0.00~0.05 | archive/target DB 검증 |
| `extract` | 0.05~0.20 | 압축 해제 byte |
| `restore` | 0.20~0.80 | `pg_restore --verbose` object count |
| `analyze` | 0.80~0.90 | 대상 table ANALYZE |
| `validate` | 0.90~0.98 | row count, smoke, 선택 consistency |
| `finalize` | 0.98~1.00 | metadata 저장, callback, cleanup |

## 저장 위치와 보안

사용자가 지정하는 저장 공간은 브라우저 로컬 경로가 아니라 서버가 접근할 수 있는 경로다. UI에서는 다음 둘 중 하나만 허용한다.

1. 운영자가 설정한 allowlist root 중 하나를 선택한다.
2. allowlist 하위 상대 경로를 입력한다.

설정 예:

```text
KRADDR_GEO_BACKUP_ALLOWED_DIRS=/mnt/f/backups/kraddr-geo,/mnt/d/backups/kraddr-geo
KRADDR_GEO_BACKUP_TEMP_DIR=/tmp/kraddr-geo-backup
KRADDR_GEO_BACKUP_DEFAULT_JOBS=4
KRADDR_GEO_BACKUP_ARTIFACT_TTL_DAYS=30
KRADDR_GEO_BACKUP_CALLBACK_ALLOWED_HOSTS=localhost,127.0.0.1,internal.example
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
    "destination_dir": "/mnt/f/backups/kraddr-geo",
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
    "target_database": "kraddr_geo_restore_20260526",
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
  "job_id": "job_...",
  "artifact_id": "backup_...",
  "state": "done",
  "progress": 1.0,
  "archive_path": "/mnt/f/backups/kraddr-geo/kraddr_geo_backup_....tar.zst",
  "download_url": "http://localhost:8000/v1/admin/backups/backup_.../download",
  "sha256": "...",
  "size_bytes": 123456789,
  "finished_at": "2026-05-26T15:40:00Z"
}
```

T-046 1차 구현은 callback을 terminal state(`done`, `failed`, `cancelled`)에서 1회 시도하고, 성공/실패를 `callback_state`에 따로 기록한다. callback 실패는 백업 파일 자체의 성공 여부를 뒤집지 않는다. exponential backoff와 제한 횟수 재시도는 후속 hardening에서 추가한다.

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
- `replace_current` 모드는 숨김 또는 별도 위험 모달 뒤로 둔다.
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
- 빈 DB `kraddr_geo_t046_daegu`를 만든다.
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
3. 진행률이 `preflight → dump → archive → checksum → finalize`를 지나 `done`이 되는지 확인한다.
4. artifact 파일이 존재하고 size > 0인지 확인한다.
5. `manifest.json`에 DB 이름, row counts, source set, format, jobs가 들어 있는지 확인한다.
6. SHA256이 metadata와 일치하는지 확인한다.
7. callback 테스트 서버를 켠 경우 terminal callback이 1회 이상 도착했는지 확인한다.

### 복원 검증

1. 빈 DB `kraddr_geo_t046_daegu_restore`를 만든다.
2. archive를 restore job으로 복원한다.
3. restore progress가 `preflight → extract → restore → analyze → validate → finalize`를 지나 `done`이 되는지 확인한다.
4. 원본 DB와 복원 DB의 핵심 row count를 비교한다.
5. 같은 대구 주소 geocode와 reverse geocode가 성공하는지 확인한다.
6. `mv_geocode_target`이 비어 있지 않고, 복원 직후 추가 full-load 없이 조회 가능한지 확인한다.

### 실제 검증 결과 (2026-05-27)

검증 환경:

| 항목 | 값 |
|------|----|
| 작업 디렉터리 | `/home/digitie/dev/python-kraddr-geo` |
| Docker DB | `kraddr-geo-t027-db-1`, `localhost:15432` |
| source DB | `kraddr_geo_t046_daegu` |
| restore DB | `kraddr_geo_t046_daegu_restore` |
| 백업 디렉터리 | `/tmp/kraddr-t046/backups` |
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
| 백업 파일 | `/tmp/kraddr-t046/backups/t046_daegu_backup.tar.zst` |
| 파일 크기 | 86,752,398 bytes, 약 83 MiB |
| archive SHA256 | `3718e98d25226215606d6324ce19422756fe900721abc22c060583322329cb57` |
| `db_backup` artifact 상태 | `available` |
| `db_backup` artifact 시간 | 5.70초 |
| `db_restore_log` artifact 상태 | `available` |
| `db_restore` 시간 | 21.25초 |
| 복원 row count | source와 동일 (`228875/26594/228610/291281/228875`) |
| smoke | 복원 DB에서 `대구광역시 중구 공평로 88` geocode `OK`, 해당 좌표 reverse `OK` |

검증 중 발견해 코드에 반영한 문제:

- `KRADDR_GEO_BACKUP_ALLOWED_DIRS=/tmp/a,/tmp/b`처럼 문서에 적은 CSV 환경변수가 pydantic-settings의 complex JSON decoding 단계에서 실패했다. `Settings.backup_allowed_dirs`와 `backup_callback_allowed_hosts`에 `NoDecode`를 적용해 CSV validator가 실제 env 값에도 동작하도록 수정했다.
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

- 디스크 여유 공간 사전 추정은 아직 명시적으로 계산하지 않는다. `pg_dump`/`tar` 실패는 job 실패와 artifact `failed` 상태로 남긴다.
- callback retry는 1회 delivery 시도만 구현했다. 재시도 정책, backoff, 재시도 횟수 기록은 후속 hardening으로 둔다.
- 복원 중 취소된 target DB 자동 drop은 아직 구현하지 않았다. 운영 안전을 위해 target DB는 새 빈 DB로 제한하고, 취소/실패 후 정리는 운영자가 명시적으로 수행한다.
- PostgreSQL/PostGIS major mismatch는 manifest에 기록하지만 restore preflight에서 hard fail로 막지는 않는다.

### 시나리오 누락 점검

| 관점 | 확인 항목 | 설계 반영 |
|------|-----------|-----------|
| 시작 전 검증 | 저장 경로, callback host, 디스크 여유 공간, 충돌 job 존재 여부 | backup/restore preflight에서 차단 |
| 진행률 | `pg_dump`/`pg_restore`가 정확한 row progress를 주지 않는 문제 | phase 추정 progress + stage/log/size/elapsed time 병행 표시 |
| 취소 | subprocess와 partial 파일/DB 정리 | phase별 cancel 규칙과 `.part` archive/temp dir 삭제 |
| 완료 알림 | callback 실패가 artifact 성공을 뒤집는 문제 | `callback_state`를 artifact state와 분리 |
| 다운로드 | 대용량 파일을 API 프로세스 메모리에 올리는 문제 | streaming 또는 web server offload |
| 복원 안전 | 운영 DB 덮어쓰기 위험 | 기본 `new_database`, 현재 DB와 같은 target 거절 |
| 검증 범위 | 전국 full-load 재실행 비용 | 대구광역시 부분 DB로 최초 통합 검증 |
| 감사 추적 | 어떤 원천 기준월/row count에서 만든 백업인지 불명확 | `manifest.json`, `source_set`, `row_counts`, SHA256 저장 |
| 보존 정책 | 오래된 artifact 누적 | `backup_artifact_ttl_days`, delete endpoint, `expired` state |
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
- 보류: callback retry 기록. 현재 callback success/failure 1회 delivery 상태만 구현한다.

## 후속 hardening 후보

- 디스크 여유 공간 사전 추정과 dump/archive 예상 크기 경고.
- callback retry/backoff와 callback delivery attempt audit.
- restore 취소 시 target DB 자동 drop 또는 quarantine 정책.
- PostgreSQL/PostGIS major mismatch hard-fail 정책.
- `pg_dump`/`pg_restore` verbose line count보다 더 안정적인 progress estimator.
