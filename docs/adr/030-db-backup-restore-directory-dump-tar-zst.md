# ADR-030: 적재 완료 DB 백업/복원은 병렬 directory dump와 압축 아카이브로 수행한다

- 상태: accepted (T-046 1차 구현 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

## 컨텍스트

전국 전체 데이터를 처음부터 적재하면 텍스트 정본, SHP 대형 레이어, 링크 해소, MV refresh/swap, C1~C10 정합성 검증까지 수 시간 단위가 걸린다. 운영자는 검증이 끝난 DB 상태를 빠르게 보존하고, 장애나 재설치 뒤에는 원천 전체를 다시 적재하지 않고 복원할 수 있어야 한다.

plain SQL 또는 DDL 중심 dump는 대용량 운영 DB에서 현실적인 기본값이 아니다. 단일 `.sql` 스트림은 파일이 커지고 복원 병렬성이 약하며, PostGIS index와 MV data가 큰 DB에서 복구 시간이 길어진다. 반대로 Docker volume snapshot이나 `pg_basebackup` 같은 물리 백업은 빠를 수 있지만 PostgreSQL cluster와 파일시스템에 강하게 묶이므로 단일 DB 이식성이 낮다.

UI 요구사항도 있다. 백업/복원은 오래 걸리므로 요청-응답으로 묶지 않고 백그라운드 작업으로 실행해야 하며, 진행률, 취소, 완료 callback, 다운로드 링크가 필요하다.

## 결정

T-046의 기본 백업 형식은 `pg_dump -Fd --jobs <N>` directory format dump를 임시 디렉터리에 만든 뒤, `manifest.json`, checksum, job log와 함께 `tar.zst` 단일 압축 아카이브로 저장하는 방식으로 한다. 복원은 archive를 해제하고 `pg_restore -Fd --jobs <N>`로 새 빈 DB에 수행한다.

T-047 전국 DB 실측 보정: `pg_dump -Fd` directory 내부의 대형 table data는 이미 `.dat.gz`로 압축되어 있어 `tar.zst` 포장 단계의 추가 압축률은 매우 작았다. dump directory 4,313,361,824 bytes가 archive 4,308,457,630 bytes가 되어 약 4.9MiB만 줄었다. 따라서 이 ADR의 `tar.zst`는 압축률보다 단일 artifact 보관, UI 다운로드, checksum 검증을 단순화하기 위한 포장 형식으로 해석한다.

세부 결정:

1. 운영 기본값은 `directory_tar_zstd`다. `pg_dump -Fp` plain SQL은 디버깅 목적 외에는 사용하지 않는다.
2. 백업 profile은 `serving-ready`, `lean-serving`, `forensic`으로 나눈다. 기본 `serving-ready`는 `mv_geocode_target` data를 포함해 복원 직후 조회가 가능해야 한다.
3. 백업/복원 작업 kind는 `db_backup`, `db_restore`로 둔다. 초기 구현은 기존 `load_jobs` 기반 영속 큐를 재사용하되, REST 표면은 중립 alias `/v1/admin/jobs/*`를 우선 사용한다.
4. 백업 파일은 사용자가 지정한 서버 측 allowlist 하위 경로에 저장한다. 브라우저 로컬 경로를 직접 쓰지 않는다.
5. callback URL은 allowlist host만 허용한다. T-050 2차 이후 terminal delivery 경로(`done`, `failed`)는 제한 횟수 retry와 exponential backoff를 적용하고, payload body는 timestamp와 callback ID를 포함해 HMAC-SHA256으로 서명한다. callback 실패는 백업/복원 성공 여부와 별도로 `callback_state`와 `manifest.callback_delivery`에 기록한다.
6. UI는 `/admin/backups` 페이지를 추가한다. 백업 생성, 진행 중 작업, 백업 목록, 복원 탭을 제공하고, 완료된 artifact에는 다운로드 링크를 표시한다.
7. 복원은 기본적으로 새 빈 DB에만 허용한다. 현재 운영 DB를 덮어쓰는 `replace_current`는 maintenance mode, typed confirmation, 선행 백업, rollback plan을 요구하는 별도 위험 경로로 둔다.

## 보안과 운영 규칙

- `KTG_BACKUP_ALLOWED_DIRS` 하위 resolve path만 허용한다. `..`, symlink escape, absolute path 우회는 거절한다.
- 임시 파일은 `.part` archive 또는 임시 디렉터리에 쓰고, checksum 계산 후 최종 archive 경로로 rename한다.
- 백업 파일은 기본 `0600` 권한으로 만든다.
- 다운로드 endpoint는 내부망 전용이어도 artifact id와 token을 모두 요구한다.
- callback payload에는 DB password, DSN, API key를 넣지 않는다.
- 동시에 실행 중인 `full_load_batch`, `mv_refresh`, `db_restore`가 있으면 `db_backup` preflight에서 경고 또는 실패한다. `db_restore`는 다른 대형 job과 동시에 실행하지 않는다.

## 검증 기준

구현 첫 검증은 전국 full-load가 아니라 대구광역시 부분 적재 DB로 수행한다.

1. 빈 DB `kor_travel_geo_t046_daegu`에 대구 `juso`, `parcel_link`, `locsum`, `navi`, `shp`만 적재한다.
2. `resolve_text_geometry_links()`와 `refresh mv --swap` 후 row count와 geocode/reverse smoke test를 확인한다.
3. `db_backup`으로 `.tar.zst` artifact를 만들고, manifest/checksum/callback/download link를 검증한다.
4. 새 빈 DB `kor_travel_geo_t046_daegu_restore`에 `db_restore`를 실행한다.
5. 원본/복원 DB의 핵심 row count, `mv_geocode_target`, 대구 geocode/reverse smoke test가 일치하는지 확인한다.

## 결과

- 운영자는 검증 완료 DB를 압축 artifact로 보존할 수 있다.
- 재검증과 재설치 복구가 원천 full-load보다 훨씬 빠른 경로를 갖는다.
- 백업/복원 작업도 `load_jobs`와 같은 관측·취소·복구 규칙을 따른다.
- logical dump라 물리 snapshot보다 느릴 수 있지만 DB 단위 이식성과 리뷰 가능한 manifest를 얻는다.

## 구현 결과

- T-046에서 DTO, API router, job handler, CLI, UI를 구현했다.
- 백업 metadata는 `ops.artifacts(artifact_type='db_backup')`에 저장한다. 복원 실행 로그는 `ops.artifacts(artifact_type='db_restore_log')`에 저장한다.
- `pg_dump`/`pg_restore` command builder는 DSN password를 argv에서 제거하고 `PGPASSWORD` 환경변수로 주입한다. 로그용 command도 password를 포함하지 않는다.
- `KTG_BACKUP_ALLOWED_DIRS`와 `KTG_BACKUP_CALLBACK_ALLOWED_HOSTS`는 문서 예시처럼 comma-separated env 값을 받을 수 있도록 `NoDecode` + validator로 처리한다.
- 대구광역시 부분 적재 DB `kor_travel_geo_t046_daegu`를 `t046_daegu_backup.tar.zst`로 백업하고, `kor_travel_geo_t046_daegu_restore`에 복원해 row count와 geocode/reverse smoke test를 비교했다.
- T-050 2차에서 callback HMAC header, retry/backoff, attempt별 callback ID, `manifest.callback_delivery` 기록을 추가했다. 수신자 측 replay 저장소는 이 저장소가 관리하지 않으므로 운영 endpoint에서 timestamp window와 callback ID de-duplication을 적용해야 한다.
- T-050 3차에서 dump/archive/checksum/extract 구간에 file/archive size sampler를 추가했다. schema 변경 없이 기존 `load_jobs.progress`, `current_stage`, `log_tail`에 byte 기반 보조 진행률을 남긴다.

## 후속

- (open) callback 수신 endpoint 예제와 replay window/de-duplication 운영 가이드를 추가한다.
- (open) restore 취소 시 target DB drop/quarantine 정책을 구현한다.
- (open) 디스크 여유 공간 사전 추정과 PostgreSQL/PostGIS major mismatch hard-fail 정책을 추가한다.
- (open) 같은 호스트 초고속 재해복구가 필요하면 물리 snapshot 전략을 별도 ADR로 검토한다.
